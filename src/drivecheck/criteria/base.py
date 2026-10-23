"""Common pieces for criteria.

Every criterion turns a whole scenario into a score from 1 (clear violation)
to 10 (fully compliant), or None when the scenario never gives it anything
to judge (no lead vehicle, no speed limit, ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..model import ActorState, Frame, Road, Scenario

BEST = 10.0
WORST = 1.0


@dataclass
class CriterionResult:
    criterion: str
    score: Optional[float]
    rated_frames: int = 0
    findings: List[str] = field(default_factory=list)
    error: Optional[str] = None


class Criterion:
    name = ""
    defaults: Dict[str, float] = {}

    def __init__(self, **params):
        unknown = set(params) - set(self.defaults)
        if unknown:
            raise ValueError("%s: unknown parameter(s) %s"
                             % (self.name, ", ".join(sorted(unknown))))
        self.params = dict(self.defaults)
        self.params.update(params)

    def evaluate(self, scenario: Scenario) -> CriterionResult:
        raise NotImplementedError


class FrameCriterion(Criterion):
    """Criterion that scores each frame on its own.

    The scenario score is the worst score that lasted for at least ``hold_s``
    seconds, so a single noisy sample cannot drag the result down.
    """
    defaults = {"hold_s": 0.0}

    def rate(self, frame: Frame, road: Road) -> Optional[float]:
        raise NotImplementedError

    def explain(self, frame: Frame, road: Road, score: float) -> str:
        return "t=%.1fs: score %g" % (frame.t, score)

    def evaluate(self, scenario: Scenario) -> CriterionResult:
        scores = [self.rate(f, scenario.road) for f in scenario.frames]
        rated = sum(s is not None for s in scores)
        result = CriterionResult(self.name, None, rated)
        if not rated:
            result.findings.append("nothing to rate in this scenario")
            return result

        window = max(1, int(round(self.params["hold_s"] / scenario.dt)) + 1)
        result.score = sustained_minimum(scores, window)
        if result.score < BEST:
            idx = next(i for i, s in enumerate(scores)
                       if s is not None and s <= result.score)
            result.findings.append(
                self.explain(scenario.frames[idx], scenario.road, scores[idx]))
        return result


def sustained_minimum(scores: Sequence[Optional[float]], window: int) -> float:
    """Lowest score held over ``window`` consecutive frames.

    For each window the best value counts, then the worst window wins.
    Unrated frames (None) count as compliant, so a single bad frame next to
    a gap in the data cannot pass as a sustained violation.
    """
    if window <= 1:
        return min(s for s in scores if s is not None)
    filled = [BEST if s is None else s for s in scores]
    if len(filled) <= window:
        return max(filled)
    return min(max(filled[i:i + window])
               for i in range(len(filled) - window + 1))


def score_at_least(value: float, table: Sequence[Tuple[float, float]]) -> float:
    """Table of (minimum value, score) pairs, best first. Falls back to WORST."""
    for threshold, score in table:
        if value >= threshold:
            return score
    return WORST


def score_at_most(value: float, table: Sequence[Tuple[float, float]]) -> float:
    """Table of (maximum value, score) pairs, best first. Falls back to WORST."""
    for threshold, score in table:
        if value <= threshold:
            return score
    return WORST


def lane_of(road: Road, actor: ActorState) -> Optional[int]:
    lane = road.lane_at(actor.y)
    return lane.id if lane is not None else None


def lead_in_lane(frame: Frame, road: Road, lane_id: int,
                 vehicles_only: bool = True, max_range: float = 250.0):
    """Closest actor ahead of the host in the given lane, with its gap."""
    host = frame.host
    best, best_gap = None, None
    for other in frame.others:
        if vehicles_only and not other.is_vehicle:
            continue
        if other.x <= host.x or lane_of(road, other) != lane_id:
            continue
        gap = max(0.0, other.rear - host.front)
        if gap > max_range:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = other, gap
    return best, best_gap
