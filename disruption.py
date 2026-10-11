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

    Args:
        scheduled_ops: the baseline ScheduledOp list (used to find a busy
            window so the disruption actually bites).
        machines: list of machine ids to choose from.
        seed: RNG seed for reproducibility across demo runs.
        machine: force a specific machine id (else picked randomly).
        window_fraction: how much of the chosen op's duration (min) plus some
            extra randomness the breakdown window should span, so it usually
            clips 1-3 operations rather than the whole schedule.

    Returns:
        Disruption
    """
    rng = random.Random(seed)

    by_machine = {}
    for so in scheduled_ops:
        by_machine.setdefault(so.machine, []).append(so)

    if machine is None:
        candidates = [m for m in machines if by_machine.get(m)]
        machine = rng.choice(candidates)

    ops_on_machine = sorted(by_machine[machine], key=lambda o: o.start)
    # avoid picking the very first op (nothing to disrupt yet) when possible
    pick_from = ops_on_machine[1:] if len(ops_on_machine) > 1 else ops_on_machine
    anchor = rng.choice(pick_from)

    # breakdown starts a bit before/at the anchor op's start, lasts long
    # enough to swallow the anchor op and often the next one too.
    jitter = rng.randint(-2, 2)
    start = max(0, anchor.start + jitter)
    span = max(6, int(anchor.duration * (1 + window_fraction)) + rng.randint(0, 10))
    end = start + span

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
