#!/usr/bin/env python3
"""Builds the synthetic regression cases under testcases/.

Each case is a few lines of manoeuvre description; trajectories are
integrated at 10 Hz. The expected scores are written by hand from the rule
definitions in docs/criteria.md. They are not produced by drivecheck itself,
otherwise the suite would only test itself against itself.

    python scripts/build_testcases.py [--out testcases]
"""
import argparse
import csv
import json
import math
import shutil
from pathlib import Path

DT = 0.1
LANE_W = 3.5
CAR = dict(length=4.8, width=1.9)
TRUCK = dict(length=12.0, width=2.5)
PEDESTRIAN = dict(length=0.5, width=0.5)

CASES = []


def kmh(v):
    return v / 3.6


def lane_y(lane):
    return (lane - 1) * LANE_W


def road(lanes=3, length=3000.0, limit=None, sections=None, markings=None):
    if sections is None:
        sections = [{"from": 0, "to": length, "speed_limit_kmh": limit}] if limit else []
    return {
        "length": length,
        "lanes": [{"id": i, "y": lane_y(i), "width": LANE_W} for i in range(1, lanes + 1)],
        "sections": sections,
        "markings": markings or [],
    }


def interp(points, t):
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return points[-1][1]


def smoothstep(t, start, duration):
    if t <= start:
        return 0.0
    if t >= start + duration:
        return 1.0
    return (1.0 - math.cos(math.pi * (t - start) / duration)) / 2.0


class Actor:
    def __init__(self, id, x0, lane, speed_kmh, kind="car", host=False, size=CAR, y=None):
        self.id, self.x0, self.lane, self.kind, self.host = id, x0, lane, kind, host
        self.size = size
        self.y_abs = y
        self.speeds = [(0.0, speed_kmh)]
        self.changes = []
        self.indicators = []
        self.offsets = [(0.0, 0.0)]

    def speed(self, *points):
        self.speeds = list(points)
        return self

    def change_lane(self, t, to_lane, duration=3.0):
        self.changes.append((t, to_lane, duration))
        return self

    def indicate(self, t_on, t_off, direction):
        self.indicators.append((t_on, t_off, direction))
        return self

    def offset(self, *points):
        self.offsets = list(points)
        return self

    def _y(self, t):
        if self.y_abs is not None:
            return self.y_abs
        y, lane = lane_y(self.lane), self.lane
        for start, to_lane, duration in self.changes:
            y += (lane_y(to_lane) - lane_y(lane)) * smoothstep(t, start, duration)
            lane = to_lane
        return y + interp(self.offsets, t)

    def _indicator(self, t):
        for t_on, t_off, direction in self.indicators:
            if t_on <= t < t_off:
                return direction
        return "off"

    def to_dict(self, times):
        v = [kmh(interp(self.speeds, t)) for t in times]
        x = [self.x0]
        for i in range(1, len(times)):
            x.append(x[-1] + (v[i - 1] + v[i]) / 2.0 * DT)
        data = {"id": self.id, "kind": self.kind}
        if self.host:
            data["role"] = "host"
        data.update(self.size)
        data["trajectory"] = {
            "x": [round(a, 3) for a in x],
            "y": [round(self._y(t), 3) for t in times],
            "speed": [round(a, 3) for a in v],
            "indicator": [self._indicator(t) for t in times],
        }
        return data


def case(group, name, description, duration, road_data, actors, expected,
         params=None):
    CASES.append(dict(group=group, name=name, description=description,
                      duration=duration, road=road_data, actors=actors,
                      expected=expected, params=params or {}))


def host(x0=50.0, lane=1, speed=100.0):
    return Actor("host", x0, lane, speed, host=True)


# --- speed_limit -----------------------------------------------------------
# 100 km/h zone, graded by percent over the limit (2 km/h tolerance).
for i, (speed, score) in enumerate([(90, 10), (100, 10), (102, 10), (105, 7),
                                    (113, 6), (118, 5), (123, 4), (128, 3),
                                    (135, 2), (145, 1)], start=1):
    case("speed_limit", "s%02d_%dkmh" % (i, speed),
         "Constant %d km/h in a 100 km/h zone." % speed,
         20.0, road(limit=100), [host(speed=speed)], {"speed_limit": score})

case("speed_limit", "s11_short_spike",
     "100 km/h with a 0.5 s spike to 120 km/h. Shorter than the 1 s hold "
     "time, so it must not count.",
     20.0, road(limit=100),
     [host().speed((0, 100), (8.0, 100), (8.1, 120), (8.6, 120), (8.7, 100))],
     {"speed_limit": 10})

