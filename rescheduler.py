"""
Step 4: Adaptive rescheduler.

When a disruption hits at time `disruption.start`, we don't throw away the
whole plan and re-solve from scratch. We:

  1. Freeze any operation that had already started before the disruption,
     except work that was mid-flight on the down machine; that operation is
     interrupted and returned to the solver so it can be re-timed. This keeps
     the already-executed portion of the schedule immutable.
  2. Keep the durations of everything else (not-yet-started operations) as-is.
  3. Add a `forbidden_intervals` constraint on the affected machine for the
     disruption window.
  4. Re-solve the SAME CP-SAT model (precedence + no-overlap + fixed ops +
     machine-down window), minimizing makespan again.

This is "reactive re-optimization": the solver is free to re-sequence and
re-time every not-yet-started operation (including on machines other than the
broken one, since downstream jobs may shift), but it cannot rewrite history.
"""

from dataclasses import dataclass
from scheduler import solve_schedule, validate_schedule


@dataclass
class RescheduleResult:
    makespan: int
    scheduled_ops: list
    status: str
    frozen_count: int
    reoptimized_count: int


def reschedule(jobs, machines, baseline_ops, disruption, time_limit_s=10.0):
    """
    Args:
        jobs: original list[Job] (full operation set, precedence intact).
        machines: list of machine ids.
        baseline_ops: the ScheduledOp list from the pre-disruption solve —
            used to decide which operations are "already started" at the
            moment the disruption occurs.
        disruption: Disruption instance (machine, start, end).
        time_limit_s: CP-SAT time limit.

    Returns:
        RescheduleResult
    """
    baseline_by_key = {(so.job_id, so.op_index): so for so in baseline_ops}

    fixed_ops = {}
    for key, so in baseline_by_key.items():
        # History is immutable: if an operation had already started before the
        # disruption, we lock its original (start, end) in place to preserve the
        # work that was already underway.
        #
        # The one exception is an operation that was running on the machine
        # that just went down; that work is interrupted and must be returned to
        # the solver so it can be re-timed after the outage.
        started_before_disruption = so.start < disruption.start
        interrupted_on_down_machine = (
            so.machine == disruption.machine and so.end > disruption.start
        )
        if started_before_disruption and not interrupted_on_down_machine:
            fixed_ops[key] = (so.start, so.end)

    forbidden_intervals = {disruption.machine: [(disruption.start, disruption.end)]}

    makespan, scheduled_ops, status = solve_schedule(
        jobs, machines,
        time_limit_s=time_limit_s,
        forbidden_intervals=forbidden_intervals,
        fixed_ops=fixed_ops,
    )

    if status not in ("OPTIMAL", "FEASIBLE"):
        raise RuntimeError(f"Reschedule failed to find a feasible plan: status={status}")

    validate_schedule(scheduled_ops, {j.job_id: j for j in jobs})

    # extra domain-specific check: nothing was scheduled inside the down window
    for so in scheduled_ops:
        if so.machine == disruption.machine:
            assert not (so.start < disruption.end and so.end > disruption.start), (
                f"Op job{so.job_id}/op{so.op_index} overlaps the down window "
                f"on M{disruption.machine}: [{so.start},{so.end}) vs down "
                f"[{disruption.start},{disruption.end})")

    return RescheduleResult(
        makespan=makespan,
        scheduled_ops=scheduled_ops,
        status=status,
        frozen_count=len(fixed_ops),
        reoptimized_count=sum(len(j.operations) for j in jobs) - len(fixed_ops),
    )


if __name__ == "__main__":
    from dataset import generate_instance
    from scheduler import solve_schedule
    from disruption import simulate_disruption

    machines, jobs = generate_instance()
    base_makespan, base_ops, _ = solve_schedule(jobs, machines)
    print(f"Baseline makespan: {base_makespan}")

    d = simulate_disruption(base_ops, machines, seed=1)
    print(f"Disruption: {d}")

    result = reschedule(jobs, machines, base_ops, d)
    print(f"New makespan after disruption: {result.makespan} "
          f"(baseline was {base_makespan}, delta = +{result.makespan - base_makespan})")
    print(f"Frozen (already-started) ops: {result.frozen_count} | "
          f"Re-optimized ops: {result.reoptimized_count}")
