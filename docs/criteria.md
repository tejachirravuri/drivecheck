# Criteria

Every criterion returns a score between 1 and 10 for the whole scenario, or
`n/a` when there was nothing to rate. The thresholds below are my own choice,
loosely based on German traffic rules (StVO) and common driving school
numbers. All of them can be changed per test case through `params` in
`case.json`.

Frame based criteria use a **hold time**: the scenario score is the worst
level that lasted at least `hold_s` seconds, so one noisy sample does not
decide the result. Unrated frames count as compliant for this purpose.

Lanes are numbered from the right, lane 1 is the rightmost lane.

## speed_limit

Host speed against the limit of the road section it is in. No limit, no rating.

| Over the limit | Score |
|---|---|
| up to `tolerance_kmh` (2 km/h) | 10 |
| up to 10 % | 7 |
| up to 15 % | 6 |
| up to 20 % | 5 |
| up to 25 % | 4 |
| up to 30 % | 3 |
| up to 40 % | 2 |
| more | 1 |

Params: `hold_s` 1.0, `tolerance_kmh` 2.0

## following_distance

Time gap to the vehicle ahead in the same lane (bumper to bumper divided by
host speed). 1.8 s corresponds to the "half the speedometer in metres" rule.
Only rated above `min_speed_kmh` and with a lead vehicle within range.

| Time gap | Score |
|---|---|
| ≥ 1.8 s | 10 |
| ≥ 1.5 s | 8 |
| ≥ 1.2 s | 6 |
| ≥ 0.9 s | 4 |
| ≥ 0.6 s | 2 |
| less | 1 |

Params: `hold_s` 1.0, `min_speed_kmh` 30, `max_range_m` 250

## time_to_collision

Gap to whatever is ahead in the host lane (vehicles and pedestrians) divided by
the closing speed. Not closing in counts as 10, contact as 1.

| TTC | Score |
|---|---|
| ≥ 4 s | 10 |
| ≥ 3 s | 8 |
| ≥ 2 s | 5 |
| ≥ 1.5 s | 3 |
| ≥ 1 s | 2 |
| less | 1 |

Params: `hold_s` 0.3, `max_range_m` 150

## minimal_distance

Smallest gap between the host footprint and any other road user within
`range_m`, in any direction. Pedestrians need more room than vehicles.

| Pedestrian | Vehicle | Score |
|---|---|---|
| ≥ 2.0 m | ≥ 1.0 m | 10 |
| ≥ 1.5 m | | 7 |
| | ≥ 0.6 m | 6 |
| ≥ 1.0 m | | 4 |
| | ≥ 0.3 m | 3 |
| ≥ 0.5 m | | 2 |
| less | less | 1 |

Params: `hold_s` 0, `range_m` 50

## lane_change

Event based. A lane change is detected when the lane under the host centre
changes. For each change:

- crossing a solid line scores 1
- the indicator in the direction of travel has to be on before the crossing;
  it may switch off at most `indicator_gap_s` before

| Indicator on before crossing | Score |
|---|---|
| ≥ 2.0 s | 10 |
| ≥ 1.0 s | 6 |
| ≥ 0.3 s | 3 |
| less, none or wrong side | 1 |

The scenario score is the worst lane change. No lane change scores 10.

Params: `lookback_s` 8, `indicator_gap_s` 1.0

## road_departure

| Host | Score |
|---|---|
| inside the carriageway | 10 |
| more than `edge_margin_m` over the outer edge | 4 |
| centre outside every lane | 1 |

Params: `hold_s` 0.3, `edge_margin_m` 0.3

## keep_right

While the host is not in the rightmost lane, the lane to its right is checked
every frame. It counts as free when nothing in it is ahead within 1.8 s, would
be caught up within `horizon_s`, is closer than `rear_clearance_m` behind, or
is coming up from behind within 5 s. The score depends on the longest time the
right lane stayed free without the host moving over (`grace_s` = g).

| Longest free time | Score |
|---|---|
| ≤ g (10 s) | 10 |
| ≤ 2g | 6 |
| ≤ 3g | 3 |
| more | 1 |

Not rated below `min_speed_kmh` (slow traffic).

Params: `grace_s` 10, `horizon_s` 10, `rear_clearance_m` 30, `min_speed_kmh` 60

## no_passing

Event based. Every time the host draws level with another vehicle:

- the other vehicle is in a lane to the **left** (host passes on the right):
  score 1, unless traffic there is slow (≤ `congestion_speed_kmh`) and the host
  is at most `max_speed_diff_kmh` faster
- the other vehicle is to the **right** and the road section is a no passing
  zone: score 1
- otherwise 10

If one of the two vehicles is not on any lane at that moment the pass is
listed as "not rated". If every pass was unrated, the score is `n/a`.

Params: `congestion_speed_kmh` 60, `max_speed_diff_kmh` 20
