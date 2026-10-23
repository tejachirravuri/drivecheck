"""Run reports: a CSV for spreadsheets, JUnit XML for CI and a Markdown summary."""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import List, Optional

from .runner import FAILED, PASSED, CaseOutcome


def _fmt(score: Optional[float]) -> str:
    return "n/a" if score is None else "%g" % score


def counts(outcomes: List[CaseOutcome]) -> Counter:
    return Counter(o.status for o in outcomes)


def write_csv(outcomes: List[CaseOutcome], path: Path) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "criterion", "expected", "received", "status", "note"])
        for o in outcomes:
            wrong = {m.criterion: m for m in o.mismatches}
            for exp in o.case.expectations:
                got = o.received.get(exp.criterion)
                if o.status not in (PASSED, FAILED):
                    status, note = o.status, o.message
                elif exp.criterion in wrong:
                    status, note = "mismatch", wrong[exp.criterion].reason
                else:
                    status, note = "ok", ""
                writer.writerow([o.case.id, exp.criterion, _fmt(exp.score),
                                 _fmt(got.score) if got else "", status, note])


def write_junit(outcomes: List[CaseOutcome], path: Path) -> None:
    c = counts(outcomes)
    suite = ET.Element("testsuite", name="drivecheck", tests=str(len(outcomes)),
                       failures=str(c[FAILED]),
                       errors=str(len(outcomes) - c[PASSED] - c[FAILED]),
                       time="%.3f" % sum(o.duration_s for o in outcomes))
    for o in outcomes:
        tc = ET.SubElement(suite, "testcase", classname=o.case.group,
                           name=o.case.name, time="%.3f" % o.duration_s)
        if o.status == FAILED:
            text = "\n".join("%s: expected %s, got %s (%s)" % (
                m.criterion, _fmt(m.expected), _fmt(m.received), m.reason)
                for m in o.mismatches)
            ET.SubElement(tc, "failure", message="%d mismatch(es)"
                          % len(o.mismatches)).text = text
        elif o.status != PASSED:
            ET.SubElement(tc, "error", message=o.status).text = o.message
    ET.ElementTree(suite).write(str(path), encoding="utf-8", xml_declaration=True)


def write_markdown(outcomes: List[CaseOutcome], path: Path, run_id: str,
                   backend: str) -> None:
    c = counts(outcomes)
    lines = [
        "# Regression run %s" % run_id,
        "",
        "Backend: `%s`  " % backend,
        "Cases: %d, passed %d, failed %d, errors %d, timeouts %d" % (
            len(outcomes), c["passed"], c["failed"], c["error"], c["timeout"]),
        "",
        "| Case | Criterion | Expected | Received | Result |",
        "|---|---|---|---|---|",
    ]
    for o in outcomes:
        wrong = {m.criterion for m in o.mismatches}
        for exp in o.case.expectations:
            got = o.received.get(exp.criterion)
            if o.status not in (PASSED, FAILED):
                result = o.status.upper()
            else:
                result = "**MISMATCH**" if exp.criterion in wrong else "ok"
            lines.append("| %s | %s | %s | %s | %s |" % (
                o.case.id, exp.criterion, _fmt(exp.score),
                _fmt(got.score) if got else "-", result))

    problems = [o for o in outcomes if o.status != PASSED]
    if problems:
        lines += ["", "## Details", ""]
        for o in problems:
            lines.append("### %s (%s)" % (o.case.id, o.status))
            if o.case.description:
                lines.append("")
                lines.append(o.case.description)
            lines.append("")
            for m in o.mismatches:
                lines.append("- %s: expected %s, got %s - %s" % (
                    m.criterion, _fmt(m.expected), _fmt(m.received), m.reason))
            if o.message:
                lines.append("- %s" % o.message)
            for name, got in o.received.items():
                if got.findings:
                    lines.append("- %s findings: %s" % (name, got.findings))
            if o.work_dir:
                lines.append("- inputs and outputs kept in `%s`" % o.work_dir)
            lines.append("")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
