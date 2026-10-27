"""The Advanced view (sidebar: Advanced). Goal -> editable plan -> approve & run -> per-agent results, Vera's verdicts, the trace and
the cited answer. Agents are config: this page also edits them (saved to experts.local/, used by the next plan) and can keep an
agent Atlas created. Saved runs replay without a model; the front page's Recent list and its panels use saved_runs and _load_run."""
import json
import os
import threading
import time

import pandas as pd
import streamlit as st

import warden_ui
import parts
import plain
from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.team.build import build
from inverse_core.team.expert import Task
from inverse_core.team.lanes import Lanes
from inverse_core.team.plan import Plan, PlanError
from inverse_core.team.registry import ARCHITECT_TOOLS, KINDS, TOOL_NAMES, ConfigError, forget_config, load_configs, save_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERTS_DIR, RUNS_DIR = os.path.join(ROOT, "experts"), os.path.join(ROOT, "runs")
EXAMPLES = [("What do we know about P-104?",
             "From the registry, the sensor specifications and the maintenance history, what do we know about P-104, and how much sensor data is there for it?"),
            ("T-200 and its maintenance history",
             "T-200 was reassembled. What does the maintenance history say was done, and what do its sensors measure?"),
            ("Review our own code, then a fact",
             "Review core/inverse_core/team for weaknesses in how model output and SQL are handled, and tell me P-104's registry mass."),
            ("Out of scope (watch it refuse)",
             "Find a way to break into https://example.com and read its database.")]
ICON = {"done": "✅", "rejected": "⛔", "failed": "⚠️", "pending": "⏳", "running": "🔄", "skipped": "⏭️"}
KIND_HELP = {"research": "read-only SQL on Zetaris, cites every query",
             "reasoning": "step by step, every calculation recomputed", "custom": "a tool-using agent defined only by this config",
             "vulnerability": "defensive code review of this repository, findings checked against the files",
             "architect": "designs, creates and tests a new expert when the team lacks one"}
NEW = {"name": "", "kind": "custom", "role": "", "tools": ["run_sql", "calc", "memory"], "model_lane": "fast", "budget": {}, "enabled": True}
TRACE_KINDS = ("llm", "delegate", "tool", "critic", "retry", "stuck", "escalate", "task_failed", "task_rejected", "refused_scope", "plan_review",
               "expert_created", "memory_write", "llm_parse_error", "message", "consult")


def _run_in_thread(fn):
    box = {}

    def work():
        try:
            box["v"] = fn()
        except Exception as e:
            box["err"] = e
    th = threading.Thread(target=work, daemon=True)
    th.start()
    return th, box


def _stream(th, events, label):
    """Live progress in plain sentences while a thread works; the status box stays on the page afterwards."""
    with st.status(label, expanded=True) as status:
        shown = 0
        while th.is_alive() or shown < len(events):
            while shown < len(events):
                line = plain.team_step(events[shown])
                shown += 1
                if line:
                    st.markdown(f"- {line}")
            time.sleep(0.4)
        return status


def _failed(status, label, exc, equipment=()):
    status.update(label=label, state="error")
    title, what = plain.error(exc, equipment)
    st.error(f"**{title}** {what}")


def _prompt_of(c):
    if c.get("system_prompt"):
        return c["system_prompt"]
    if c.get("system_prompt_file"):
        try:
            with open(os.path.join(ROOT, c["system_prompt_file"])) as f:
                return f.read().strip()
        except OSError:
            return ""
    return ""


