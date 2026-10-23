import pytest

from drivecheck.criteria.base import score_at_least, score_at_most, sustained_minimum
from drivecheck.model import ActorState, Lane, Marking, Road, box_distance


def test_sustained_minimum_without_hold_is_plain_minimum():
    assert sustained_minimum([10, 4, 10, None, 7], 1) == 4


def test_short_dip_is_ignored():
    scores = [10] * 10 + [1, 1] + [10] * 10
    assert sustained_minimum(scores, 3) == 10
    assert sustained_minimum(scores, 2) == 1


def test_single_frame_next_to_gap_is_not_sustained():
    # one bad frame followed by unrated frames used to count as held
    scores = [10, 10, 10, 2, None, None, None]
    assert sustained_minimum(scores, 3) == 10


def test_sequence_shorter_than_window():
    assert sustained_minimum([3, 3], 5) == 3


def test_score_tables():
    table = ((1.8, 10), (1.2, 6))
    assert score_at_least(2.0, table) == 10
    assert score_at_least(1.2, table) == 6
    assert score_at_least(0.1, table) == 1
    assert score_at_most(5.0, ((10, 7), (20, 5))) == 7
    assert score_at_most(25.0, ((10, 7), (20, 5))) == 1


def test_lane_lookup_and_markings():
    road = Road(1000, [Lane(2, 3.5, 3.5), Lane(1, 0.0, 3.5)],
                markings=[Marking((1, 2), "solid", 100, 200)])
    assert road.rightmost_lane == 1
    assert road.lane_at(0.4).id == 1
    assert road.lane_at(4.0).id == 2
    assert road.lane_at(-3.0) is None
    assert road.marking_between(2, 1, 150) == "solid"
    assert road.marking_between(1, 2, 250) == "dashed"


def test_box_distance():
    a = ActorState("a", "car", 0, 0, 0, length=4, width=2)
    b = ActorState("b", "car", 10, 0, 0, length=4, width=2)
    c = ActorState("c", "car", 0, 3, 0, length=4, width=2)
    assert box_distance(a, b) == pytest.approx(6.0)
    assert box_distance(a, c) == pytest.approx(1.0)
    assert box_distance(a, a) == 0.0
