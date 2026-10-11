"""
Step 1: Dataset generator for the Adaptive Production Scheduler.

We generate a synthetic job-shop scheduling (JSSP) instance instead of using a
raw Taillard file, because:
  - Taillard instances only give (machine, duration) pairs with no semantic
    meaning (no job names, no "materials/workforce" story) which makes the
    demo/explainability layer harder to narrate.
  - A synthetic generator lets us control size (5-8 machines, 15-20 jobs) and
    reproduce that data using its own generator can be shown to judges as
    "this scales to real factory data" story.

Each job is a sequence of operations. Each operation is (machine_id, duration).
Operations within a job MUST run in that order (precedence constraint).
A job's operations don't all have to touch every machine (routing flexibility),
matching real production lines more than a rigid Taillard square matrix.
"""

import random
from dataclasses import dataclass, field


@dataclass
class Operation:
    job_id: int
    op_index: int          # position within the job's sequence (precedence order)
    machine: int
    duration: int


@dataclass
class Job:
    job_id: int
    name: str
    operations: list = field(default_factory=list)  # list[Operation], in precedence order


def generate_instance(num_machines=6, num_jobs=18, min_ops=3, max_ops=6,
                       min_dur=4, max_dur=18, seed=42):
    """
    Generate a synthetic job-shop instance.

    Returns:
        machines: list[int]  machine ids 0..num_machines-1
        jobs: list[Job]
    """
    rng = random.Random(seed)
    machines = list(range(num_machines))
    jobs = []

    product_names = [
        "Widget", "Bracket", "Housing", "Gear", "Panel", "Valve", "Piston",
        "Frame", "Rotor", "Sensor-Mount", "Casing", "Flange", "Shaft",
        "Coupler", "Bearing", "Manifold", "Bracket-XL", "Enclosure", "Hinge",
        "Spindle"
    ]

    for j in range(num_jobs):
        n_ops = rng.randint(min_ops, max_ops)
        # each job visits a random subset/order of machines (no machine used
        # twice in a row, mimicking real routings where you don't revisit the
        # same station consecutively)
        seq_machines = []
        last = None
        for _ in range(n_ops):
            choices = [m for m in machines if m != last]
            m = rng.choice(choices)
            seq_machines.append(m)
            last = m

        ops = []
        for idx, m in enumerate(seq_machines):
            dur = rng.randint(min_dur, max_dur)
            ops.append(Operation(job_id=j, op_index=idx, machine=m, duration=dur))

        name = product_names[j % len(product_names)]
        suffix = f"-{j // len(product_names)}" if j >= len(product_names) else ""
        jobs.append(Job(job_id=j, name=f"{name}{suffix}", operations=ops))

    return machines, jobs


def instance_summary(machines, jobs):
    total_ops = sum(len(j.operations) for j in jobs)
    total_work = sum(op.duration for j in jobs for op in j.operations)
    lines = [
        f"Machines: {len(machines)}",
        f"Jobs: {len(jobs)}",
        f"Total operations: {total_ops}",
        f"Total processing time (sum of all durations): {total_work}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    machines, jobs = generate_instance()
    print(instance_summary(machines, jobs))
    print()
    for j in jobs[:3]:
        seq = " -> ".join(f"M{op.machine}({op.duration})" for op in j.operations)
        print(f"Job {j.job_id} ({j.name}): {seq}")
