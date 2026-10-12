"""
Step 5: Explainability log.

Diffs the baseline ("before") schedule against the adaptive ("after")
schedule and turns the diff into a plain-language summary a shop-floor
manager (not an optimization expert) could read and trust:

  - which machine went down, when, and why
  - how the overall makespan changed
  - which jobs got reassigned/delayed as a DIRECT result, and by how much
  - which jobs were completely unaffected (important to say explicitly --
    shows the system isn't needlessly churning the whole plan)
"""


def diff_schedules(before_ops, after_ops):
    """
    Returns a dict job_id -> {
        'before_start', 'before_end', 'after_start', 'after_end', 'delta',
        'machine_changed': bool, 'shifted_ops': [...], 'replanned': bool
    }
    """
    before_by_job = {}
    after_by_job = {}
    for so in before_ops:
        before_by_job.setdefault(so.job_id, []).append(so)
    for so in after_ops:
        after_by_job.setdefault(so.job_id, []).append(so)

    diffs = {}
    for job_id in before_by_job:
        b_ops = sorted(before_by_job[job_id], key=lambda o: o.op_index)
        a_ops = sorted(after_by_job[job_id], key=lambda o: o.op_index)

        b_end = b_ops[-1].end
        a_end = a_ops[-1].end

        machine_changed = any(
            b.machine != a.machine for b, a in zip(b_ops, a_ops)
        )
        shifted_ops = [
            (a.op_index, b.start, a.start) for b, a in zip(b_ops, a_ops)
            if b.start != a.start
        ]

        diffs[job_id] = {
            "job_name": b_ops[0].job_name,
            "before_end": b_end,
            "after_end": a_end,
            "delta": a_end - b_end,
            "machine_changed": machine_changed,
            "shifted_ops": shifted_ops,
            "replanned": bool(shifted_ops),
        }
    return diffs


def generate_explanation(disruption, before_makespan, after_makespan, diffs):
    """
    Build the plain-language explanation string printed/logged after a
    reschedule. The summary emphasizes the actual business impact instead of a
    raw matrix dump.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("ADAPTIVE RESCHEDULE — EXPLANATION LOG")
    lines.append("=" * 70)
    lines.append(f"Disruption detected: Machine M{disruption.machine} became "
                  f"unavailable from t={disruption.start} to t={disruption.end} "
                  f"({disruption.end - disruption.start} time units).")
    lines.append(f"Reason: {disruption.reason}.")
    lines.append("")

    makespan_delta = after_makespan - before_makespan
    if makespan_delta <= 0:
        lines.append(f"Result: the plan absorbed this disruption with NO increase "
                      f"in overall completion time (makespan stayed at {after_makespan}).")
    else:
        lines.append(f"Result: overall completion time (makespan) increased from "
                      f"{before_makespan} to {after_makespan} (+{makespan_delta} time units).")

    delayed = {jid: d for jid, d in diffs.items() if d["delta"] > 0}
    reassigned = {jid: d for jid, d in diffs.items() if d["machine_changed"]}
    unaffected = {jid: d for jid, d in diffs.items()
                  if d["delta"] == 0 and not d["shifted_ops"]}
    replan_count = sum(1 for d in diffs.values() if d["replanned"])
    worst_job = max(delayed.items(), key=lambda item: item[1]["delta"], default=None)

    if worst_job is not None:
        jid, d = worst_job
        lines.append(
            f"Critical impact: Job {jid} ({d['job_name']}) absorbed the largest delay, "
            f"finishing {d['delta']} units later than the original plan."
        )
    lines.append(
        f"Recovery signal: {replan_count} jobs were re-timed, {len(delayed)} were delayed, "
        f"and {len(unaffected)} were completely unaffected."
    )
    lines.append("")

    lines.append(f"Jobs delayed: {len(delayed)} / {len(diffs)}")
    for jid, d in sorted(delayed.items(), key=lambda kv: -kv[1]["delta"]):
        lines.append(f"  - Job {jid} ({d['job_name']}): finishes {d['delta']} "
                      f"units later (was t={d['before_end']}, now t={d['after_end']})")

    if reassigned:
        lines.append("")
        lines.append(f"Jobs with at least one operation moved to a different machine: "
                      f"{len(reassigned)}")
        for jid, d in sorted(reassigned.items()):
            lines.append(f"  - Job {jid} ({d['job_name']}): re-routed to keep the plan "
                          f"on schedule")

    lines.append("")
    lines.append(f"Jobs completely unaffected: {len(unaffected)} / {len(diffs)} "
                  f"(their timing didn't need to change at all).")
    lines.append("=" * 70)

    return "\n".join(lines)


if __name__ == "__main__":
    from dataset import generate_instance
    from scheduler import solve_schedule
    from disruption import simulate_disruption
    from rescheduler import reschedule

    machines, jobs = generate_instance()
    base_makespan, base_ops, _ = solve_schedule(jobs, machines)
    d = simulate_disruption(base_ops, machines, seed=5)
    result = reschedule(jobs, machines, base_ops, d)

    diffs = diff_schedules(base_ops, result.scheduled_ops)
    print(generate_explanation(d, base_makespan, result.makespan, diffs))
