import csv
import json
import sys
from pathlib import Path

import pytest

from drivecheck.backends import Backend, CommandBackend
from drivecheck.engine import ReceivedScore
from drivecheck.runner import (ERROR, FAILED, PASSED, TIMEOUT, DiscoveryError,
                               Expectation, compare, discover, run_case,
                               run_suite)

REPO = Path(__file__).resolve().parent.parent


def write_case(root, group, name, expected, results=None, config=None):
    case_dir = root / group / name
    case_dir.mkdir(parents=True)
    with (case_dir / "expected.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["criterion", "score", "tolerance"])
        w.writerows(expected)
    if results is not None:
        (case_dir / "fake_results.csv").write_text(
            "criterion,score\n" + "".join("%s,%s\n" % r for r in results))
    if config is not None:
        (case_dir / "case.json").write_text(json.dumps(config))
    return case_dir


class CopyBackend(Backend):
    """Copies fake_results.csv from the case input to the output."""
    name = "copy"

    def run(self, case, input_dir, output_dir):
        (output_dir / "results.csv").write_text(
            (input_dir / "fake_results.csv").read_text())


def test_compare_reports_every_mismatch():
    expectations = [Expectation("a", 10), Expectation("b", 1), Expectation("c", 5)]
    received = {"a": ReceivedScore(3), "b": ReceivedScore(7), "c": ReceivedScore(5)}
    diffs = compare(expectations, received)
    assert [d.criterion for d in diffs] == ["a", "b"]


def test_compare_is_numeric_with_tolerance():
    assert compare([Expectation("a", 10)], {"a": ReceivedScore(10.0)}) == []
    assert compare([Expectation("a", 7, 1)], {"a": ReceivedScore(8)}) == []
    assert compare([Expectation("a", 7, 1)], {"a": ReceivedScore(9)})


def test_compare_not_rated_missing_and_error():
    exps = [Expectation("na", None), Expectation("gone", 10), Expectation("err", 10),
            Expectation("unrated", 10)]
    received = {"na": ReceivedScore(None), "err": ReceivedScore(None, "boom"),
                "unrated": ReceivedScore(None)}
    reasons = {d.criterion: d.reason for d in compare(exps, received)}
    assert "na" not in reasons
    assert reasons["gone"] == "missing from results"
    assert reasons["err"].startswith("criterion failed")
    assert reasons["unrated"] == "not rated"


def test_discover_collects_all_problems(tmp_path):
    write_case(tmp_path, "g", "ok", [("a", 10, 0)])
    (tmp_path / "g" / "no_expectations").mkdir()
    write_case(tmp_path, "g", "bad_score", [("a", "ten", 0)])
    with pytest.raises(DiscoveryError) as e:
        discover(tmp_path)
    assert "no_expectations" in str(e.value)
    assert "bad_score" in str(e.value)


def test_discover_filter(tmp_path):
    write_case(tmp_path, "speed", "one", [("a", 10, 0)])
    write_case(tmp_path, "lane", "two", [("a", 10, 0)])
    assert [c.id for c in discover(tmp_path, "speed/*")] == ["speed/one"]


def test_cases_do_not_share_inputs(tmp_path):
    # Both cases ship a file with the same name. Each must see its own copy.
    write_case(tmp_path / "cases", "g", "first", [("a", 1, 0)], [("a", 1)])
    write_case(tmp_path / "cases", "g", "second", [("a", 2, 0)], [("a", 2)])
    cases = discover(tmp_path / "cases")
    outcomes = run_suite(cases, CopyBackend(), tmp_path / "work", jobs=2)
    assert [o.status for o in outcomes] == [PASSED, PASSED]


def test_failed_case_keeps_work_dir_and_run_continues(tmp_path):
    write_case(tmp_path / "cases", "g", "a_fails", [("x", 10, 0)], [("x", 1)])
    write_case(tmp_path / "cases", "g", "b_passes", [("x", 10, 0)], [("x", 10)])
    outcomes = run_suite(discover(tmp_path / "cases"), CopyBackend(), tmp_path / "work")
    failed, passed = outcomes
    assert failed.status == FAILED
    assert (failed.work_dir / "output" / "results.csv").is_file()
    assert passed.status == PASSED and passed.work_dir is None


def test_missing_results_is_an_error_not_a_crash(tmp_path):
    write_case(tmp_path / "cases", "g", "c", [("x", 10, 0)])
    [case] = discover(tmp_path / "cases")
    outcome = run_case(case, CommandBackend([sys.executable, "-c", "pass"]),
                       tmp_path / "work")
    assert outcome.status == ERROR
    assert "no results.csv" in outcome.message


def test_command_backend_timeout(tmp_path):
    write_case(tmp_path / "cases", "g", "slow", [("x", 10, 0)], config={"timeout_s": 0.5})
    [case] = discover(tmp_path / "cases")
    backend = CommandBackend([sys.executable, "-c", "import time; time.sleep(5)"])
    assert run_case(case, backend, tmp_path / "work").status == TIMEOUT


def test_command_backend_with_spaces_in_paths(tmp_path):
    root = tmp_path / "with space"
    write_case(root / "cases", "g", "c", [("x", 10, 0)], [("x", 10)])
    [case] = discover(root / "cases")
    script = ("import shutil, sys; shutil.copy(sys.argv[1] + '/fake_results.csv', "
              "sys.argv[2] + '/results.csv')")
    backend = CommandBackend([sys.executable, "-c", script, "{input}", "{output}"])
    outcome = run_case(case, backend, root / "work")
    assert outcome.status == PASSED, outcome.message


def test_shipped_suite_passes(tmp_path):
    from drivecheck.backends import ReplayBackend
    cases = discover(REPO / "testcases")
    assert len(cases) > 40
    outcomes = run_suite(cases, ReplayBackend(), tmp_path)
    failing = ["%s %s %s" % (o.case.id, o.status, o.mismatches or o.message)
               for o in outcomes if o.status != PASSED]
    assert not failing, "\n".join(failing)


def test_wrong_expectation_is_caught(tmp_path):
    import shutil
    from drivecheck.backends import ReplayBackend
    src = REPO / "testcases" / "speed_limit" / "s04_105kmh"
    dst = tmp_path / "cases" / "speed_limit" / "s04_105kmh"
    shutil.copytree(src, dst)
    (dst / "expected.csv").write_text("criterion,score,tolerance\nspeed_limit,10,0\n")
    [outcome] = run_suite(discover(tmp_path / "cases"), ReplayBackend(), tmp_path / "work")
    assert outcome.status == FAILED
    assert outcome.mismatches[0].received == 7