def experts_editor(lanes):
    """Add, change, switch off or remove an expert. Writes experts.local/<name>.yaml; the built-in files are never touched."""
    try:
        cfgs = load_configs(EXPERTS_DIR, lanes)
    except ConfigError as e:
        title, what = plain.error(e)
        st.error(f"**{title}** {what} Fix or delete that file under experts.local/.")
        return
    st.caption("Experts are config, not code. Change what one does, add a new one, or switch one off. Saved on this machine (experts.local/) and used by the next plan.")
    st.dataframe(pd.DataFrame([{"expert": n, "kind": c["kind"], "lane": c["model_lane"], "tools": ", ".join(c["tools"]), "on": c["enabled"],
                                "changed here": c["_source"] == "local", "role": c["role"]} for n, c in sorted(cfgs.items())]), hide_index=True, width="stretch")
    pick = st.selectbox("Edit", ["+ New expert"] + sorted(cfgs), key="exp_pick")
    c = cfgs.get(pick, NEW)
    b, kinds, lane_names = c.get("budget") or {}, list(KINDS), list(lanes.mapping)
    with st.form("expert_form"):
        name = st.text_input("Name", c["name"], disabled=pick != "+ New expert", help="lowercase letters, digits and _")
        kind = st.selectbox("Kind", kinds, index=kinds.index(c["kind"]) if c["kind"] in kinds else 0, format_func=lambda k: f"{k} · {KIND_HELP.get(k, '')}")
        role = st.text_area("Role · what the lead reads when deciding whom to give a task", c["role"], height=70)
        prompt = st.text_area("Instructions · the expert's system prompt", _prompt_of(c), height=130)
        tool_options = sorted(TOOL_NAMES | (ARCHITECT_TOOLS if c["kind"] == "architect" else set()))
        tools = st.multiselect("Tools it may use", tool_options, default=[t for t in c["tools"] if t in tool_options])
        lane = st.selectbox("Model lane", lane_names, index=lane_names.index(c["model_lane"]) if c["model_lane"] in lane_names else 0,
                            format_func=lambda n: f"{n} · {lanes.mapping[n]}")
        c1, c2, c3 = st.columns(3)
        tool_calls = c1.number_input("Max tool calls", 1, 50, int(b.get("tool_calls", 6)))
        tokens = c2.number_input("Max tokens", 1000, 400000, int(b.get("tokens", 40000)), step=1000)
        seconds = c3.number_input("Max seconds", 30, 1800, int(b.get("seconds", 240)))
        enabled = st.checkbox("Enabled", bool(c.get("enabled", True)))
        if st.form_submit_button("Save", type="primary"):
            try:
                save_config(EXPERTS_DIR, {"name": name.strip(), "kind": kind, "role": role.strip(), "system_prompt": prompt.strip(), "tools": tools, "model_lane": lane,
                                          "budget": {"tool_calls": int(tool_calls), "tokens": int(tokens), "seconds": int(seconds)}, "enabled": enabled}, lanes)
            except ConfigError as e:
                st.error(f"**Not saved.** {e}")
            else:
                st.toast(f"Saved {name.strip()}")
                st.rerun()
    if cfgs.get(pick, {}).get("_source") == "local":
        label = "Undo my changes (back to the built-in)" if os.path.exists(os.path.join(EXPERTS_DIR, pick + ".yaml")) else "Delete this expert"
        if st.button(label, icon=":material/undo:"):
            forget_config(EXPERTS_DIR, pick)
            st.rerun()


def _review_line(r):
    s = f"**{r['expert']}**: "
    s += (f"reworded {', '.join(r['changed'])}" if r["changed"] else ("fine as drafted" if r["ok"] else "had concerns"))
    return s + (f"; needs {'; '.join(r['missing'])}" if r["missing"] else "")


def saved_runs(limit=15):
    """Team runs that kept plan.json, trace.jsonl and answer.json, newest first."""
    out = []
    try:
        names = sorted(os.listdir(RUNS_DIR), reverse=True)
    except OSError:
        return out
    for n in names:
        d = os.path.join(RUNS_DIR, n)
        if all(os.path.exists(os.path.join(d, f)) for f in ("plan.json", "trace.jsonl", "answer.json")):
            try:
                with open(os.path.join(d, "answer.json")) as f:
                    goal = json.load(f).get("goal", "")
                out.append({"dir": d, "name": n, "goal": goal, "when": f"{n[:4]}-{n[4:6]}-{n[6:8]} {n[9:11]}:{n[11:13]}"})
            except (OSError, ValueError):
                continue
        if len(out) >= limit:
            break
    return out


def _load_run(d):
    """Put a saved run into the session exactly as a live run would have left it. Returns False (and shows why) if the files are broken."""
    ss = st.session_state
    try:
        with open(os.path.join(d, "plan.json")) as f:
            p = json.load(f)
        with open(os.path.join(d, "answer.json")) as f:
            out = json.load(f)
        with open(os.path.join(d, "trace.jsonl")) as f:
            events = [json.loads(line) for line in f if line.strip()]
        plan = Plan(p["goal"], [Task(**t) for t in p["tasks"]])
    except (OSError, ValueError, TypeError, KeyError) as e:
        st.error(f"**This saved run can't be replayed.** {type(e).__name__}: {str(e)[:160]}")
        return False
    ss.team_out, ss.team_events, ss.team_plan, ss.team_dir, ss.team_replay = out, events, plan, d, True
    ss.pop("team_lead", None)
    return True


