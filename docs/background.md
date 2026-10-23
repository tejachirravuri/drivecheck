# Background

## The internship

From July to October 2018 I was an intern in the data science and AI
departments of the BMW Group in Munich. My team worked on evaluating automated
driving functions in simulation: a simulated drive is recorded, and a set of
rule based criteria rates how the vehicle under test ("host") behaved, each on
a scale from 1 to 10. Speed limits, lane changes, overtaking, keeping a safe
distance, emergency corridors and similar traffic rules each had their own
criterion.

To keep those criteria from silently changing, the project had a regression
suite: for every criterion a handful of scenarios with a known expected
rating, run inside docker containers by a Python 2 script.

My tasks were:

1. **Update the regression scenarios.** The simulator had changed its scenario
   description format (still JSON, but renamed fields, for example `host`
   instead of `ego`), so the existing scenarios for twelve criteria, around
   fifty scenarios in total, no longer loaded. I converted them, checked each
   one visually in the simulator against its written description, and ran it
   through the evaluation with the matching criterion configured.
2. **Document deviations.** Where the rating did not match the expectation I
   wrote it up for the criterion owner. That turned out to be a large share:
   graded criteria often collapsed to the lowest score, some scenarios no
   longer showed the situation they were written for (missing signs, roads
   ending before the scenario did), and two criteria were not registered in
   the result aggregation at all, so they never produced a score.
3. **Port the regression runner to Python 3.** The old pipeline was broken and
   the team wanted it on Python 3 and under version control for future
   changes.

## What I took away

The criteria themselves were the interesting part, but most of the time went
into the plumbing around them. A few things stuck:

- A regression suite is only as good as its failure reporting. The old runner
  stopped at the first differing criterion and compared scores as strings, so
  a run could fail on `1` vs `1.0` and hide the real problem behind it.
- Errors inside a criterion were logged and then ignored. One scenario threw
  the same exception on almost every frame (an object that was not on any lane
  had no lane id) and still produced a final rating, which looked like a
  normal result in the summary. A crashing criterion has to fail the case.
- Every case needs its own copy of its inputs. Sharing one input folder meant
  the configuration of the last case was used for all of them.
- Expected values must come from the rule, not from a previous run.
  Otherwise the suite only checks that nothing changed, not that anything is
  right.

[migration_notes.md](migration_notes.md) goes through these in more detail.

## Why a rewrite

The original code and scenarios are BMW internal, so I cannot publish them.
This repository is my own reimplementation of the same idea, written later
and without the simulator: the scenarios are synthetic trajectories generated
by a script, the criteria follow German traffic rules as I understand them
(not any internal specification), and the runner is designed around the
problems listed above. A simulator can still be plugged in through the command
backend.
