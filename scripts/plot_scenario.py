#!/usr/bin/env python3
"""Top view and speed plot of a scenario, with the criterion scores in the title.

    python scripts/plot_scenario.py testcases/combined/c02_sloppy_overtake/scenario.json -o c02.png

Needs matplotlib (not a dependency of the package itself).
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from drivecheck.engine import evaluate  # noqa: E402
from drivecheck.scenario import load_scenario  # noqa: E402


def plot(scenario, criteria, out):
    road = scenario.road
    fig, (top, speed) = plt.subplots(2, 1, figsize=(11, 5.5),
                                     gridspec_kw={"height_ratios": [1.3, 1]})

    xs = [f.host.x for f in scenario.frames]
    x_min, x_max = min(xs) - 20, max(xs) + 20
    for lane in road.lanes:
        lo = lane.y_center - lane.width / 2
        top.axhspan(lo, lo + lane.width, color="0.93" if lane.id % 2 else "0.88", lw=0)
    for lane in road.lanes[:-1]:
        y = lane.y_center + lane.width / 2
        top.axhline(y, color="white", lw=1.5, ls=(0, (6, 6)))

    actors = {}
    for f in scenario.frames:
        for a in (f.host,) + f.others:
            actors.setdefault(a.id, []).append((f.t, a))

    for actor_id, states in actors.items():
        kind = states[0][1].kind
        style = dict(lw=2.2, color="#c0392b") if actor_id == "host" else dict(lw=1.4, color="#2c3e50")
        if kind == "pedestrian":
            top.plot([s.x for _, s in states], [s.y for _, s in states], "o", color="#8e44ad", label=actor_id)
            continue
        top.plot([s.x for _, s in states], [s.y for _, s in states], label=actor_id, **style)
        on = [(s.x, s.y) for _, s in states if s.indicator in ("left", "right")]
        if actor_id == "host" and on:
            top.plot(*zip(*on), ".", color="#f39c12", ms=3, label="indicator on")
        speed.plot([t for t, _ in states], [s.speed_kmh for _, s in states], label=actor_id, **style)

    top.set_xlim(x_min, x_max)
    top.set_ylim(road.lanes[0].y_center - road.lanes[0].width,
                 road.lanes[-1].y_center + road.lanes[-1].width)
    top.set_xlabel("x [m]")
    top.set_ylabel("y [m]")
    top.legend(loc="upper right", fontsize=8, ncol=4)

    for section in road.sections:
        if section.speed_limit_kmh:
            speed.axhline(section.speed_limit_kmh, color="0.5", ls="--", lw=1)
    speed.set_xlabel("t [s]")
    speed.set_ylabel("speed [km/h]")
    speed.grid(alpha=0.3)

    scores = "   ".join("%s %s" % (r.criterion, "n/a" if r.score is None else "%g" % r.score)
                        for r in evaluate(scenario, criteria))
    fig.suptitle("%s\n%s" % (scenario.name, scores), fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print("saved", out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario")
    parser.add_argument("-o", "--out", default="scenario.png")
    parser.add_argument("--criteria", help="comma separated, default all")
    args = parser.parse_args()
    plot(load_scenario(args.scenario),
         args.criteria.split(",") if args.criteria else None, args.out)


if __name__ == "__main__":
    main()
