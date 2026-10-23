"""Overtaking rules: no passing zones and no passing on the right."""
from __future__ import annotations

from .base import BEST, WORST, Criterion, CriterionResult, lane_of


class NoPassing(Criterion):
    """Rates every moment the host draws level with another vehicle.

    Passing on the right is only accepted in slow traffic: the passed vehicle
    is at or below ``congestion_speed_kmh`` and the host is at most
    ``max_speed_diff_kmh`` faster. Passing on the left is a violation inside
    a no passing section.

    If either vehicle is not on a lane at that moment (off road, on the
    shoulder) the pass is reported as unrated instead of raising.
    """
    name = "no_passing"
    defaults = {"congestion_speed_kmh": 60.0, "max_speed_diff_kmh": 20.0}

    def evaluate(self, scenario):
        road = scenario.road
        result = CriterionResult(self.name, BEST, 0)
        last_offset = {}
        unrated = 0

        for frame in scenario.frames:
            host = frame.host
            for other in frame.others:
                if not other.is_vehicle:
                    continue
                offset = other.x - host.x
                before = last_offset.get(other.id)
                last_offset[other.id] = offset
                if before is None or not before > 0.0 >= offset:
                    continue

                host_lane = lane_of(road, host)
                other_lane = lane_of(road, other)
                if host_lane is None or other_lane is None:
                    unrated += 1
                    result.findings.append(
                        "t=%.1fs: passed %s but %s is not on a lane, not rated"
                        % (frame.t, other.id,
                           "host" if host_lane is None else other.id))
                    continue

                result.rated_frames += 1
                score = self._rate_pass(frame, other, host_lane, other_lane,
                                        road, result.findings)
                result.score = min(result.score, score)

        if result.rated_frames == 0:
            if unrated:
                result.score = None
            else:
                result.findings.append("host did not pass anyone")
        return result

    def _rate_pass(self, frame, other, host_lane, other_lane, road, findings):
        host = frame.host
        if other_lane > host_lane:
            slow = other.speed_kmh <= self.params["congestion_speed_kmh"]
            diff = host.speed_kmh - other.speed_kmh
            if slow and diff <= self.params["max_speed_diff_kmh"]:
                findings.append("t=%.1fs: passed %s on the right in slow traffic "
                                "(+%.0f km/h), allowed" % (frame.t, other.id, diff))
                return BEST
            findings.append("t=%.1fs: passed %s on the right at %.0f vs %.0f km/h"
                            % (frame.t, other.id, host.speed_kmh, other.speed_kmh))
            return WORST

        if other_lane < host_lane:
            section = road.section_at(host.x)
            if section is not None and section.no_passing:
                findings.append("t=%.1fs: passed %s inside a no passing zone"
                                % (frame.t, other.id))
                return WORST
        return BEST
