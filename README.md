# AI-Based Adaptive Production Scheduler
**SPARKTANK 2026 — Problem Statement 005.3: Intelligent Production Planning**

A production scheduler that reacts to real-time disruptions (machine
breakdowns, late materials, worker absence) by automatically re-optimizing
the schedule instead of relying on a fixed plan a human has to manually redo.

## Architecture (4 stages)

| # | Stage | File | What it does |
|---|-------|------|---------------|
| 1 | Production State | `dataset.py` | Synthetic job-shop instance: machines, jobs, operation sequences (machine, duration) with precedence |
| 2 | Optimization Layer | `scheduler.py` | Google OR-Tools **CP-SAT** solver: minimizes makespan subject to precedence + no-overlap-per-machine constraints. Produces the **baseline ("before")** schedule |
| 3 | Disruption + Adaptive Reschedule | `disruption.py`, `rescheduler.py` | Randomly takes a machine offline for a window; freezes already-completed operations; re-solves CP-SAT with the machine-down constraint to produce the **adaptive ("after")** schedule |
| 4 | Explainability | `explain.py`, `gantt.py` | Diffs before/after schedules into a plain-language log (which machine, when, which jobs delayed/re-routed) + a before/after Gantt chart |

> **Predictive Layer (stretch goal, not implemented):** the original 4-stage
> design includes an LSTM-based forecaster that predicts delays/bottlenecks
> from historical logs *before* they cause downstream impact. This prototype
> implements reactive rescheduling (stages 1, 3(CP-SAT reopt), 4) which is
> the core, demo-critical loop; the predictive layer is a natural next step
> once real historical logs are available to train on.

## Why CP-SAT (not a heuristic)

OR-Tools installed cleanly in this environment, so we used the CP-SAT
constraint solver rather than the greedy-heuristic fallback. Trade-off notes,
in case judges ask:

- **CP-SAT (used here):** solves this instance (18 jobs, 6 machines, 72 ops)
  to **proven optimality** in ~10-20 milliseconds. Guarantees the best
  possible makespan for both the baseline and every reschedule. Scales well
  into the hundreds of operations within the same sub-second/low-second
  budget; very large instances would need a tighter time limit (already
  configurable via `time_limit_s`) and would then return the best *feasible*
  (not necessarily optimal) plan found in that budget.
- **Greedy dispatch-rule fallback (not needed, but designed for):** if
  OR-Tools were unavailable, `solve_schedule()`'s interface (jobs, machines,
  forbidden_intervals, fixed_ops -> makespan, schedule) could be swapped for
  a Shortest-Processing-Time-first dispatcher. It would be faster on huge
  instances but gives no optimality guarantee and can be meaningfully worse,
  especially right after a disruption when the "obvious" greedy choice is no
  longer efficient.

## How the reschedule actually works

1. Take the full job list (precedence intact).
2. Any operation that had **fully finished** before the disruption's start
   time is frozen at its original (start, end) — you can't undo work already
   done.
3. An operation still **running** on the disrupted machine when the
   breakdown hits is released back to the solver (it's interrupted and needs
   to be re-timed).
4. Add a hard "no operation may run on machine M during [start, end)"
   constraint for the disrupted machine.
5. Re-run CP-SAT to minimize makespan over what's left. The solver is free
   to re-sequence and re-time every unfinished operation — including on
   machines other than the broken one, since downstream jobs may need to
   shift — but never rewrites history.

## Files

```
dataset.py       Step 1: synthetic job-shop data generator
scheduler.py     Step 2: CP-SAT solver + schedule validator
disruption.py    Step 3: disruption simulator
rescheduler.py   Step 4: adaptive reschedule (freeze + re-solve)
explain.py       Step 5: before/after diff -> plain-language explanation
gantt.py         Step 6: before/after Gantt chart (matplotlib broken_barh)
main.py          Wires stages 1-4 into one runnable pipeline
requirements.txt Python dependencies
```

## Run it

```bash
pip install -r requirements.txt
python3 main.py                      # curated demo scenario (M2 breakdown, +33 delay)
python3 main.py --seed 3             # try a different random disruption
python3 main.py --machine 4          # force machine 4 to break down
python3 main.py --instance-seed 7    # generate a different job-shop instance
```

Each run prints the 4-stage pipeline log (state -> baseline solve ->
disruption -> reschedule -> explanation) and writes
`gantt_before_after.png` — safe to run live on stage, typical end-to-end
time is **under 1 second**.

## Web dashboard

Install the dependencies above, then start the interactive local web UI:

```bash
streamlit run app.py
```

Open the local URL shown in the terminal (usually `http://localhost:8501`).
The sidebar lets you change the generated job-shop instance and disruption
scenario. Select **Run adaptive schedule** to solve both schedules, then use
the live production replay controls to play, pause, restart, change speed, or
seek through the timeline. At the disruption time, unfinished operations move
to their new slots and playback continues on the adaptive schedule. The page
also shows makespan metrics, job-level schedule details, and a plain-language
explanation. Unlike the CLI demo, the web dashboard does not generate a static
Gantt image.

## Validated robustness

`validate_schedule()` is called after every solve (baseline and reschedule)
and asserts: (a) operations within a job run in strict precedence order, and
(b) no two operations on the same machine overlap. `rescheduler.py`
additionally asserts nothing was scheduled inside the machine-down window.
10 randomized disruption scenarios (different machines, windows, and
severities) were run against the demo instance — all 10 produced a valid,
optimal reschedule with no crashes; solve times were 8-14 ms each.

## Demo scenario used for the pitch

`--seed 7` (machine M2 down for `[49, 81]`): baseline makespan **155 ->
188** (+33), 8/18 jobs delayed, 4 machines show visible re-sequencing in the
Gantt chart — the clearest "before vs after recovery" visual of the ones
tested.