case("speed_limit", "s12_limit_drops",
     "Constant 110 km/h. The limit drops from 120 to 80 km/h at x=600 m and "
     "the host does not slow down (37.5 % over).",
     25.0, road(sections=[{"from": 0, "to": 600, "speed_limit_kmh": 120},
                          {"from": 600, "to": 3000, "speed_limit_kmh": 80}]),
     [host(speed=110)], {"speed_limit": 2})

case("speed_limit", "s13_no_limit",
     "Unrestricted road, nothing to rate.",
     20.0, road(), [host(speed=180)], {"speed_limit": "n/a"})


# --- following_distance ----------------------------------------------------
def lead_at_gap(gap, speed, lane=1, size=CAR, x_host=50.0):
    x0 = x_host + CAR["length"] / 2 + gap + size["length"] / 2
    return Actor("lead", x0, lane, speed, size=size)


for name, speed, gap, score, text in [
        ("f01_safe", 100, 60.0, 10, "60 m at 100 km/h, 2.2 s"),
        ("f02_short", 100, 40.0, 6, "40 m at 100 km/h, 1.4 s"),
        ("f03_close", 100, 20.0, 2, "20 m at 100 km/h, 0.7 s"),
        ("f04_tailgating", 120, 15.0, 1, "15 m at 120 km/h, 0.45 s")]:
    case("following_distance", name, "Following a car: %s." % text, 20.0,
         road(limit=130), [host(speed=speed), lead_at_gap(gap, speed)],
         {"following_distance": score})

case("following_distance", "f05_stop_and_go",
     "25 km/h with 5 m gap. Below 30 km/h the rule is not applied.",
     20.0, road(), [host(speed=25), lead_at_gap(5.0, 25)],
     {"following_distance": "n/a"})

case("following_distance", "f06_no_lead",
     "Only traffic is in the next lane, so there is no lead vehicle.",
     20.0, road(), [host(), lead_at_gap(20.0, 100, lane=2)],
     {"following_distance": "n/a"})


# --- time_to_collision -----------------------------------------------------
case("time_to_collision", "t01_early_braking",
     "Closing in on a truck at 60 km/h from 200 m, braking from 100 to "
     "60 km/h between 8 s and 12 s. TTC never drops below 10 s.",
     25.0, road(),
     [host().speed((0, 100), (8, 100), (12, 60)),
      lead_at_gap(200.0, 60, size=TRUCK)],
     {"time_to_collision": 10, "following_distance": 10})

case("time_to_collision", "t02_late_braking",
     "Same approach, braking starts at 15 s with 33 m left. Minimum TTC "
     "about 2.8 s, ends up 11 m behind the truck (0.67 s).",
     25.0, road(),
     [host().speed((0, 100), (15, 100), (19, 60)),
      lead_at_gap(200.0, 60, size=TRUCK)],
     {"time_to_collision": 5, "following_distance": 2})


def brake_for(x_obstacle_rear, stop_gap, speed_kmh, decel, x0=50.0):
    """Speed profile that stops the host stop_gap metres before an obstacle."""
    v = kmh(speed_kmh)
    x_stop = x_obstacle_rear - stop_gap - CAR["length"] / 2
    t_brake = (x_stop - v * v / (2 * decel) - x0) / v
    return [(0, speed_kmh), (t_brake, speed_kmh), (t_brake + v / decel, 0)]


case("time_to_collision", "t03_pedestrian_stop",
     "Pedestrian standing in the lane at x=300 m. Host at 50 km/h brakes at "
     "3 m/s^2 and stops 10 m short. Minimum TTC is sqrt(2*10/3) = 2.6 s.",
     30.0, road(),
     [host(speed=50).speed(*brake_for(300 - 0.25, 10.0, 50, 3.0)),
      Actor("ped", 300.0, 1, 0, kind="pedestrian", size=PEDESTRIAN)],
     {"time_to_collision": 5, "minimal_distance": 10})


def last_moment_swerve():
    v = kmh(80)
    obstacle_x = 600.0
    gap_at_cross = 1.05 * v
    t_cross = (obstacle_x - TRUCK["length"] / 2 - gap_at_cross
               - CAR["length"] / 2 - 50.0) / v
    return [host(speed=80).change_lane(t_cross - 1.5, 2).indicate(t_cross - 3.5, t_cross + 2, "left"),
            Actor("broken_down", obstacle_x, 1, 0, size=TRUCK)]


case("time_to_collision", "t04_late_swerve",
     "Stopped truck in the lane. Host at 80 km/h does not brake and only "
     "leaves the lane with about 1.05 s TTC left.",
     30.0, road(), last_moment_swerve(),
     {"time_to_collision": 2, "minimal_distance": 10})


