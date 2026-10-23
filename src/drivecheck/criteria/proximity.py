"""Clearance to other road users in any direction."""
from __future__ import annotations

from ..model import box_distance
from .base import WORST, FrameCriterion, score_at_least


class MinimalDistance(FrameCriterion):
    name = "minimal_distance"
    defaults = {"hold_s": 0.0, "range_m": 50.0}
    pedestrian_table = ((2.0, 10.0), (1.5, 7.0), (1.0, 4.0), (0.5, 2.0))
    vehicle_table = ((1.0, 10.0), (0.6, 6.0), (0.3, 3.0))

    def _closest(self, frame):
        host = frame.host
        closest = None
        for other in frame.others:
            if abs(other.x - host.x) > self.params["range_m"]:
                continue
            d = box_distance(host, other)
            table = self.vehicle_table if other.is_vehicle else self.pedestrian_table
            score = WORST if d == 0.0 else score_at_least(d, table)
            if closest is None or score < closest[0]:
                closest = (score, other, d)
        return closest

    def rate(self, frame, road):
        closest = self._closest(frame)
        return closest[0] if closest else None

    def explain(self, frame, road, score):
        _, other, d = self._closest(frame)
        return "t=%.1fs: %.2f m to %s (%s)" % (frame.t, d, other.id, other.kind)
