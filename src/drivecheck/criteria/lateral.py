"""Lane changes, staying on the road and keeping right."""
from __future__ import annotations

from .base import (BEST, WORST, Criterion, CriterionResult, FrameCriterion,
                   lane_of, score_at_least, score_at_most)


class LaneChange(Criterion):
    """Each lane change must be signalled in time and must not cross a solid line."""
    name = "lane_change"
    defaults = {"lookback_s": 8.0, "indicator_gap_s": 1.0}
    signal_table = ((2.0, 10.0), (1.0, 6.0), (0.3, 3.0))

    def _signal_time(self, frames, cross_idx, direction):
        """Seconds the indicator was on before the crossing, 0 if never."""
        t_cross = frames[cross_idx].t
        last_on = None
        for k in range(cross_idx, -1, -1):
            if t_cross - frames[k].t > self.params["indicator_gap_s"]:
                break
            if frames[k].host.indicator == direction:
                last_on = k
                break
        if last_on is None:
            return 0.0
        start = last_on
        while (start > 0 and frames[start - 1].host.indicator == direction
               and t_cross - frames[start - 1].t <= self.params["lookback_s"]):
            start -= 1
        return t_cross - frames[start].t

    def evaluate(self, scenario):
        frames, road = scenario.frames, scenario.road
        result = CriterionResult(self.name, BEST, 0)

        previous = None
        for i, frame in enumerate(frames):
            current = lane_of(road, frame.host)
            if current is None:
                continue
            if previous is not None and current != previous:
                score = self._rate_change(frames, i, previous, current, road,
                                          result.findings)
                result.score = min(result.score, score)
                result.rated_frames += 1
            previous = current

        if result.rated_frames == 0:
            result.findings.append("no lane change in this scenario")
        return result

    def _rate_change(self, frames, i, from_lane, to_lane, road, findings):
        frame = frames[i]
        direction = "left" if to_lane > from_lane else "right"
        score = BEST

        step = 1 if to_lane > from_lane else -1
        for lane in range(from_lane, to_lane, step):
            if road.marking_between(lane, lane + step, frame.host.x) == "solid":
                findings.append("t=%.1fs: crossed solid line between lane %d and %d"
                                % (frame.t, lane, lane + step))
                score = WORST

        signal = self._signal_time(frames, i, direction)
        signal_score = score_at_least(signal, self.signal_table)
        if signal == 0.0:
            findings.append("t=%.1fs: lane %d -> %d without indicator"
                            % (frame.t, from_lane, to_lane))
        elif signal_score < BEST:
            findings.append("t=%.1fs: lane %d -> %d, indicator only %.1f s before"
                            % (frame.t, from_lane, to_lane, signal))
        return min(score, signal_score)


class RoadDeparture(FrameCriterion):
    """Host footprint leaving the outer edges of the carriageway."""
    name = "road_departure"
    defaults = {"hold_s": 0.3, "edge_margin_m": 0.3}

    def _overhang(self, frame, road):
        host = frame.host
        right = road.lanes[0]
        left = road.lanes[-1]
        right_edge = right.y_center - right.width / 2.0
        left_edge = left.y_center + left.width / 2.0
        return max(right_edge - (host.y - host.width / 2.0),
                   (host.y + host.width / 2.0) - left_edge, 0.0)

    def rate(self, frame, road):
        if lane_of(road, frame.host) is None:
            return WORST
        if self._overhang(frame, road) > self.params["edge_margin_m"]:
            return 4.0
        return BEST

    def explain(self, frame, road, score):
        if score == WORST:
            return "t=%.1fs: host is off the road (y=%.2f m)" % (frame.t, frame.host.y)
        return "t=%.1fs: host %.2f m over the road edge" % (
            frame.t, self._overhang(frame, road))


class KeepRight(Criterion):
    """Driving in a left lane while the lane to the right has been free for a while."""
    name = "keep_right"
    defaults = {"grace_s": 10.0, "horizon_s": 10.0, "rear_clearance_m": 30.0,
                "min_speed_kmh": 60.0}

    def _right_lane_free(self, frame, road, right_lane):
        host = frame.host
        for other in frame.others:
            if not other.is_vehicle or lane_of(road, other) != right_lane:
                continue
            if other.x >= host.x:
                gap = other.rear - host.front
                closing = host.speed - other.speed
                if gap < host.speed * 1.8:
                    return False
                if closing > 0 and gap / closing < self.params["horizon_s"]:
                    return False
            else:
                gap = host.rear - other.front
                if gap < self.params["rear_clearance_m"]:
                    return False
                closing = other.speed - host.speed
                if closing > 0 and gap / closing < 5.0:
                    return False
        return True

    def evaluate(self, scenario):
        road = scenario.road
        grace = self.params["grace_s"]
        table = ((grace, 10.0), (2 * grace, 6.0), (3 * grace, 3.0))
        result = CriterionResult(self.name, None, 0)

        free_since = None
        worst_time = 0.0
        for frame in scenario.frames:
            host_lane = lane_of(road, frame.host)
            if host_lane is None or frame.host.speed_kmh < self.params["min_speed_kmh"]:
                free_since = None
                continue
            result.rated_frames += 1
            right_lane = host_lane - 1
            if host_lane == road.rightmost_lane or not self._right_lane_free(
                    frame, road, right_lane):
                free_since = None
                continue
            if free_since is None:
                free_since = frame.t
            if frame.t - free_since > worst_time:
                worst_time = frame.t - free_since
                worst_frame = frame

        if result.rated_frames == 0:
            result.findings.append("nothing to rate in this scenario")
            return result
        result.score = score_at_most(worst_time, table)
        if result.score < BEST:
            result.findings.append(
                "t=%.1fs: lane %d, right lane free for %.1f s"
                % (worst_frame.t, lane_of(road, worst_frame.host), worst_time))
        return result