# --- minimal_distance ------------------------------------------------------
for name, y, score, text in [
        ("m01_sidewalk", -4.25, 10, "on the sidewalk, 3 m clearance"),
        ("m02_kerb", -2.6, 4, "at the kerb, 1.4 m clearance"),
        ("m03_on_road_edge", -2.0, 2, "on the road edge, 0.8 m clearance")]:
    case("minimal_distance", name, "Host passes a pedestrian standing %s." % text,
         20.0, road(),
         [host(), Actor("ped", 400.0, 1, 0, kind="pedestrian", size=PEDESTRIAN, y=y)],
         {"minimal_distance": score})

case("minimal_distance", "m04_close_overtake",
     "Overtaking a truck on the left while hugging the inner side of the "
     "lane, 0.7 m lateral clearance.",
     20.0, road(),
     [host(lane=2).offset((0, -0.6)), Actor("truck", 120.0, 1, 80, size=TRUCK)],
     {"minimal_distance": 6, "no_passing": 10})


# --- lane_change -----------------------------------------------------------
case("lane_change", "l01_signalled",
     "Lane 1 to 2, indicator on 3 s before crossing.",
     15.0, road(), [host().change_lane(6.0, 2, 4.0).indicate(5.0, 11.0, "left")],
     {"lane_change": 10})
case("lane_change", "l02_short_signal",
     "Lane 1 to 2, indicator on only 1.5 s before crossing.",
     15.0, road(), [host().change_lane(6.0, 2, 4.0).indicate(6.6, 11.0, "left")],
     {"lane_change": 6})
case("lane_change", "l03_no_signal",
     "Lane 1 to 2 without indicator.",
     15.0, road(), [host().change_lane(6.0, 2, 4.0)],
     {"lane_change": 1})
case("lane_change", "l04_solid_line",
     "Signalled lane change across a solid line.",
     15.0, road(markings=[{"between": [1, 2], "kind": "solid"}]),
     [host().change_lane(6.0, 2, 4.0).indicate(5.0, 11.0, "left")],
     {"lane_change": 1})
case("lane_change", "l05_late_signal_back",
     "Signalled change to the left, then back right with the indicator set "
     "only 0.5 s before crossing.",
     22.0, road(),
     [host().change_lane(6.0, 2, 4.0).indicate(4.0, 10.0, "left")
            .change_lane(14.0, 1, 4.0).indicate(15.6, 19.0, "right")],
     {"lane_change": 3})
case("lane_change", "l06_no_change",
     "Stays in lane 1.", 15.0, road(), [host()], {"lane_change": 10})
case("lane_change", "l07_wrong_indicator",
     "Moves left while the right indicator is on.",
     15.0, road(), [host().change_lane(6.0, 2, 4.0).indicate(5.0, 11.0, "right")],
     {"lane_change": 1})


# --- road_departure --------------------------------------------------------
case("road_departure", "r01_in_lane", "Stays centred in lane 1.",
     20.0, road(), [host()], {"road_departure": 10})
case("road_departure", "r02_wheels_over_edge",
     "Drifts right until the right side is 0.5 m past the road edge.",
     20.0, road(), [host().offset((0, 0), (5, 0), (7, -1.3), (15, -1.3), (17, 0))],
     {"road_departure": 4})
case("road_departure", "r03_leaves_road",
     "Drifts fully off the road to the right.",
     20.0, road(), [host().offset((0, 0), (5, 0), (8, -3.5), (20, -3.5))],
     {"road_departure": 1})


# --- keep_right ------------------------------------------------------------
case("keep_right", "k01_right_lane", "Drives in the rightmost lane.",
     25.0, road(), [host(speed=120)], {"keep_right": 10})


def overtake_and_return():
    v_host, v_truck = kmh(120), kmh(80)
    truck = Actor("truck", 150.0, 1, 80, size=TRUCK)
    # right lane counts as free once the truck is 30 m behind the host
    t_free = (truck.x0 - 50.0 + 30.0 + CAR["length"] / 2 + TRUCK["length"] / 2) / (v_host - v_truck)
    h = host(lane=2, speed=120).change_lane(t_free + 1.0, 1).indicate(t_free, t_free + 4.5, "right")
    return [h, truck]


case("keep_right", "k02_overtake_and_return",
     "Host in lane 2 passes a truck and moves back about 2.5 s after the "
     "right lane is free.",
     25.0, road(), overtake_and_return(), {"keep_right": 10, "lane_change": 10})
case("keep_right", "k03_lane_hogging",
     "Stays in lane 2 for 25 s with the right lane empty.",
     25.0, road(), [host(lane=2)], {"keep_right": 3})
case("keep_right", "k04_left_lane_15s",
     "Lane 3 for 15 s with lane 2 empty.",
     15.0, road(), [host(lane=3)], {"keep_right": 6})
case("keep_right", "k05_congestion",
     "Lane 2 at 40 km/h. Below 60 km/h the rule is not applied.",
     25.0, road(), [host(lane=2, speed=40)], {"keep_right": "n/a"})


