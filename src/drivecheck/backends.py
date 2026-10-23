"""Ways of producing a results.csv for a test case.

The replay backend scores the recorded trajectories directly. The command
backend calls any external program (a simulator wrapped in a shell script,
a docker run, ...) that writes results.csv into the output folder.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from .engine import evaluate, write_results
from .scenario import load_scenario


class BackendError(RuntimeError):
    pass


class CaseTimeout(BackendError):
    pass


class Backend:
    name = "base"

    def run(self, case, input_dir: Path, output_dir: Path) -> None:
        raise NotImplementedError


class ReplayBackend(Backend):
    name = "replay"

    def run(self, case, input_dir, output_dir):
        scenario = load_scenario(input_dir / "scenario.json")
        criteria = case.criteria or [e.criterion for e in case.expectations]
        write_results(output_dir / "results.csv",
                      evaluate(scenario, criteria, case.params))


class CommandBackend(Backend):
    """Runs a command template once per case.

    Placeholders: {input}, {output}, {case} and {timeout}. Arguments are
    passed as a list, so paths with spaces need no quoting.
    """
    name = "command"

    def __init__(self, command: List[str]):
        if not command:
            raise ValueError("command backend needs a command")
        self.command = list(command)

    def run(self, case, input_dir, output_dir):
        args = [part.format(input=input_dir, output=output_dir, case=case.slug,
                            timeout=case.timeout_s) for part in self.command]
        log_path = output_dir.parent / "backend.log"
        with log_path.open("w", encoding="utf-8") as log:
            try:
                proc = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=case.timeout_s)
            except subprocess.TimeoutExpired:
                raise CaseTimeout("killed after %g s" % case.timeout_s) from None
            except OSError as e:
                raise BackendError("could not start %s: %s" % (args[0], e)) from e
        if proc.returncode != 0:
            raise BackendError("exit code %d, see %s" % (proc.returncode, log_path))
        if not (output_dir / "results.csv").is_file():
            raise BackendError("command finished but wrote no results.csv")
