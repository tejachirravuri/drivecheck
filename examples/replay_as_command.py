#!/usr/bin/env python3
"""Stand-in for a simulator wrapper, used to try out the command backend.

A real wrapper would start the simulator with the scenario from INPUT_DIR,
record the run and score it. This one skips the simulator and scores the
recorded trajectories, but it follows the same contract:

    replay_as_command.py INPUT_DIR OUTPUT_DIR
    -> writes OUTPUT_DIR/results.csv (criterion,score,...)
    -> exit code 0 on success

    drivecheck run --backend command \
        --command "python examples/replay_as_command.py {input} {output}"
"""
import json
import sys
from pathlib import Path

from drivecheck.engine import evaluate, write_results
from drivecheck.scenario import load_scenario


def main(input_dir, output_dir):
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    config = {}
    if (input_dir / "case.json").is_file():
        config = json.loads((input_dir / "case.json").read_text(encoding="utf-8"))
    scenario = load_scenario(input_dir / "scenario.json")
    results = evaluate(scenario, config.get("criteria") or None, config.get("params"))
    write_results(output_dir / "results.csv", results)
    print("%s: %d criteria scored" % (scenario.name, len(results)))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
