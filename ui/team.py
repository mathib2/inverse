"""Team-of-experts mode (Streamlit). Goal -> editable plan -> approve & run -> per-expert results, Critic verdicts, trace, cited answer.
Experts are config: this page also edits them (saved to experts.local/, used by the next plan) and can keep an expert the lead created.
The single-machine page in app.py is unchanged and remains the fallback demo."""
import os
import threading
import time

import pandas as pd
import streamlit as st

import plain
from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.team.build import build
from inverse_core.team.lanes import Lanes
from inverse_core.team.plan import Plan, PlanError
from inverse_core.team.registry import KINDS, TOOL_NAMES, ConfigError, forget_config, load_configs, save_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERTS_DIR = os.path.join(ROOT, "experts")
EXAMPLES = ["Pump P-104 vibration changed. Has it worn, and what does its registry mass imply for the spring force at 5 mm displacement given the fitted stiffness?",
            "Rig T-200 was reassembled. What governs its vibration, and what do we know about it from the maintenance history?",
            "Review core/inverse_core/team for weaknesses in how model output and SQL are handled, and tell me P-104's registry mass."]
ICON = {"done": "✅", "rejected": "⛔", "failed": "⚠️", "pending": "⏳", "running": "🔄"}
KIND_HELP = {"physics": "the physics-checked pipeline, unchanged", "research": "read-only SQL on Zetaris, cites every query",
             "reasoning": "step by step, every calculation recomputed", "custom": "a tool-using agent defined only by this config",
             "vulnerability": "defensive code review of this repository, findings checked against the files"}
NEW = {"name": "", "kind": "custom", "role": "", "tools": ["run_sql", "calc", "memory"], "model_lane": "fast", "budget": {}, "enabled": True}


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
    cfgs = load_configs(EXPERTS_DIR, lanes)
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
        tools = st.multiselect("Tools it may use", sorted(TOOL_NAMES), default=[t for t in c["tools"] if t in TOOL_NAMES])
        lane = st.selectbox("Model lane", lane_names, index=lane_names.index(c["model_lane"]) if c["model_lane"] in lane_names else 0,
                            format_func=lambda n: f"{n} · {lanes.mapping[n]}")
        c1, c2, c3 = st.columns(3)
        tool_calls = c1.number_input("Max tool calls", 1, 50, int(b.get("tool_calls", 6)))
        tokens = c2.number_input("Max tokens", 1000, 200000, int(b.get("tokens", 40000)), step=1000)
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


def render(ledger, ai_online, sidecar):
    ss, lanes = st.session_state, Lanes()
    st.markdown("## Team of experts")
    st.caption("A lead agent plans the work, hands tasks to experts, a separate Critic can send work back, and the answer cites its evidence. "
               "The experts can review the plan first, and the lead can create a new expert when none fits.")
    with st.expander("Experts · customize the team", icon=":material/groups:"):
        experts_editor(lanes)
    goal = st.text_area("Your goal", value=ss.get("team_goal", EXAMPLES[0]), height=90, key="team_goal_box")
    st.caption("Examples: " + " · ".join(f"“{e[:70]}…”" for e in EXAMPLES))
    collaborate = st.toggle("Let the experts review the plan before it runs", value=True, key="team_collab",
                            help="Each expert with a task checks its own tasks and can reword them. The physics expert checks by rule; the others ask their own model lane. One extra AI call per expert.")

    if st.button("Make a plan", type="primary", disabled=not ai_online or not goal.strip()):
        ss.pop("team_out", None)
        events = []
        ss.team_events = events
        lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=ROOT, runs_dir=os.path.join(ROOT, "runs"), on_event=events.append, lanes=lanes)
        with st.spinner("The lead is planning" + (", then the experts review the plan…" if collaborate else "…")):
            th, box = _run_in_thread(lambda: lead.plan(goal, collaborate=collaborate))
            th.join()
        if "err" in box:
            st.error(f"**Planning failed.** {box['err']}")
        else:
            ss.team_lead, ss.team_plan, ss.team_dir = lead, box["v"], ctx.trace.dir
    plan = ss.get("team_plan")
    if not plan:
        st.info("Write a goal and press **Make a plan**. You can edit the plan before anything runs.")
        return
    lead = ss.team_lead

    st.markdown("### 1 · Plan (edit, then approve)")
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
    df = pd.DataFrame([{"id": t.id, "expert": t.expert, "goal": t.goal, "depends_on": ", ".join(t.depends_on)} for t in plan.tasks])
    edited = st.data_editor(df, num_rows="dynamic", width="stretch", key="plan_editor",
                            column_config={"expert": st.column_config.SelectboxColumn(options=names, required=True),
                                           "goal": st.column_config.TextColumn(width="large")})
    if st.button("Approve and run", icon=":material/play_arrow:"):
        try:
            rows = [r for r in edited.to_dict("records") if r.get("id") and r.get("goal")]
            new = Plan.from_dict({"goal": plan.goal, "tasks": [{"id": str(r["id"]).strip(), "goal": r["goal"], "expert": r["expert"],
                                                                 "depends_on": [d.strip() for d in str(r.get("depends_on") or "").split(",") if d.strip()]} for r in rows]})
            new.validate(names)
        except (PlanError, KeyError, TypeError) as e:
            st.error(f"**This plan can't run.** {e}")
        else:
            ss.team_plan = new
            th, box = _run_in_thread(lambda: (lead.run(new, ss.team_dir), lead.compose(new))[1])
            status = _stream(th, ss.team_events, "Experts are working… delegating, checking, reviewing")
            if "err" in box:
                status.update(label="The run stopped", state="error")
                st.error(f"**{type(box['err']).__name__}.** {box['err']}")
            else:
                status.update(label="Run complete", state="complete", expanded=False)
                ss.team_out = box["v"]

    out = ss.get("team_out")
    if not out:
        return
    plan = ss.team_plan
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
                st.dataframe(pd.DataFrame([{"#": f"{t.id}.E{i}", "type": e["type"], "source": e["source"][:120], "detail": e["detail"][:200]}
                                           for i, e in enumerate(t.result["evidence"], 1)]), hide_index=True, width="stretch")
            if t.feedback:
                st.caption(f"Last feedback: {t.feedback}")

    st.markdown("### 4 · Trace")
    ev = [e for e in ss.team_events if e["kind"] in ("llm", "delegate", "tool", "critic", "retry", "stuck", "escalate", "task_failed", "task_rejected",
                                                      "refused_scope", "plan_review", "expert_created")]
    st.dataframe(pd.DataFrame([{"t (s)": e["t"], "event": e["kind"], "task": e.get("task", ""), "lane": e.get("lane", ""), "model": e.get("model", ""),
                                "detail": str(e.get("reason") or e.get("verdict") or e.get("tool") or e.get("name") or e.get("agent") or "")[:140]} for e in ev]),
                 hide_index=True, width="stretch")
    st.caption("Models that served this run: " + ", ".join(out["models_used"]) + f" · trace file: `{os.path.relpath(ss.team_dir, ROOT)}/trace.jsonl`")