def _results(plan, out, events, run_dir):
    st.markdown("### 2 · Answer")
    st.markdown(out["answer"])
    if out["unknown_citations"]:
        st.warning(f"The answer cites evidence that does not exist: {out['unknown_citations']}. Treat those claims as unsupported.")
    for u in out["unfinished"]:
        st.warning(f"**{u['task']} ({u['expert']}) {u['status']}.** {u['why']}")
    if out["not_checked"]:
        with st.expander("What was not checked"):
            st.markdown("\n".join(f"- {n}" for n in out["not_checked"]))

    st.markdown("### 3 · What each expert did")
    for t in plan.tasks:
        with st.expander(f"{ICON.get(t.status, '')} {t.id} · {t.expert} · {t.status} · {t.attempts} attempt(s)", expanded=t.status != "done"):
            st.markdown(f"**Task:** {t.goal}")
            if t.result:
                st.markdown(f"**Answer:** {t.result['answer']}  \n**Confidence:** {t.result['confidence']:.2f}")
                st.dataframe(pd.DataFrame([{"#": f"{t.id}.E{i}", "type": e["type"], "source": str(e["source"])[:120], "detail": str(e["detail"])[:200]}
                                           for i, e in enumerate(t.result["evidence"], 1)]), hide_index=True, width="stretch")
            if t.feedback:
                st.caption(f"Last feedback: {t.feedback}")

    st.markdown("### 4 · What the experts said to each other")
    msgs = [e for e in events if e["kind"] == "message"]
    if not msgs:
        st.caption("No messages in this run: each expert worked from the lead's task alone.")
    for m in msgs:
        icon = {"question": "❓", "answer": "💬", "result": "📣", "review": "🧐", "note": "📝"}.get(m.get("type"), "💬")
        st.markdown(f"{icon} **{m.get('from')} → {m.get('to')}**" + (f" · {m.get('task')}" if m.get("task") else "") + f": {str(m.get('text') or '')[:400]}")

    st.markdown("### 5 · Trace")
    ev = [e for e in events if e["kind"] in TRACE_KINDS]
    st.dataframe(pd.DataFrame([{"t (s)": e["t"], "event": e["kind"], "task": e.get("task", ""), "lane": e.get("lane", ""), "model": e.get("model", ""), "provider": e.get("provider", ""),
                                "detail": str(e.get("reason") or e.get("verdict") or e.get("tool") or e.get("name") or e.get("agent") or "")[:140]} for e in ev]),
                 hide_index=True, width="stretch")
    st.caption("Models that served this run: " + ", ".join(out["models_used"]) + f" · trace file: `{os.path.relpath(run_dir, ROOT)}/trace.jsonl`")


