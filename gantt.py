"""
Step 6: Before/after Gantt charts using matplotlib's broken_barh.

One row per machine, one bar per operation, colored by job. Two subplots
side-by-side (baseline vs adaptive) sharing the same x-axis scale so the
"recovery" is visually obvious: the disrupted machine's row shows a gap
(hatched red block) in the "after" chart, and any shifted bars are easy to
compare against the "before" chart directly above/below it.
"""

import matplotlib
matplotlib.use("Agg")  # headless-safe backend for saving PNGs in the container
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def _job_color_map(all_ops):
    job_ids = sorted({so.job_id for so in all_ops})
    cmap = plt.get_cmap("tab20")
    return {jid: cmap(i % 20) for i, jid in enumerate(job_ids)}


def _draw_panel(ax, scheduled_ops, machines, color_map, title, makespan,
                 xlim_max, disruption=None):
    machine_rows = {m: i for i, m in enumerate(machines)}
    bar_height = 0.8

    by_machine = {}
    for so in scheduled_ops:
        by_machine.setdefault(so.machine, []).append(so)

    for m in machines:
        row = machine_rows[m]
        ops = sorted(by_machine.get(m, []), key=lambda o: o.start)
        spans = [(so.start, so.end - so.start) for so in ops]
        colors = [color_map[so.job_id] for so in ops]
        # broken_barh doesn't take per-bar colors directly across versions,
        # so draw one call per contiguous color run (simplest: one call per op).
        for so in ops:
            ax.broken_barh([(so.start, so.end - so.start)], (row, bar_height),
                            facecolors=color_map[so.job_id], edgecolors="black",
                            linewidth=0.4)
            # label small ops with job id if there's room
            if so.end - so.start >= max(4, makespan * 0.02):
                ax.text(so.start + (so.end - so.start) / 2, row + bar_height / 2,
                        f"J{so.job_id}", ha="center", va="center", fontsize=6,
                        color="black")

    if disruption is not None:
        row = machine_rows.get(disruption.machine)
        if row is not None:
            ax.broken_barh([(disruption.start, disruption.end - disruption.start)],
                            (row, bar_height), facecolors="none", edgecolor="red",
                            hatch="////", linewidth=1.5, zorder=5)
            ax.text(disruption.start, row + bar_height + 0.15, "MACHINE DOWN",
                     fontsize=7, color="red", fontweight="bold")

    ax.set_yticks([machine_rows[m] + bar_height / 2 for m in machines])
    ax.set_yticklabels([f"M{m}" for m in machines])
    ax.set_xlabel("Time")
    ax.set_xlim(0, xlim_max * 1.05)
    ax.axvline(makespan, color="black", linestyle="--", linewidth=1)
    ax.text(makespan, len(machines) - 0.2, f" makespan={makespan}",
            fontsize=9, fontweight="bold", va="top")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(axis="x", linestyle=":", alpha=0.4)


def plot_before_after(before_ops, after_ops, machines, before_makespan,
                       after_makespan, disruption, out_path="gantt_before_after.png"):
    all_ops = before_ops + after_ops
    color_map = _job_color_map(all_ops)

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    xlim_max = max(before_makespan, after_makespan)

    _draw_panel(axes[0], before_ops, machines, color_map,
                title="BEFORE — Baseline schedule (no disruption)",
                makespan=before_makespan, xlim_max=xlim_max)

    _draw_panel(axes[1], after_ops, machines, color_map,
                title="AFTER — Adaptive reschedule (post-disruption)",
                makespan=after_makespan, xlim_max=xlim_max,
                disruption=disruption)

    delta = after_makespan - before_makespan
    delta_str = f"+{delta}" if delta > 0 else str(delta)
    fig.suptitle(
        f"Disruption: M{disruption.machine} down [{disruption.start}-{disruption.end}]   |   "
        f"Makespan: {before_makespan} -> {after_makespan}  ({delta_str} time units)",
        fontsize=13, fontweight="bold")

    # Legend of job colors (compact, outside plot area)
    job_ids = sorted(color_map.keys())
    handles = [Patch(facecolor=color_map[j], edgecolor="black", label=f"Job {j}")
               for j in job_ids]
    fig.legend(handles=handles, loc="lower center", ncol=min(9, len(job_ids)),
               fontsize=7, bbox_to_anchor=(0.5, -0.02))

    fig.tight_layout(rect=[0, 0.05, 1, 0.96])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    from dataset import generate_instance
    from scheduler import solve_schedule
    from disruption import simulate_disruption
    from rescheduler import reschedule

    machines, jobs = generate_instance()
    base_makespan, base_ops, _ = solve_schedule(jobs, machines)
    d = simulate_disruption(base_ops, machines, seed=5)
    result = reschedule(jobs, machines, base_ops, d)

    path = plot_before_after(base_ops, result.scheduled_ops, machines,
                              base_makespan, result.makespan, d,
                              out_path="/home/claude/scheduler/test_gantt.png")
    print(f"Saved: {path}")
