"""Command line entry point.

    drivecheck run [TESTCASES] [--backend replay|command] [--jobs N] ...
    drivecheck evaluate SCENARIO [--criteria a,b]
    drivecheck list [TESTCASES]
"""
from __future__ import annotations

import argparse
import logging
import shlex
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .backends import CommandBackend, ReplayBackend
from .criteria import CRITERIA
from .engine import evaluate
from .report import counts, write_csv, write_junit, write_markdown
from .runner import PASSED, DiscoveryError, discover, run_suite
from .scenario import ScenarioError, load_scenario

log = logging.getLogger("drivecheck")


def cmd_run(args) -> int:
    try:
        cases = discover(Path(args.testcases), args.filter)
    except DiscoveryError as e:
        log.error("%s", e)
        return 2
    if not cases:
        log.error("no test cases found in %s", args.testcases)
        return 2

    if args.backend == "command":
        if not args.command:
            log.error("--backend command needs --command")
            return 2
        backend = CommandBackend(shlex.split(args.command, posix=True))
    else:
        backend = ReplayBackend()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.out) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("%d case(s), backend %s, output in %s", len(cases), backend.name, run_dir)

    outcomes = run_suite(cases, backend, run_dir / "work", args.jobs, args.keep)

    write_csv(outcomes, run_dir / "results.csv")
    write_junit(outcomes, run_dir / "junit.xml")
    write_markdown(outcomes, run_dir / "summary.md", run_id, backend.name)

    c = counts(outcomes)
    log.info("passed %d / %d (failed %d, errors %d, timeouts %d)", c["passed"],
             len(outcomes), c["failed"], c["error"], c["timeout"])
    for o in outcomes:
        if o.status == PASSED:
            continue
        log.warning("%s %s %s", o.status.upper(), o.case.id, o.message)
        for m in o.mismatches:
            log.warning("    %s: expected %s, got %s (%s)", m.criterion,
                        m.expected, m.received, m.reason)
    log.info("report: %s", run_dir / "summary.md")
    return 0 if c["passed"] == len(outcomes) else 1


def cmd_evaluate(args) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except (OSError, ScenarioError) as e:
        log.error("%s", e)
        return 2
    names = args.criteria.split(",") if args.criteria else list(CRITERIA)
    print("%s (%.1f s, %d frames)" % (scenario.name, scenario.duration,
                                       len(scenario.frames)))
    for r in evaluate(scenario, names):
        score = "n/a" if r.score is None else "%g" % r.score
        print("  %-20s %5s  %s" % (r.criterion, score, r.error or "; ".join(r.findings)))
    return 0


def cmd_list(args) -> int:
    try:
        cases = discover(Path(args.testcases), args.filter)
    except DiscoveryError as e:
        log.error("%s", e)
        return 2
    for case in cases:
        expected = ", ".join("%s=%s" % (e.criterion, "n/a" if e.score is None else "%g" % e.score)
                             for e in case.expectations)
        print("%-40s %s" % (case.id, expected))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drivecheck",
                                     description="Rule compliance scoring and scenario regression tests")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command_name", required=True)

    run = sub.add_parser("run", help="run the regression suite")
    run.add_argument("testcases", nargs="?", default="testcases")
    run.add_argument("--backend", choices=["replay", "command"], default="replay")
    run.add_argument("--command", help="command template for the command backend, "
                     "e.g. \"bash run_sim.sh {input} {output}\"")
    run.add_argument("--jobs", "-j", type=int, default=1)
    run.add_argument("--filter", "-k", help="glob on group/case, e.g. 'speed_limit/*'")
    run.add_argument("--out", default="runs", help="where run folders are created")
    run.add_argument("--keep", action="store_true", help="keep work folders of passed cases")
    run.set_defaults(func=cmd_run)

    ev = sub.add_parser("evaluate", help="score a single scenario file")
    ev.add_argument("scenario")
    ev.add_argument("--criteria", help="comma separated, default all")
    ev.set_defaults(func=cmd_evaluate)

    ls = sub.add_parser("list", help="list test cases and their expectations")
    ls.add_argument("testcases", nargs="?", default="testcases")
    ls.add_argument("--filter", "-k")
    ls.set_defaults(func=cmd_list)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)-7s %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
