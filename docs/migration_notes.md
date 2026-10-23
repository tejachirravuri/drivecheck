# Notes on the Python 2 runner and what changed

These are the problems I ran into with the 2018 regression runner while
porting it to Python 3, written from memory and from my notes. The code here
does not reuse any of it; this list is what the new design is built around.

| Problem in the old runner | Effect | How drivecheck handles it |
|---|---|---|
| All cases were copied into one shared input folder before the run, including each case's settings file | Every case ran with the settings of the last case copied | Each case gets `work/<group>__<case>/input` with a fresh copy of only its own files (`runner.run_case`) |
| Expected and received scores compared as strings | `1` vs `1.0` reported as a failure | Scores parsed as numbers, per-criterion `tolerance` column (`runner.compare`) |
| The comparison raised on the first differing criterion | Later mismatches in the same case were never reported | All mismatches are collected and reported per case |
| Only two exception types were caught per case | A missing results file or any other error stopped the whole suite | Every failure mode becomes a case status (`failed`, `error`, `timeout`), the run continues |
| Exceptions inside a criterion were logged per frame and the criterion still returned a value | A broken criterion looked like a normal rating | A criterion that raises gets no score and an error; the case is marked as failed (`engine.evaluate`) |
| A crash in the overtaking check when another object was not on any lane | Hundreds of tracebacks per scenario | Passes involving an actor without a lane are reported as "not rated" (`criteria/overtaking.py`, case `no_passing/n07_vehicle_off_lane`) |
| Shell commands built with string formatting, `timeout` wrapper and exit code bit shifting | Broke on paths with spaces, platform specific | `subprocess.run` with an argument list and its own timeout (`backends.CommandBackend`) |
| `map()` used for side effects (creating folders, printing log lines) | After a straight port nothing happens, because `map` is lazy in Python 3. Folder creation also stopped at the first folder that already existed | Plain loops, `mkdir(parents=True)` |
| `.next()`, `err.message`, integer `/` in the report alignment | Python 2 only | Python 3 idioms, no `six` or `2to3` leftovers |
| On failure the complete shared input folder was copied for every failing case | Large, confusing error logs | Work folder of a failing case is kept as it is, passed cases are cleaned up |
| Two criteria missing from the aggregation step | No score at all, noticed only by reading the output | Results are matched by name, a missing criterion is a `missing from results` mismatch |

## Things I would still add

- A JSON schema for `scenario.json` and `case.json`, so format changes like
  the 2018 one (`ego` to `host`) are caught at load time with a clear message
  instead of somewhere inside a criterion.
- A converter for OpenSCENARIO / OpenDRIVE files so real simulator scenarios
  can be used directly.
- Keeping a history of runs and showing per-criterion trends instead of a
  single pass/fail.
