"""
================================================================================
AI-BASED ADAPTIVE PRODUCTION SCHEDULER — main demo script
SPARKTANK 2026, Problem Statement 005.3 — Intelligent Production Planning
================================================================================

Pipeline (matches the 4-stage architecture):
  1. Production State   -> dataset.py       (machines, jobs, operations)
  2. Optimization Layer  -> scheduler.py     (CP-SAT baseline "before" schedule)
     [Predictive Layer is the documented stretch goal -- see README]
  3. Disruption + Adaptive Reschedule
                          -> disruption.py, rescheduler.py (CP-SAT "after" schedule)
  4. Explainability       -> explain.py      (plain-language diff)
                          -> gantt.py        (optional CLI PNG visualization)

Run:  python3 main.py                 (uses the curated demo seed)
      python3 main.py --seed 3        (try a different disruption scenario)
      python3 main.py --machine 2     (force a specific machine to break)

Designed to run in well under 30 seconds end-to-end (CP-SAT solves in
milliseconds on an instance this size), so it's safe to run live on stage.
"""

import argparse
import time

from dataset import generate_instance, instance_summary
from scheduler import solve_schedule, validate_schedule
from disruption import simulate_disruption
from rescheduler import reschedule
from explain import diff_schedules, generate_explanation
from gantt import plot_before_after


def run_demo(seed=5, machine=None, instance_seed=42, out_path="gantt_before_after.png",
             num_machines=6, num_jobs=18):
    t_start = time.time()

    # ---- Stage 1: Production State ----
    print("Stage 1/4: Building production state (machines, jobs, materials queue)...")
    machines, jobs = generate_instance(
        num_machines=num_machines,
        num_jobs=num_jobs,
        seed=instance_seed,
    )
    print(instance_summary(machines, jobs))
    print()

    # ---- Stage 2: Optimization Layer (baseline) ----
    print("Stage 2/4: Solving baseline schedule with OR-Tools CP-SAT...")
    t0 = time.time()
    base_makespan, base_ops, base_status = solve_schedule(jobs, machines)
    validate_schedule(base_ops, {j.job_id: j for j in jobs})
    print(f"  status={base_status}  makespan={base_makespan}  "
          f"solve_time={time.time()-t0:.3f}s  [validated OK]")
    print()

    # ---- Stage 3: Disruption + Adaptive Reschedule ----
    print("Stage 3/4: Simulating a real-time disruption...")
    disruption = simulate_disruption(base_ops, machines, seed=seed, machine=machine)
    print(f"  {disruption}")

    print("Re-optimizing with CP-SAT (unfinished operations + machine-down constraint)...")
    t0 = time.time()
    result = reschedule(jobs, machines, base_ops, disruption)
    print(f"  status={result.status}  new_makespan={result.makespan}  "
          f"solve_time={time.time()-t0:.3f}s  [validated OK]")
    print(f"  frozen (already completed) ops: {result.frozen_count}  |  "
          f"re-optimized ops: {result.reoptimized_count}")
    print()

    # ---- Stage 4: Explainability ----
    print("Stage 4/4: Generating explanation and schedule visualization...")
    diffs = diff_schedules(base_ops, result.scheduled_ops)
    explanation = generate_explanation(disruption, base_makespan, result.makespan, diffs)
    print()
    print(explanation)

    path = None
    if out_path is not None:
        path = plot_before_after(base_ops, result.scheduled_ops, machines,
                                  base_makespan, result.makespan, disruption,
                                  out_path=out_path)
        print(f"\nGantt chart saved to: {path}")
    else:
        print("\nStatic Gantt chart skipped (live dashboard mode).")

    total_elapsed = time.time() - t_start
    print(f"\nTOTAL PIPELINE TIME: {total_elapsed:.2f}s")
    assert total_elapsed < 30, "Pipeline exceeded 30s demo budget!"

    return {
        "machines": machines, "jobs": jobs,
        "base_makespan": base_makespan, "base_ops": base_ops,
        "disruption": disruption, "result": result,
        "diffs": diffs, "explanation": explanation,
        "gantt_path": path, "elapsed": total_elapsed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adaptive Production Scheduler demo")
    parser.add_argument("--seed", type=int, default=5,
                         help="Disruption RNG seed (which machine/window gets picked)")
    parser.add_argument("--machine", type=int, default=None,
                         help="Force a specific machine id to break down")
    parser.add_argument("--instance-seed", type=int, default=42,
                         help="Dataset generation seed")
    parser.add_argument("--out", type=str, default="gantt_before_after.png",
                         help="Output path for the Gantt chart PNG")
    args = parser.parse_args()

    run_demo(seed=args.seed, machine=args.machine,
              instance_seed=args.instance_seed, out_path=args.out)
