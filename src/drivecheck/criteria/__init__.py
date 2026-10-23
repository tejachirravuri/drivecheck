from .base import Criterion, CriterionResult
from .lateral import KeepRight, LaneChange, RoadDeparture
from .longitudinal import FollowingDistance, SpeedLimit, TimeToCollision
from .overtaking import NoPassing
from .proximity import MinimalDistance

CRITERIA = {cls.name: cls for cls in (
    SpeedLimit,
    FollowingDistance,
    TimeToCollision,
    MinimalDistance,
    LaneChange,
    RoadDeparture,
    KeepRight,
    NoPassing,
)}


def create(name, params=None):
    try:
        cls = CRITERIA[name]
    except KeyError:
        raise ValueError("unknown criterion '%s' (known: %s)"
                         % (name, ", ".join(sorted(CRITERIA)))) from None
    return cls(**(params or {}))


__all__ = ["CRITERIA", "Criterion", "CriterionResult", "create"]
