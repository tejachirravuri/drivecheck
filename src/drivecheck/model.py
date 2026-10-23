"""Road and actor model used by all criteria.

Coordinates follow a simple road frame: x runs along the road, y is the
lateral offset (positive to the left). Lanes are numbered from the right,
so lane 1 is the rightmost lane and higher ids are further left.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


KMH_PER_MS = 3.6


@dataclass(frozen=True)
class Lane:
    id: int
    y_center: float
    width: float

    def contains(self, y: float) -> bool:
        return abs(y - self.y_center) <= self.width / 2.0


@dataclass(frozen=True)
class Section:
    """Road attributes that hold between x_start and x_end."""
    x_start: float
    x_end: float
    speed_limit_kmh: Optional[float] = None
    no_passing: bool = False

    def covers(self, x: float) -> bool:
        return self.x_start <= x < self.x_end


@dataclass(frozen=True)
class Marking:
    """Line between two neighbouring lanes. Anything not listed is dashed."""
    lanes: tuple
    kind: str
    x_start: float
    x_end: float

    def applies(self, lane_a: int, lane_b: int, x: float) -> bool:
        return (set(self.lanes) == {lane_a, lane_b}
                and self.x_start <= x < self.x_end)


@dataclass
class Road:
    length: float
    lanes: List[Lane]
    sections: List[Section] = field(default_factory=list)
    markings: List[Marking] = field(default_factory=list)

    def __post_init__(self):
        self.lanes = sorted(self.lanes, key=lambda lane: lane.id)

    @property
    def rightmost_lane(self) -> int:
        return self.lanes[0].id

    def lane_at(self, y: float) -> Optional[Lane]:
        for lane in self.lanes:
            if lane.contains(y):
                return lane
        return None

    def lane_by_id(self, lane_id: int) -> Optional[Lane]:
        for lane in self.lanes:
            if lane.id == lane_id:
                return lane
        return None

    def section_at(self, x: float) -> Optional[Section]:
        for section in self.sections:
            if section.covers(x):
                return section
        return None

    def marking_between(self, lane_a: int, lane_b: int, x: float) -> str:
        for marking in self.markings:
            if marking.applies(lane_a, lane_b, x):
                return marking.kind
        return "dashed"


@dataclass(frozen=True)
class ActorState:
    id: str
    kind: str
    x: float
    y: float
    speed: float          # m/s along the road
    length: float = 4.8
    width: float = 1.9
    indicator: str = "off"  # off | left | right | hazard

    @property
    def speed_kmh(self) -> float:
        return self.speed * KMH_PER_MS

    @property
    def front(self) -> float:
        return self.x + self.length / 2.0

    @property
    def rear(self) -> float:
        return self.x - self.length / 2.0

    @property
    def is_vehicle(self) -> bool:
        return self.kind != "pedestrian"


@dataclass(frozen=True)
class Frame:
    t: float
    host: ActorState
    others: tuple


@dataclass
class Scenario:
    name: str
    road: Road
    dt: float
    frames: List[Frame]
    description: str = ""

    @property
    def duration(self) -> float:
        if not self.frames:
            return 0.0
        return self.frames[-1].t - self.frames[0].t


def box_distance(a: ActorState, b: ActorState) -> float:
    """Gap between two axis-aligned footprints, 0 when they overlap."""
    dx = max(0.0, abs(a.x - b.x) - (a.length + b.length) / 2.0)
    dy = max(0.0, abs(a.y - b.y) - (a.width + b.width) / 2.0)
    return (dx * dx + dy * dy) ** 0.5
