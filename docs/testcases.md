# Test cases and file formats

## Folder layout

```
testcases/
    speed_limit/
        s04_105kmh/
            scenario.json
            expected.csv
            case.json
    no_passing/
        ...
```

The first level is a group (usually the criterion under test), the second
level is one case. `drivecheck run -k "speed_limit/s0*"` selects cases by
glob on `group/case`.

## expected.csv

```
criterion,score,tolerance
time_to_collision,5,0
following_distance,2,0
```

- `score` is a number or `n/a` (the criterion must not rate this scenario)
- `tolerance` is optional, default 0

## case.json

```json
{
  "description": "Same approach, braking starts at 15 s ...",
  "timeout_s": 30,
  "criteria": ["time_to_collision", "following_distance"],
  "params": {"speed_limit": {"tolerance_kmh": 3}}
}
```

All fields are optional. Without `criteria` the replay backend evaluates the
criteria listed in `expected.csv`.

## scenario.json

```json
{
  "name": "t02_late_braking",
  "road": {
    "length": 3000,
    "lanes": [{"id": 1, "y": 0.0, "width": 3.5}, {"id": 2, "y": 3.5, "width": 3.5}],
    "sections": [{"from": 0, "to": 3000, "speed_limit_kmh": 100, "no_passing": false}],
    "markings": [{"between": [1, 2], "kind": "solid", "from": 0, "to": 500}]
  },
  "t": [0.0, 0.1, 0.2],
  "actors": [
    {
      "id": "host", "role": "host", "kind": "car", "length": 4.8, "width": 1.9,
      "trajectory": {
        "x": [50.0, 52.8, 55.6],
        "y": [0.0, 0.0, 0.0],
        "speed": [27.8, 27.8, 27.8],
        "indicator": ["off", "off", "left"]
      }
    }
  ]
}
```

- x runs along the road, y is the lateral offset, positive to the left
- lanes are numbered from the right; anything not listed in `markings` is dashed
- `speed` in m/s, `indicator` one of `off`, `left`, `right`, `hazard`
- `kind` is `car`, `truck` or `pedestrian`; exactly one actor has `role: host`
- all trajectories share the time base `t`

## Adding cases

The shipped cases come from `scripts/build_testcases.py`. To add one, describe
the manoeuvre there and write the expected score from the rule in
[criteria.md](criteria.md), then regenerate:

```bash
python scripts/build_testcases.py
drivecheck run -k "my_group/*"
```

If the run disagrees, check the case before changing the expectation. The
expectation is the specification.

`scripts/plot_scenario.py` (needs matplotlib) draws a top view and the speed
profile, which helps a lot when a case does not do what its description says.

## Plugging in a simulator

`--backend command --command "<template>"` runs the template once per case,
with `{input}`, `{output}`, `{case}` and `{timeout}` filled in. The program has
to write `{output}/results.csv`:

```
criterion,score
speed_limit,7
lane_change,1
```

Extra columns (`rated_frames`, `error`, `findings`) are optional; a non-empty
`error` marks that criterion as failed. Output of the command goes to
`backend.log` in the case work folder, which is kept for failing cases.