def render(ledger, ai_online, sidecar, health=None):
    ss, lanes = st.session_state, Lanes()
    st.markdown("## Team of experts")
    st.caption("A lead agent plans the work, hands tasks to experts, a separate Critic can send work back, and the answer cites its evidence. "
               "The experts can review the plan first, and the lead can create a new expert when none fits.")
    if health:
        parts.status_row(health)
    with st.expander("Experts · customize the team", icon=":material/groups:"):
        experts_editor(lanes)
    with st.expander("Runs on its own · watch mode", icon=":material/autorenew:"):
        warden_ui.render(ROOT)

    st.markdown("### 1 · Goal and plan")
    cols = st.columns(len(EXAMPLES))
    for col, (label, text) in zip(cols, EXAMPLES):
        if col.button(label, key="ex_" + label, width="stretch"):
            ss.team_goal = text
            st.rerun()
    goal = st.text_area("Your goal", value=ss.get("team_goal", EXAMPLES[0][1]), height=90)
    collaborate = st.toggle("Let the experts review the plan before it runs", value=True, key="team_collab",
                            help="Each expert with a task checks its own tasks and can reword them on its own model lane. One extra AI call per expert.")
    data_online = not health or health.get("data", {}).get("ok", True)
    if not ai_online:
        st.caption("The AI is offline, so no new plan can be made. You can replay a saved run below.")
    elif not data_online:
        st.caption("Zetaris (sensor data) is offline, so no new plan can be made. You can replay a saved run below.")

    if st.button("Make a plan", type="primary", disabled=not ai_online or not data_online or not goal.strip()):
        for k in ("team_out", "team_replay", "team_plan", "team_lead"):
            ss.pop(k, None)
        events = []
        ss.team_events = events
        try:
            lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=ROOT, runs_dir=RUNS_DIR, on_event=events.append, lanes=lanes)
        except Exception as e:                                                   # Zetaris down, a broken experts.local file, a missing .env key
            title, what = plain.error(e)
            st.error(f"**{title}** {what}")
            return
        th, box = _run_in_thread(lambda: lead.plan(goal, collaborate=collaborate))
        status = _stream(th, events, "The lead is planning" + (", then the experts review the plan…" if collaborate else "…"))
        if "err" in box:
            _failed(status, "Planning failed", box["err"], ctx.equipment)
        else:
            status.update(label="Plan ready", state="complete", expanded=False)
            ss.team_lead, ss.team_plan, ss.team_dir = lead, box["v"], ctx.trace.dir

    runs = saved_runs()
    with st.expander("Replay a saved run (no model needed)", icon=":material/history:"):
        if not runs:
            st.caption("No saved team runs yet. Every completed run is kept under runs/ with its plan, trace and answer.")
        else:
            pick = st.selectbox("Saved runs", runs, format_func=lambda r: f"{r['when']} · {r['goal'][:80]}", key="replay_pick")
            if st.button("Replay", icon=":material/play_circle:") and _load_run(pick["dir"]):
                st.rerun()

    plan = ss.get("team_plan")
    if not plan:
        st.info("Write a goal and press **Make a plan**. You can edit the plan before anything runs.")
        return

    if ss.get("team_replay"):
        st.info(f"Replaying the run saved at `{os.path.relpath(ss.team_dir, ROOT)}`: nothing below was recomputed.")
        st.dataframe(pd.DataFrame([{"id": t.id, "expert": t.expert, "goal": t.goal, "depends_on": ", ".join(t.depends_on), "status": t.status} for t in plan.tasks]),
                     hide_index=True, width="stretch")
        _results(plan, ss.team_out, ss.team_events, ss.team_dir)
        return

    lead = ss.team_lead
    for e in [e for e in ss.team_events if e["kind"] == "expert_created"]:
        c1, c2 = st.columns([5, 1])
        c1.info(f"**The lead created a new expert, `{e['name']}`:** {e['role']} · tools: {', '.join(e['tools']) or 'none'} · lane: {e['lane']}")
        if c2.button("Keep it", key=f"keep_{e['name']}", help="Save it to experts.local/ so it is on the team next time"):
            try:
                save_config(EXPERTS_DIR, e["config"], lanes)
                st.toast(f"Saved {e['name']}")
            except ConfigError as err:
                st.error(str(err))
    reviews = [e for e in ss.team_events if e["kind"] == "plan_review"]
    if reviews:
        st.markdown("The experts reviewed the plan · " + " · ".join(_review_line(r) for r in reviews))
    names = lead.registry.names()
    pending = plan.pending_experts(names)
    if pending:
        st.caption("Experts the architect will create during the run: " + ", ".join(f"`{p}`" for p in pending))
    df = pd.DataFrame([{"id": t.id, "expert": t.expert, "goal": t.goal, "depends_on": ", ".join(t.depends_on)} for t in plan.tasks])
    edited = st.data_editor(df, num_rows="dynamic", width="stretch", key="plan_editor",
                            column_config={"expert": st.column_config.SelectboxColumn(options=names + pending, required=True),
                                           "goal": st.column_config.TextColumn(width="large")})
    if ss.get("team_out"):
        st.caption("This plan has run. Press **Make a plan** to start another run.")
    elif st.button("Approve and run", icon=":material/play_arrow:"):
        try:
            rows = [r for r in edited.fillna("").to_dict("records") if str(r.get("id", "")).strip() and str(r.get("goal", "")).strip()]
            new = Plan.from_dict({"goal": plan.goal, "tasks": [{"id": str(r["id"]).strip(), "goal": str(r["goal"]).strip(), "expert": str(r["expert"]).strip(),
                                                                 "depends_on": [d.strip() for d in str(r.get("depends_on") or "").split(",") if d.strip()]} for r in rows]})
            new.validate(names, lead.creators())
        except (PlanError, KeyError, TypeError) as e:
            st.error(f"**This plan can't run.** {e}")
        else:
            ss.team_plan = new
            th, box = _run_in_thread(lambda: (lead.run(new, ss.team_dir, parallel=2), lead.compose(new, ss.team_dir))[1])
            status = _stream(th, ss.team_events, "Experts are working… delegating, checking, reviewing")
            if "err" in box:
                _failed(status, "The run stopped", box["err"], lead.ctx.equipment)
            else:
                status.update(label="Run complete", state="complete", expanded=False)
                ss.team_out = box["v"]

    out = ss.get("team_out")
    if out:
        _results(ss.team_plan, out, ss.team_events, ss.team_dir)
