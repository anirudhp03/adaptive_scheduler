"""
Step 2: Baseline job-shop scheduler using Google OR-Tools CP-SAT.

Model:
  - One interval variable per operation (job, op_index, machine, duration).
  - Precedence: op k of a job must finish before op k+1 of the same job starts.
  - No-overlap: operations sharing a machine cannot overlap in time
    (CP-SAT's AddNoOverlap on the interval variables assigned to that machine).
  - Objective: minimize makespan = max(end time of every job's last operation).

This produces the "before" schedule referenced throughout the rest of the app.
"""

from ortools.sat.python import cp_model
from dataclasses import dataclass


@dataclass
class ScheduledOp:
    job_id: int
    job_name: str
    op_index: int
    machine: int
    duration: int
    start: int
    end: int


def solve_schedule(jobs, machines, horizon=None, time_limit_s=10.0,
                    forbidden_intervals=None, fixed_ops=None):
    """
    Solve the job-shop problem with CP-SAT.

    Args:
        jobs: list[Job] — each with .operations in precedence order. For a
              reschedule, pass in jobs whose remaining operations are just the
              ones not yet completed (see rescheduler.py).
        machines: list[int] of machine ids.
        horizon: upper bound on schedule length; auto-computed if None.
        time_limit_s: CP-SAT wall-clock time limit (kept short for live demo).
        forbidden_intervals: dict[machine_id -> list[(start, end)]] windows
              during which that machine cannot run ANY operation. Used to
              model a machine breakdown when rescheduling.
        fixed_ops: dict[(job_id, op_index) -> (start, end)] operations whose
              time is already locked in (already finished / in progress when
              a disruption hits) and must not move.

    Returns:
        makespan (int), list[ScheduledOp], solve_status (str)
    """
    forbidden_intervals = forbidden_intervals or {}
    fixed_ops = fixed_ops or {}

    model = cp_model.CpModel()

    if horizon is None:
        total_work = sum(op.duration for job in jobs for op in job.operations)
        max_job_work = max((sum(op.duration for op in job.operations) for job in jobs), default=0)
        machine_work = {
            machine: sum(
                op.duration
                for job in jobs
                for op in job.operations
                if op.machine == machine
            )
            for machine in machines
        }
        worst_machine_work = max(machine_work.values(), default=0)
        horizon = max(total_work, max_job_work, worst_machine_work) + 1
        # Add extra time for any disruption windows to keep the search space
        # realistic without inflating it unnecessarily.
        for windows in forbidden_intervals.values():
            horizon += sum(e - s for (s, e) in windows)

    all_tasks = {}          # (job_id, op_index) -> (start_var, end_var, interval_var)
    machine_to_intervals = {m: [] for m in machines}

    for job in jobs:
        for op in job.operations:
            key = (job.job_id, op.op_index)
            suffix = f"_j{job.job_id}_o{op.op_index}"

            if key in fixed_ops:
                # Operation already happened (or is locked) - fix its time.
                fs, fe = fixed_ops[key]
                start_var = model.NewConstant(fs)
                end_var = model.NewConstant(fe)
                interval = model.NewIntervalVar(start_var, fe - fs, end_var, "fixed" + suffix)
            else:
                start_var = model.NewIntVar(0, horizon, "start" + suffix)
                end_var = model.NewIntVar(0, horizon, "end" + suffix)
                interval = model.NewIntervalVar(start_var, op.duration, end_var, "interval" + suffix)

            all_tasks[key] = (start_var, end_var, interval)
            machine_to_intervals[op.machine].append(interval)

    # Precedence constraints: op k finishes before op k+1 starts, within a job.
    for job in jobs:
        ops_sorted = sorted(job.operations, key=lambda o: o.op_index)
        for a, b in zip(ops_sorted, ops_sorted[1:]):
            key_a = (job.job_id, a.op_index)
            key_b = (job.job_id, b.op_index)
            if key_a in fixed_ops and key_b in fixed_ops:
                continue  # both already fixed in the past, nothing to enforce
            model.Add(all_tasks[key_b][0] >= all_tasks[key_a][1])

    # No-overlap per machine (breakdown windows added as fake zero-job intervals).
    for m in machines:
        intervals = list(machine_to_intervals[m])
        for (s, e) in forbidden_intervals.get(m, []):
            if e > s:
                down_interval = model.NewIntervalVar(
                    model.NewConstant(s), e - s, model.NewConstant(e),
                    f"down_m{m}_{s}_{e}")
                intervals.append(down_interval)
        if intervals:
            model.AddNoOverlap(intervals)

    # Objective: minimize makespan.
    makespan = model.NewIntVar(0, horizon, "makespan")
    end_vars = [all_tasks[(job.job_id, job.operations[-1].op_index)][1] for job in jobs if job.operations]
    model.AddMaxEquality(makespan, end_vars)
    model.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    # NOTE: num_search_workers=1 + a fixed random_seed makes CP-SAT's search
    # fully deterministic run-to-run. With workers>1, parallel portfolio
    # search can return a *different* optimal solution (same makespan, but a
    # different tie-broken assignment) on each run, which is confusing for a
    # live demo where we want the exact same before/after picture every time.
    # This instance solves in <20ms single-threaded, so there's no speed cost.
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.Solve(model)

    status_name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, [], status_name

    result = []
    for job in jobs:
        for op in job.operations:
            key = (job.job_id, op.op_index)
            s = solver.Value(all_tasks[key][0])
            e = solver.Value(all_tasks[key][1])
            result.append(ScheduledOp(job.job_id, job.name, op.op_index, op.machine, op.duration, s, e))

    return solver.Value(makespan), result, status_name


