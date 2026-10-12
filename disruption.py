"""
Step 3: Disruption simulator.

Randomly picks one machine and a time window (partway through the baseline
schedule's makespan) during which it becomes unavailable — e.g. a breakdown,
maintenance stoppage, or a worker absence that takes the station offline.

We derive the window from the ALREADY-SOLVED baseline schedule so the
disruption plausibly lands in the middle of real activity on that machine
(instead of e.g. picking a window when the machine was idle anyway, which
would be a no-op and a bad demo).
"""

import random
from dataclasses import dataclass


@dataclass
class Disruption:
    machine: int
    start: int
    end: int
    reason: str

    def __str__(self):
        return (f"Machine M{self.machine} DOWN from t={self.start} to t={self.end} "
                f"({self.end - self.start} time units) — reason: {self.reason}")


REASONS = [
    "unplanned mechanical breakdown",
    "late raw-material delivery blocking the station",
    "operator absence (no qualified worker available)",
    "emergency maintenance stoppage",
]


def simulate_disruption(scheduled_ops, machines, seed=None, machine=None,
                         window_fraction=0.35):
    """
    Pick a machine and a breakdown window that overlaps real work on it.

    The generator prefers busesier machines and anchors the disruption inside a
    credible active window, so it typically affects at least one real operation
    instead of a random idle slice.
    """
    rng = random.Random(seed)

    by_machine = {}
    for so in scheduled_ops:
        by_machine.setdefault(so.machine, []).append(so)

    candidates = [m for m in machines if by_machine.get(m)]
    if machine is None:
        # Prefer the heaviest-loaded machine to make the impact meaningful.
        machine = max(candidates, key=lambda m: (
            sum(op.duration for op in by_machine[m]),
            len(by_machine[m]),
            -m,
            rng.random(),
        ))

    ops_on_machine = sorted(by_machine[machine], key=lambda o: o.start)
    if not ops_on_machine:
        raise ValueError(f"No scheduled operations found for machine M{machine}")

    # Use a non-trivial anchor in the middle of the machine's active window.
    # This avoids degenerately picking the very first operation when a later
    # machine bottleneck is a more realistic disruption point.
    start_candidates = ops_on_machine[1:] if len(ops_on_machine) > 1 else ops_on_machine
    anchor = max(
        start_candidates,
        key=lambda op: (op.duration, op.start, rng.random()),
    )

    # Bias the disruption window toward the anchor's busy period while still
    # allowing slight randomness around it.
    jitter = rng.randint(-2, 4)
    start = max(0, anchor.start + jitter)
    next_op = None
    for op in ops_on_machine:
        if op.start >= anchor.start and op is not anchor:
            next_op = op
            break
    tied_duration = next_op.duration if next_op is not None else anchor.duration
    span = max(
        8,
        int((anchor.duration + tied_duration) * (0.65 + window_fraction))
        + rng.randint(0, 12),
    )
    latest_end = max(op.end for op in ops_on_machine)
    end = min(latest_end, start + span)
    if end <= start:
        end = min(latest_end, start + 8)

    reason = rng.choice(REASONS)
    return Disruption(machine=machine, start=start, end=end, reason=reason)


if __name__ == "__main__":
    from dataset import generate_instance
    from scheduler import solve_schedule

    machines, jobs = generate_instance()
    makespan, scheduled_ops, status = solve_schedule(jobs, machines)
    print(f"Baseline makespan: {makespan}")

    for seed in [1, 2, 3]:
        d = simulate_disruption(scheduled_ops, machines, seed=seed)
        print(f"[seed={seed}] {d}")
