"""Loading scenario files (road description plus recorded trajectories)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .model import ActorState, Frame, Lane, Marking, Road, Scenario, Section


class ScenarioError(ValueError):
    pass


def road_from_dict(data: dict) -> Road:
    lanes = [Lane(int(l["id"]), float(l["y"]), float(l.get("width", 3.5)))
             for l in data["lanes"]]
    if not lanes:
        raise ScenarioError("road needs at least one lane")
    length = float(data["length"])
    sections = [Section(float(s.get("from", 0.0)), float(s.get("to", length)),
                        s.get("speed_limit_kmh"), bool(s.get("no_passing", False)))
                for s in data.get("sections", [])]
    markings = [Marking(tuple(m["between"]), m["kind"],
                        float(m.get("from", 0.0)), float(m.get("to", length)))
                for m in data.get("markings", [])]
    return Road(length, lanes, sections, markings)


def _actor_states(actor: dict, n_samples: int):
    traj = actor["trajectory"]
    for key in ("x", "y", "speed"):
        if len(traj[key]) != n_samples:
            raise ScenarioError("actor %s: '%s' has %d samples, expected %d"
                                % (actor["id"], key, len(traj[key]), n_samples))
    indicator = traj.get("indicator") or ["off"] * n_samples
    for i in range(n_samples):
        yield ActorState(
            id=actor["id"],
            kind=actor.get("kind", "car"),
            x=float(traj["x"][i]),
            y=float(traj["y"][i]),
            speed=float(traj["speed"][i]),
            length=float(actor.get("length", 4.8)),
            width=float(actor.get("width", 1.9)),
            indicator=indicator[i],
        )


def scenario_from_dict(data: dict) -> Scenario:
    road = road_from_dict(data["road"])
    times = [float(t) for t in data["t"]]
    if len(times) < 2:
        raise ScenarioError("scenario needs at least two samples")

    hosts = [a for a in data["actors"] if a.get("role") == "host"]
    if len(hosts) != 1:
        raise ScenarioError("exactly one actor must have role 'host', found %d"
                            % len(hosts))

    host_states = list(_actor_states(hosts[0], len(times)))
    other_states = [list(_actor_states(a, len(times)))
                    for a in data["actors"] if a.get("role") != "host"]

    frames = [Frame(t, host_states[i], tuple(states[i] for states in other_states))
              for i, t in enumerate(times)]
    dt = (times[-1] - times[0]) / (len(times) - 1)
    return Scenario(data.get("name", "unnamed"), road, dt, frames,
                    data.get("description", ""))


def load_scenario(path: Union[str, Path]) -> Scenario:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ScenarioError("%s: %s" % (path, e)) from e
    try:
        return scenario_from_dict(data)
    except KeyError as e:
        raise ScenarioError("%s: missing key %s" % (path, e)) from e
