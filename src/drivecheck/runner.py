"""Regression runner: find test cases, run them, compare against expectations.

Layout of a test case folder::

    testcases/<group>/<case>/
        expected.csv    criterion,score[,tolerance]   (score may be n/a)
        case.json       optional: description, timeout_s, criteria, params
        scenario.json   needed by the replay backend

Every case runs in its own work folder with a fresh copy of its inputs, so
cases cannot overwrite each other's files.
"""
from __future__ import annotations

import csv
import json
import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional

from .backends import Backend, BackendError, CaseTimeout
from .engine import ReceivedScore, parse_score, read_results
from .scenario import ScenarioError

log = logging.getLogger(__name__)

PASSED, FAILED, ERROR, TIMEOUT = "passed", "failed", "error", "timeout"


class DiscoveryError(ValueError):
    pass


@dataclass
class Expectation:
    criterion: str
    score: Optional[float]
    tolerance: float = 0.0


@dataclass
class TestCase:
    __test__ = False  # keep pytest from collecting this class

    group: str
    name: str
    path: Path
    expectations: List[Expectation]
    description: str = ""
    timeout_s: float = 120.0
    criteria: List[str] = field(default_factory=list)
    params: Dict[str, dict] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return "%s/%s" % (self.group, self.name)

    @property
    def slug(self) -> str:
        return "%s__%s" % (self.group, self.name)


@dataclass
class Mismatch:
    criterion: str
    expected: Optional[float]
    received: Optional[float]
    reason: str


@dataclass
class CaseOutcome:
    case: TestCase
    status: str
    mismatches: List[Mismatch] = field(default_factory=list)
    message: str = ""
    duration_s: float = 0.0
    received: Dict[str, ReceivedScore] = field(default_factory=dict)
    work_dir: Optional[Path] = None


def load_expectations(path: Path) -> List[Expectation]:
    expectations = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not {"criterion", "score"} <= set(reader.fieldnames or []):
            raise DiscoveryError("%s: header must contain criterion,score" % path)
        for line, row in enumerate(reader, start=2):
            try:
                expectations.append(Expectation(
                    row["criterion"].strip(),
                    parse_score(row["score"]),
                    float(row.get("tolerance") or 0.0)))
            except ValueError as e:
                raise DiscoveryError("%s line %d: %s" % (path, line, e)) from e
    names = [e.criterion for e in expectations]
    if not names:
        raise DiscoveryError("%s: no expectations" % path)
    if len(set(names)) != len(names):
        raise DiscoveryError("%s: a criterion is listed twice" % path)
    return expectations


def load_case(group: str, case_dir: Path) -> TestCase:
    config = {}
    config_path = case_dir / "case.json"
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as e:
                raise DiscoveryError("%s: %s" % (config_path, e)) from e
    return TestCase(
        group=group,
        name=case_dir.name,
        path=case_dir,
        expectations=load_expectations(case_dir / "expected.csv"),
        description=config.get("description", ""),
        timeout_s=float(config.get("timeout_s", 120.0)),
        criteria=list(config.get("criteria", [])),
        params=dict(config.get("params", {})),
    )


def discover(root: Path, pattern: Optional[str] = None) -> List[TestCase]:
    """Collect all cases below root. Problems are gathered and reported together."""
    root = Path(root)
    if not root.is_dir():
        raise DiscoveryError("test case folder %s does not exist" % root)

    cases, problems = [], []
    for group_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for case_dir in sorted(p for p in group_dir.iterdir() if p.is_dir()):
            case_id = "%s/%s" % (group_dir.name, case_dir.name)
            if pattern and not fnmatch(case_id, pattern):
                continue
            if not (case_dir / "expected.csv").is_file():
                problems.append("%s: expected.csv is missing" % case_id)
                continue
            try:
                cases.append(load_case(group_dir.name, case_dir))
            except DiscoveryError as e:
                problems.append(str(e))
    if problems:
        raise DiscoveryError("invalid test cases:\n  " + "\n  ".join(problems))
    return cases


def compare(expectations: List[Expectation],
            received: Dict[str, ReceivedScore]) -> List[Mismatch]:
    """All differences between expected and received scores, not just the first."""
    mismatches = []
    for exp in expectations:
        got = received.get(exp.criterion)
        if got is None:
            mismatches.append(Mismatch(exp.criterion, exp.score, None,
                                       "missing from results"))
        elif got.error:
            mismatches.append(Mismatch(exp.criterion, exp.score, None,
                                       "criterion failed: %s" % got.error))
        elif exp.score is None and got.score is not None:
            mismatches.append(Mismatch(exp.criterion, None, got.score,
                                       "expected no rating"))
        elif exp.score is not None and got.score is None:
            mismatches.append(Mismatch(exp.criterion, exp.score, None,
                                       "not rated"))
        elif (exp.score is not None
              and abs(got.score - exp.score) > exp.tolerance + 1e-9):
            mismatches.append(Mismatch(exp.criterion, exp.score, got.score,
                                       "score differs"))
    return mismatches


def run_case(case: TestCase, backend: Backend, work_root: Path,
             keep: bool = False) -> CaseOutcome:
    work_dir = Path(work_root) / case.slug
    if work_dir.exists():
        shutil.rmtree(work_dir)
    input_dir, output_dir = work_dir / "input", work_dir / "output"
    shutil.copytree(case.path, input_dir)
    output_dir.mkdir(parents=True)

    outcome = CaseOutcome(case, ERROR, work_dir=work_dir)
    start = time.perf_counter()
    try:
        backend.run(case, input_dir, output_dir)
        outcome.received = read_results(output_dir / "results.csv")
        outcome.mismatches = compare(case.expectations, outcome.received)
        outcome.status = FAILED if outcome.mismatches else PASSED
    except CaseTimeout as e:
        outcome.status, outcome.message = TIMEOUT, str(e)
    except (BackendError, ScenarioError, OSError, ValueError) as e:
        outcome.status, outcome.message = ERROR, "%s: %s" % (type(e).__name__, e)
    outcome.duration_s = time.perf_counter() - start

    if outcome.status == PASSED and not keep:
        shutil.rmtree(work_dir, ignore_errors=True)
        outcome.work_dir = None
    return outcome


def run_suite(cases: List[TestCase], backend: Backend, work_root: Path,
              jobs: int = 1, keep: bool = False) -> List[CaseOutcome]:
    def one(case):
        log.info("running %s", case.id)
        outcome = run_case(case, backend, work_root, keep)
        log.info("%-40s %s (%.2fs)", case.id, outcome.status.upper(),
                 outcome.duration_s)
        return outcome

    if jobs <= 1:
        return [one(c) for c in cases]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(one, cases))
