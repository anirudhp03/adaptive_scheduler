"""Streamlit dashboard for the adaptive production scheduler."""

import json

import streamlit as st
import streamlit.components.v1 as components

from main import run_demo


def _live_timeline_html(schedule_result):
    """Build an interactive SVG timeline that replays the adaptive schedule."""
    tasks = schedule_result["tasks"]
    payload = {
        "tasks": tasks,
        "machines": schedule_result["machines"],
        "makespan": schedule_result["makespan"],
        "disruption": schedule_result["disruption"],
    }
    data = json.dumps(payload).replace("<", "\\u003c")
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; color: #e7edf7; background: #101827;
         font: 14px/1.45 system-ui, sans-serif; }}
  .panel {{ padding: 18px; border: 1px solid #28364b; border-radius: 14px;
            background: linear-gradient(145deg, #172337, #111a29); }}
  .heading {{ display: flex; justify-content: space-between; gap: 16px;
              align-items: flex-start; flex-wrap: wrap; }}
  h2 {{ margin: 0; font-size: 18px; }}
  #status {{ margin-top: 4px; color: #aebbd0; }}
  #clock {{ color: #fff; font: 700 20px ui-monospace, monospace; }}
  .controls {{ display: flex; gap: 9px; align-items: center;
               flex-wrap: wrap; margin: 14px 0 8px; }}
  button {{ padding: 8px 14px; color: #eef4ff; border: 1px solid #40516b;
            border-radius: 8px; background: #22344d; cursor: pointer; }}
  button.primary {{ background: #147d69; border-color: #20a58b; }}
  button:hover {{ filter: brightness(1.15); }}
  select {{ padding: 8px; color: #eef4ff; background: #1a293d;
            border: 1px solid #40516b; border-radius: 8px; }}
  #scrubber {{ width: 100%; accent-color: #42d6b2; }}
  .timeline-labels {{ display:flex; justify-content:space-between;
                      color:#8f9db2; font-size:12px; margin-top:-3px; }}
  .chart-wrap {{ overflow-x: auto; margin-top: 12px;
                 border: 1px solid #28364b; border-radius: 9px;
                 background: #111b2a; }}
  svg {{ display:block; min-width: 760px; width:100%; }}
  .lane {{ fill:#182539; }}
  .lane.alt {{ fill:#1b2a3f; }}
  .machine-label {{ fill:#d5e0f0; font-size:13px; font-weight:650; }}
  .axis-label {{ fill:#8999af; font-size:11px; }}
  .task {{ stroke:#0c1420; stroke-width:1; }}
  .task-label {{ fill:#101827; font-size:10px; font-weight:700;
                 pointer-events:none; }}
  .down-window {{ fill:#ef4444; fill-opacity:.16; stroke:#fb7185;
                  stroke-width:1.5; stroke-dasharray:5 4; }}
  .down-label {{ fill:#fda4af; font-size:10px; font-weight:700; }}
  .playhead {{ stroke:#f4f7ff; stroke-width:2; stroke-dasharray:4 3;
               pointer-events:none; }}
  .playhead-dot {{ fill:#f4f7ff; stroke:#101827; stroke-width:2; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; color:#b9c5d7;
             font-size:12px; margin-top:12px; }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%;
          margin-right:5px; }}
  .note {{ color:#8999af; font-size:12px; margin:10px 0 0; }}
  @media (max-width: 650px) {{ .panel {{ padding:12px; }} }}
</style>
</head>
<body>
<div class="panel">
  <div class="heading">
    <div>
      <h2>Live production replay</h2>
      <div id="status">Baseline plan · ready to start</div>
    </div>
    <div id="clock">t = 0</div>
  </div>
  <div class="controls">
    <button id="play" class="primary" type="button">▶ Play</button>
    <button id="restart" type="button">↺ Restart</button>
    <label for="speed">Playback</label>
    <select id="speed" aria-label="Playback speed">
      <option value="12">0.5×</option>
      <option value="24" selected>1×</option>
      <option value="48">2×</option>
      <option value="96">4×</option>
    </select>
  </div>
  <input id="scrubber" type="range" min="0" value="0" step="0.1"
         aria-label="Production time">
  <div class="timeline-labels"><span>Start of shift</span><span id="end-label"></span></div>
  <div class="chart-wrap"><svg id="timeline" role="img"
      aria-label="Animated production schedule by machine"></svg></div>
  <div class="legend">
    <span><i class="dot" style="background:#33d6a6"></i>In progress</span>
    <span><i class="dot" style="background:#73839b"></i>Queued</span>
    <span><i class="dot" style="background:#f87171"></i>Machine disruption</span>
  </div>
  <p class="note">The solver computes the recovery plan when you run the scenario.
  Playback shows production up to the disruption, then animates unfinished work
  into its new slots and continues on the recovered plan.</p>
</div>
<script>
(() => {{
const data = {data};
const svg = document.getElementById("timeline");
const scrubber = document.getElementById("scrubber");
const clock = document.getElementById("clock");
const status = document.getElementById("status");
const playButton = document.getElementById("play");
const duration = data.makespan;
const disruption = data.disruption;
const width = 1200, left = 78, right = 20, chartTop = 50, rowHeight = 43;
const chartWidth = width - left - right;
const height = chartTop + data.machines.length * rowHeight + 48;
const scale = chartWidth / duration;
const colors = ["#65d6be","#f6bd60","#7aa2f7","#e58de5","#8bd17c",
                "#f28b82","#72c9e8","#d9a0ff","#ffc857","#91c7b1"];
const jobColor = new Map();
let time = 0, playing = false, previous = 0, lastPaint = 0;
let hasAppliedRecovery = false;
const groups = [];
const ns = "http://www.w3.org/2000/svg";

function element(name, attrs, parent=svg) {{
  const node = document.createElementNS(ns, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  parent.appendChild(node);
  return node;
}}
function xAt(t) {{ return left + t * scale; }}
function setStatus(text) {{ status.textContent = text; }}

svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
svg.setAttribute("height", height);
scrubber.max = duration;
document.getElementById("end-label").textContent = `Makespan ${{duration}}`;

for (let row = 0; row < data.machines.length; row++) {{
  const machine = data.machines[row];
  const y = chartTop + row * rowHeight;
  element("rect", {{x:left, y:y-15, width:chartWidth, height:rowHeight-2,
                    class: row % 2 ? "lane alt" : "lane"}});
  element("text", {{x:left-12, y:y+6, "text-anchor":"end",
                    class:"machine-label"}}).textContent = `M${{machine}}`;
}}

const tickStep = Math.max(10, Math.ceil(duration / 8 / 10) * 10);
for (let tick = 0; tick <= duration; tick += tickStep) {{
  const x = xAt(tick);
  element("line", {{x1:x, x2:x, y1:chartTop-12,
                    y2:chartTop + data.machines.length * rowHeight - 10,
                    stroke:"#27364a", "stroke-width":"1"}});
  element("text", {{x:x, y:height-17, "text-anchor":"middle",
                    class:"axis-label"}}).textContent = tick;
}}
element("text", {{x:left+chartWidth/2, y:height-2, "text-anchor":"middle",
                  class:"axis-label"}}).textContent = "Production time";

const outageY = chartTop + data.machines.indexOf(disruption.machine) * rowHeight - 15;
const outage = element("rect", {{
  x:xAt(disruption.start), y:outageY,
  width:Math.max(2, (disruption.end-disruption.start)*scale),
  height:rowHeight-2, class:"down-window"
}});
const outageLabel = element("text", {{
  x:xAt(disruption.start)+4, y:outageY+13, class:"down-label"
}});
outageLabel.textContent = "BREAKDOWN";

for (const task of data.tasks) {{
  if (!jobColor.has(task.job_id))
    jobColor.set(task.job_id, colors[jobColor.size % colors.length]);
  const row = data.machines.indexOf(task.machine);
  const y = chartTop + row * rowHeight - 12;
  const group = element("g", {{class:"operation"}});
  const rect = element("rect", {{
    x:xAt(task.before_start), y:y, width:Math.max(2, task.duration*scale),
    height:22, rx:4, fill:jobColor.get(task.job_id), class:"task",
    "data-state":""
  }}, group);
  const label = element("text", {{
    x:xAt(task.before_start)+4, y:y+15, class:"task-label"
  }}, group);
  label.textContent = task.duration*scale >= 37
    ? `J${{task.job_id}} · O${{task.op_index+1}}` : "";
  const tooltip = element("title", {{}}, group);
  tooltip.textContent = `${{task.job_name}} · operation ${{task.op_index+1}} · ` +
    `M${{task.machine}} · ${{task.duration}} time units`;
  groups.push({{task, group, rect, label}});
}}

const playhead = element("line", {{y1:chartTop-20,
  y2:chartTop + data.machines.length*rowHeight - 10, class:"playhead"}});
const playheadDot = element("circle", {{cy:chartTop-20, r:5, class:"playhead-dot"}});

function applyRecovery() {{
  if (hasAppliedRecovery) return;
  hasAppliedRecovery = true;
  for (const item of groups) {{
    const x = xAt(item.task.after_start);
    item.rect.style.transition = "x 750ms cubic-bezier(.2,.75,.25,1)";
    item.label.style.transition = "x 750ms cubic-bezier(.2,.75,.25,1)";
    item.rect.style.setProperty("x", `${{x}}px`);
    item.label.style.setProperty("x", `${{x+4}}px`);
  }}
}}

function paint(now) {{
  const recovered = time >= disruption.start;
  if (recovered) applyRecovery();
  const currentX = xAt(time);
  playhead.setAttribute("x1", currentX);
  playhead.setAttribute("x2", currentX);
  playheadDot.setAttribute("cx", currentX);
  clock.textContent = `t = ${{time.toFixed(1)}}`;
  scrubber.value = time;
  outage.setAttribute("fill-opacity", recovered ? ".38" : ".12");
  outageLabel.textContent = recovered ? "MACHINE DOWN" : "PLANNED DISRUPTION";

  for (const item of groups) {{
    const task = item.task;
    const start = recovered ? task.after_start : task.before_start;
    const end = start + task.duration;
    const state = time >= end ? "done" : time >= start ? "active" : "queued";
    if (item.rect.getAttribute("data-state") !== state) {{
      item.rect.setAttribute("data-state", state);
      item.rect.style.opacity = state === "active" ? "1" :
        state === "done" ? ".88" : ".4";
      item.rect.style.stroke = state === "active" ? "#ffffff" : "#0c1420";
      item.rect.style.strokeWidth = state === "active" ? "2" : "1";
    }}
  }}

  if (!recovered) {{
    setStatus("Baseline plan · running production");
  }} else if (time < disruption.end) {{
    setStatus(`M${{disruption.machine}} disruption · recovery plan applied`);
  }} else if (time >= duration) {{
    setStatus("Recovery complete · all scheduled operations finished");
  }} else {{
    setStatus("Adaptive plan · production resumed");
  }}
}}

function resetReplay() {{
  playing = false;
  time = 0;
  previous = 0;
  hasAppliedRecovery = false;
  playButton.textContent = "▶ Play";
  for (const item of groups) {{
    item.rect.style.transition = "none";
    item.label.style.transition = "none";
    item.rect.style.setProperty("x", `${{xAt(item.task.before_start)}}px`);
    item.label.style.setProperty("x", `${{xAt(item.task.before_start)+4}}px`);
    item.rect.setAttribute("data-state", "");
  }}
  paint(performance.now());
}}

function frame(now) {{
  if (!playing) return;
  if (!previous) previous = now;
  const elapsed = Math.min(100, now - previous);
  previous = now;
  const rate = Number(document.getElementById("speed").value);
  time = Math.min(duration, time + elapsed * rate / 1000);
  if (now - lastPaint >= 40 || time === duration) {{
    paint(now);
    lastPaint = now;
  }}
  if (time >= duration) {{
    playing = false;
    playButton.textContent = "▶ Play";
    return;
  }}
  requestAnimationFrame(frame);
}}

playButton.addEventListener("click", () => {{
  if (playing) {{
    playing = false;
    playButton.textContent = "▶ Play";
    setStatus("Paused · use the timeline slider to seek");
    return;
  }}
  if (time >= duration) resetReplay();
  playing = true;
  previous = 0;
  playButton.textContent = "Ⅱ Pause";
  requestAnimationFrame(frame);
}});
document.getElementById("restart").addEventListener("click", resetReplay);
scrubber.addEventListener("input", () => {{
  time = Number(scrubber.value);
  if (time < disruption.start && hasAppliedRecovery) {{
    hasAppliedRecovery = false;
    for (const item of groups) {{
      const x = xAt(item.task.before_start);
      item.rect.style.transition = "x 500ms ease";
      item.label.style.transition = "x 500ms ease";
      item.rect.style.setProperty("x", `${{x}}px`);
      item.label.style.setProperty("x", `${{x+4}}px`);
    }}
  }}
  paint(performance.now());
}});
paint(performance.now());
}})();
</script>
</body>
</html>"""


st.set_page_config(
    page_title="Adaptive Production Scheduler",
    page_icon="🏭",
    layout="wide",
)

st.title("Adaptive Production Scheduler")
st.caption(
    "Explore a production plan, introduce a machine disruption, "
    "and watch the recovery plan take effect."
)

with st.sidebar:
    st.header("Scenario")
    num_machines = st.slider("Machines", min_value=3, max_value=8, value=6)
    num_jobs = st.slider("Jobs", min_value=5, max_value=30, value=18)
    instance_seed = st.number_input(
        "Production instance seed", min_value=0, max_value=999_999, value=42
    )
    disruption_seed = st.number_input(
        "Disruption seed", min_value=0, max_value=999_999, value=5
    )

    machine_options = [None, *range(num_machines)]
    selected_machine = st.selectbox(
        "Machine to disrupt",
        options=machine_options,
        format_func=lambda machine: (
            "Random machine" if machine is None else f"M{machine}"
        ),
    )

    run_schedule = st.button(
        "Run adaptive schedule", type="primary", use_container_width=True
    )

if run_schedule:
    with st.spinner("Solving baseline and adaptive production plans..."):
        result = run_demo(
            seed=int(disruption_seed),
            machine=selected_machine,
            instance_seed=int(instance_seed),
            out_path=None,
            num_machines=num_machines,
            num_jobs=num_jobs,
        )

    before_by_key = {
        (op.job_id, op.op_index): op for op in result["base_ops"]
    }
    schedule_rows = []
    tasks = []
    for after in sorted(
        result["result"].scheduled_ops,
        key=lambda op: (op.start, op.machine, op.job_id, op.op_index),
    ):
        before = before_by_key[(after.job_id, after.op_index)]
        schedule_rows.append(
            {
                "Job": f"{after.job_name} (J{after.job_id})",
                "Operation": after.op_index + 1,
                "Machine": f"M{after.machine}",
                "Duration": after.duration,
                "Before start": before.start,
                "Before end": before.end,
                "After start": after.start,
                "After end": after.end,
            }
        )
        tasks.append(
            {
                "job_id": after.job_id,
                "job_name": after.job_name,
                "op_index": after.op_index,
                "machine": after.machine,
                "duration": after.duration,
                "before_start": before.start,
                "after_start": after.start,
            }
        )

    st.session_state["schedule_result"] = {
        "makespan": result["result"].makespan,
        "base_makespan": result["base_makespan"],
        "machines": result["machines"],
        "disruption": {
            "machine": result["disruption"].machine,
            "start": result["disruption"].start,
            "end": result["disruption"].end,
        },
        "explanation": result["explanation"],
        "diffs": result["diffs"],
        "schedule_rows": schedule_rows,
        "tasks": tasks,
        "frozen_count": result["result"].frozen_count,
        "reoptimized_count": result["result"].reoptimized_count,
        "machine_count": len(result["machines"]),
        "job_count": len(result["jobs"]),
    }

schedule_result = st.session_state.get("schedule_result")
if schedule_result:
    delta = schedule_result["makespan"] - schedule_result["base_makespan"]
    delayed_jobs = sum(
        job["delta"] > 0 for job in schedule_result["diffs"].values()
    )

    st.subheader("Schedule overview")
    disruption = schedule_result["disruption"]
    st.caption(
        f"Machine M{disruption['machine']} disruption at t={disruption['start']} "
        f"through t={disruption['end']}"
    )
    metric_columns = st.columns(5)
    metric_columns[0].metric("Jobs", schedule_result["job_count"])
    metric_columns[1].metric("Machines", schedule_result["machine_count"])
    metric_columns[2].metric("Before makespan", schedule_result["base_makespan"])
    metric_columns[3].metric(
        "After makespan",
        schedule_result["makespan"],
        delta=f"{delta:+} time units",
        delta_color="inverse",
    )
    metric_columns[4].metric("Jobs delayed", delayed_jobs)

    components.html(_live_timeline_html(schedule_result), height=690, scrolling=True)

    with st.expander("Schedule details"):
        st.dataframe(
            schedule_result["schedule_rows"],
            hide_index=True,
            use_container_width=True,
        )

    with st.expander("Why did the schedule change?"):
        st.text(schedule_result["explanation"])
        st.caption(
            f"Frozen completed operations: {schedule_result['frozen_count']} · "
            f"Re-optimized operations: {schedule_result['reoptimized_count']}"
        )
else:
    st.info(
        "Choose a scenario in the sidebar and select **Run adaptive schedule** "
        "to create and replay its recovery plan."
    )
