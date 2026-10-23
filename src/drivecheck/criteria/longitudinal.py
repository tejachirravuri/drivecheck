"""Speed and spacing along the lane."""
from __future__ import annotations

from .base import (BEST, WORST, FrameCriterion, lane_of, lead_in_lane,
                   score_at_least, score_at_most)


class SpeedLimit(FrameCriterion):
    """Graded by how far the host is above the posted limit, in percent."""
    name = "speed_limit"
    defaults = {"hold_s": 1.0, "tolerance_kmh": 2.0}
    overshoot_table = ((10.0, 7.0), (15.0, 6.0), (20.0, 5.0), (25.0, 4.0),
                       (30.0, 3.0), (40.0, 2.0))

    def rate(self, frame, road):
        section = road.section_at(frame.host.x)
        if section is None or section.speed_limit_kmh is None:
            return None
        limit = float(section.speed_limit_kmh)
        speed = frame.host.speed_kmh
        if speed <= limit + self.params["tolerance_kmh"]:
            return BEST
        overshoot = (speed - limit) / limit * 100.0
        return score_at_most(overshoot, self.overshoot_table)

    def explain(self, frame, road, score):
        limit = road.section_at(frame.host.x).speed_limit_kmh
        return "t=%.1fs: %.0f km/h in a %g km/h zone" % (
            frame.t, frame.host.speed_kmh, limit)


class FollowingDistance(FrameCriterion):
    """Time gap to the vehicle ahead. 1.8 s is the 'half the speedometer' rule."""
    name = "following_distance"
    defaults = {"hold_s": 1.0, "min_speed_kmh": 30.0, "max_range_m": 250.0}
    headway_table = ((1.8, 10.0), (1.5, 8.0), (1.2, 6.0), (0.9, 4.0), (0.6, 2.0))

    def _lead(self, frame, road):
        if frame.host.speed_kmh < self.params["min_speed_kmh"]:
            return None, None
        host_lane = lane_of(road, frame.host)
        if host_lane is None:
            return None, None
        return lead_in_lane(frame, road, host_lane, True,
                            self.params["max_range_m"])

    def rate(self, frame, road):
        lead, gap = self._lead(frame, road)
        if lead is None:
            return None
        return score_at_least(gap / frame.host.speed, self.headway_table)

    def explain(self, frame, road, score):
        lead, gap = self._lead(frame, road)
        return "t=%.1fs: %.1f m behind %s at %.0f km/h (%.2f s)" % (
            frame.t, gap, lead.id, frame.host.speed_kmh, gap / frame.host.speed)


class TimeToCollision(FrameCriterion):
    """Time until the host would reach whatever is ahead in its lane."""
    name = "time_to_collision"
    defaults = {"hold_s": 0.3, "max_range_m": 150.0}
    ttc_table = ((4.0, 10.0), (3.0, 8.0), (2.0, 5.0), (1.5, 3.0), (1.0, 2.0))

    def _ttc(self, frame, road):
        host_lane = lane_of(road, frame.host)
        if host_lane is None:
            return None, None
        lead, gap = lead_in_lane(frame, road, host_lane, False,
                                 self.params["max_range_m"])
        if lead is None:
            return None, None
        closing = frame.host.speed - lead.speed
        if gap <= 0.0:
            return lead, 0.0
        if closing <= 0.1:
            return lead, float("inf")
        return lead, gap / closing

    def rate(self, frame, road):
        lead, ttc = self._ttc(frame, road)
        if lead is None:
            return None
        if ttc == 0.0:
            return WORST
        return score_at_least(ttc, self.ttc_table)

    def explain(self, frame, road, score):
        lead, ttc = self._ttc(frame, road)
        return "t=%.1fs: TTC %.2f s to %s" % (frame.t, ttc, lead.id)
