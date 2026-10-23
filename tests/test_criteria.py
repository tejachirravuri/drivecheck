import pytest

from drivecheck.criteria import create
from drivecheck.engine import evaluate

from helpers import scenario, three_lanes, track

N = 201  # 20 s at 10 Hz


@pytest.mark.parametrize("speed,expected", [
    (80, 10), (101, 10), (104, 7), (112, 6), (150, 1),
])
def test_speed_limit_bands(speed, expected):
    sc = scenario(track("host", 0, 0, speed, N), road=three_lanes(limit=100))
    assert create("speed_limit").evaluate(sc).score == expected


def test_speed_limit_tolerance_is_configurable():
    sc = scenario(track("host", 0, 0, 104, N), road=three_lanes(limit=100))
    assert create("speed_limit", {"tolerance_kmh": 5}).evaluate(sc).score == 10


def test_speed_limit_without_sign_is_not_rated():
    result = create("speed_limit").evaluate(scenario(track("host", 0, 0, 200, N)))
    assert result.score is None
    assert result.rated_frames == 0


def test_unknown_parameter_is_rejected():
    with pytest.raises(ValueError, match="unknown parameter"):
        create("speed_limit", {"tolerence_kmh": 3})


def test_unknown_criterion_is_rejected():
    with pytest.raises(ValueError, match="unknown criterion"):
        create("speedlimit")


def test_following_distance_uses_time_gap():
    host = track("host", 0, 0, 108, N)          # 30 m/s
    lead = track("lead", 4.8 + 46, 0, 108, N)   # 46 m gap, 1.53 s
    assert create("following_distance").evaluate(scenario(host, lead)).score == 8


def test_following_distance_ignores_other_lanes():
    host = track("host", 0, 0, 108, N)
    lead = track("lead", 10, 3.5, 108, N)
    assert create("following_distance").evaluate(scenario(host, lead)).score is None


def test_ttc_contact_is_worst():
    host = track("host", 0, 0, 50, N)
    ped = track("ped", 2.6, 0, 0, N, kind="pedestrian", length=0.5, width=0.5)
    assert create("time_to_collision", {"hold_s": 0}).evaluate(scenario(host, ped)).score == 1


def test_no_passing_on_right_is_flagged():
    host = track("host", 0, 0, 120, N)
    left = track("car", 30, 3.5, 80, N)
    result = create("no_passing").evaluate(scenario(host, left))
    assert result.score == 1
    assert "on the right" in result.findings[0]


def test_no_passing_with_vehicle_off_every_lane_does_not_raise():
    host = track("host", 0, 0, 80, N)
    parked = track("parked", 60, -4.0, 0, N)
    result = create("no_passing").evaluate(scenario(host, parked))
    assert result.score is None
    assert result.error is None
    assert "not on a lane" in result.findings[0]


def test_no_passing_ignores_pedestrians():
    host = track("host", 0, 3.5, 50, N)
    ped = track("ped", 40, 0, 0, N, kind="pedestrian")
    assert create("no_passing").evaluate(scenario(host, ped)).score == 10


def _lane_change(indicator_from=None, direction="left"):
    ys = [0.0 if i < 60 else 3.5 for i in range(N)]
    ind = None
    if indicator_from is not None:
        ind = [direction if indicator_from <= i < 90 else "off" for i in range(N)]
    return track("host", 0, 0, 100, N, ys=ys, indicator=ind)


def test_lane_change_signal_time():
    lc = create("lane_change")
    assert lc.evaluate(scenario(_lane_change(30))).score == 10   # 3.0 s
    assert lc.evaluate(scenario(_lane_change(45))).score == 6    # 1.5 s
    assert lc.evaluate(scenario(_lane_change(56))).score == 3    # 0.4 s
    assert lc.evaluate(scenario(_lane_change())).score == 1
    assert lc.evaluate(scenario(_lane_change(30, "right"))).score == 1


def test_keep_right_counts_free_time():
    sc = scenario(track("host", 0, 3.5, 100, 151))  # lane 2, 15 s, nobody around
    assert create("keep_right").evaluate(sc).score == 6
    assert create("keep_right", {"grace_s": 25}).evaluate(sc).score == 10


def test_keep_right_blocked_by_slower_traffic_ahead():
    host = track("host", 0, 3.5, 100, N)
    # truck is caught up, passed and only 30 m behind after ~14 s
    truck = track("truck", 40, 0, 80, N, length=12, width=2.5)
    assert create("keep_right").evaluate(scenario(host, truck)).score == 10


def test_engine_isolates_a_failing_criterion(monkeypatch):
    from drivecheck.criteria.longitudinal import SpeedLimit

    def boom(self, frame, road):
        raise AttributeError("'NoneType' object has no attribute 'id'")

    monkeypatch.setattr(SpeedLimit, "rate", boom)
    sc = scenario(track("host", 0, 0, 100, N), road=three_lanes(limit=100))
    results = {r.criterion: r for r in evaluate(sc, ["speed_limit", "lane_change"])}
    assert results["speed_limit"].score is None
    assert "AttributeError" in results["speed_limit"].error
    assert results["lane_change"].score == 10