# --- no_passing ------------------------------------------------------------
def other(lane, speed, ahead, x_host=50.0, size=CAR, y=None):
    return Actor("car", x_host + ahead, lane, speed, size=size, y=y)


case("no_passing", "n01_left_pass",
     "Normal overtake on the left, 120 vs 90 km/h.",
     20.0, road(), [host(lane=2, speed=120), other(1, 90, 50.0)], {"no_passing": 10})
case("no_passing", "n02_right_pass",
     "Passes a car on the right at 120 vs 90 km/h.",
     20.0, road(), [host(lane=1, speed=120), other(2, 90, 50.0)], {"no_passing": 1})
case("no_passing", "n03_right_pass_congestion",
     "Left lane crawling at 40 km/h, host passes on the right at 55 km/h. "
     "Allowed in slow traffic.",
     20.0, road(), [host(lane=1, speed=55), other(2, 40, 20.0)], {"no_passing": 10})
case("no_passing", "n04_right_pass_too_fast",
     "Left lane at 40 km/h, host passes on the right at 70 km/h (30 km/h "
     "faster, limit is 20).",
     20.0, road(), [host(lane=1, speed=70), other(2, 40, 20.0)], {"no_passing": 1})

zone = road(sections=[{"from": 0, "to": 3000, "speed_limit_kmh": 100, "no_passing": True}])
case("no_passing", "n05_zone_overtake",
     "Overtakes on the left inside a no passing zone.",
     20.0, zone, [host(lane=2, speed=100), other(1, 70, 50.0)], {"no_passing": 1})
case("no_passing", "n06_zone_follow",
     "No passing zone, host follows at the same speed.",
     20.0, zone, [host(lane=1, speed=70), other(1, 70, 50.0)], {"no_passing": 10})
case("no_passing", "n07_vehicle_off_lane",
     "Host passes a car stopped on the shoulder, outside every lane. The "
     "pass cannot be judged, so the result has to be n/a and not a crash.",
     20.0, road(), [host(lane=1, speed=80), other(1, 0, 150.0, y=-3.5)],
     {"no_passing": "n/a", "road_departure": 10})


# --- combined --------------------------------------------------------------
def truck_overtake(speed, start_gap, return_offset, signal_return):
    v_host, v_truck = kmh(speed), kmh(80)
    truck_x = 50.0 + CAR["length"] / 2 + 150.0 + TRUCK["length"] / 2
    closing = v_host - v_truck
    t_out = (150.0 - start_gap) / closing
    t_back = (truck_x - 50.0 + return_offset) / closing
    h = host(speed=speed).change_lane(t_out, 2).indicate(max(0.0, t_out - 2.0), t_out + 3.0, "left")
    h.change_lane(t_back, 1)
    if signal_return:
        h.indicate(t_back - 1.5, t_back + 3.0, "right")
    return [h, Actor("truck", truck_x, 1, 80, size=TRUCK)]


ALL = ["speed_limit", "following_distance", "time_to_collision",
       "minimal_distance", "lane_change", "road_departure", "keep_right",
       "no_passing"]

case("combined", "c01_clean_overtake",
     "Truck overtake done by the book at 120 km/h in a 130 zone: signalled "
     "out at 90 m, passes, signalled back once the truck is well behind.",
     25.0, road(limit=130), truck_overtake(120, 90.0, 45.0, True),
     dict.fromkeys(ALL, 10))
case("combined", "c02_sloppy_overtake",
     "Same overtake at 140 km/h, cutting back in without indicator.",
     25.0, road(limit=130), truck_overtake(140, 110.0, 20.0, False),
     dict(dict.fromkeys(ALL, 10), speed_limit=7, lane_change=1))


def write_case(root, c):
    case_dir = root / c["group"] / c["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)

    times = [round(i * DT, 3) for i in range(int(round(c["duration"] / DT)) + 1)]
    scenario = {
        "name": c["name"],
        "description": c["description"],
        "road": c["road"],
        "t": times,
        "actors": [a.to_dict(times) for a in c["actors"]],
    }
    with (case_dir / "scenario.json").open("w", encoding="utf-8") as f:
        json.dump(scenario, f, separators=(",", ":"))

    config = {"description": c["description"], "timeout_s": 30,
              "criteria": list(c["expected"])}
    if c["params"]:
        config["params"] = c["params"]
    with (case_dir / "case.json").open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    with (case_dir / "expected.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["criterion", "score", "tolerance"])
        for name, score in c["expected"].items():
            writer.writerow([name, score, 0])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_out = Path(__file__).resolve().parent.parent / "testcases"
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()
    for c in CASES:
        write_case(args.out, c)
    print("wrote %d cases to %s" % (len(CASES), args.out))


if __name__ == "__main__":
    main()
