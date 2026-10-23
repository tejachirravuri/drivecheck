"""Runs a set of criteria over one scenario and reads/writes result files."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .criteria import CRITERIA, CriterionResult, create
from .model import Scenario

log = logging.getLogger(__name__)

RESULT_FIELDS = ["criterion", "score", "rated_frames", "error", "findings"]


def evaluate(scenario: Scenario, criteria: Optional[Iterable[str]] = None,
             params: Optional[Dict[str, dict]] = None) -> List[CriterionResult]:
    """Evaluate the scenario with each criterion.

    A criterion that raises does not stop the others. Its result carries the
    error and no score, so it can never be mistaken for a real rating.
    """
    params = params or {}
    results = []
    for name in criteria or CRITERIA:
        criterion = create(name, params.get(name))
        try:
            results.append(criterion.evaluate(scenario))
        except Exception as e:  # report and carry on with the next criterion
            log.exception("criterion %s failed on %s", name, scenario.name)
            results.append(CriterionResult(name, None,
                                           error="%s: %s" % (type(e).__name__, e)))
    return results


def write_results(path: Path, results: Iterable[CriterionResult]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "criterion": r.criterion,
                "score": "" if r.score is None else "%g" % r.score,
                "rated_frames": r.rated_frames,
                "error": r.error or "",
                "findings": " | ".join(r.findings),
            })


@dataclass
class ReceivedScore:
    score: Optional[float]
    error: Optional[str] = None
    findings: str = ""


def read_results(path: Path) -> Dict[str, ReceivedScore]:
    """Read a results file. Only 'criterion' and 'score' columns are required,
    so output from other tools can be compared as well."""
    received = {}
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"criterion", "score"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError("%s: missing column(s) %s" % (path, ", ".join(sorted(missing))))
        for row in reader:
            name = row["criterion"].strip()
            if name in received:
                raise ValueError("%s: criterion %s listed twice" % (path, name))
            received[name] = ReceivedScore(parse_score(row["score"]),
                                           (row.get("error") or "").strip() or None,
                                           row.get("findings") or "")
    return received


def parse_score(text: Optional[str]) -> Optional[float]:
    text = (text or "").strip().lower()
    if text in ("", "n/a", "na", "none"):
        return None
    return float(text)