def validate_schedule(scheduled_ops, jobs_by_id):
    """
    Sanity-check a solved schedule:
      - operations within a job are in non-decreasing precedence order
      - no two operations on the same machine overlap
    Raises AssertionError with a clear message if broken. Used by the test
    harness so a bad CP-SAT result (or a bug in reschedule stitching) is
    caught immediately instead of silently demoed.
    """
    by_job = {}
    by_machine = {}
    for so in scheduled_ops:
        by_job.setdefault(so.job_id, []).append(so)
        by_machine.setdefault(so.machine, []).append(so)

    for job_id, ops in by_job.items():
        ops.sort(key=lambda o: o.op_index)
        for a, b in zip(ops, ops[1:]):
            assert b.start >= a.end, (
                f"Precedence violated in job {job_id}: op{a.op_index} ends {a.end} "
                f"but op{b.op_index} starts {b.start}")

    for machine, ops in by_machine.items():
        ops.sort(key=lambda o: o.start)
        for a, b in zip(ops, ops[1:]):
            assert b.start >= a.end, (
                f"Overlap on machine {machine}: job{a.job_id} op{a.op_index} "
                f"ends {a.end} but job{b.job_id} op{b.op_index} starts {b.start}")

    return True


if __name__ == "__main__":
    from dataset import generate_instance, instance_summary
    import time

    machines, jobs = generate_instance()
    print(instance_summary(machines, jobs))

    t0 = time.time()
    makespan, scheduled_ops, status = solve_schedule(jobs, machines, time_limit_s=10.0)
    elapsed = time.time() - t0

    print(f"\nSolve status: {status}  |  solve time: {elapsed:.2f}s")
    print(f"Baseline makespan: {makespan}")

    validate_schedule(scheduled_ops, {j.job_id: j for j in jobs})
    print("Schedule validated OK (no precedence violations, no machine overlaps).")

    print("\nFirst 8 scheduled operations:")
    for so in sorted(scheduled_ops, key=lambda o: o.start)[:8]:
        print(f"  Job {so.job_id} ({so.job_name}) op{so.op_index}: "
              f"M{so.machine} [{so.start} -> {so.end}]")
