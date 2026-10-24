"""Team-of-experts mode (Streamlit). Goal -> editable plan -> approve & run -> per-expert results, Critic verdicts, trace, cited answer.
The single-machine page in app.py is unchanged and remains the fallback demo."""
import os
import threading
import time

import pandas as pd
import streamlit as st

from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.team.build import build
from inverse_core.team.plan import Plan, PlanError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = ["Pump P-104 vibration changed. Has it worn, and what does its registry mass imply for the spring force at 5 mm displacement given the fitted stiffness?",
            "Rig T-200 was reassembled. What governs its vibration, and what do we know about it from the maintenance history?"]
ICON = {"done": "✅", "rejected": "⛔", "failed": "⚠️", "pending": "⏳", "running": "🔄"}


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
                e = events[shown]
                shown += 1
                if e["kind"] in ("plan", "delegate", "expert_result", "critic", "retry", "stuck", "escalate", "task_failed", "task_rejected", "compose"):
                    detail = {k: v for k, v in e.items() if k in ("task", "expert", "verdict", "reason", "attempt", "model", "lane")}
                    st.markdown(f"- `{e['kind']}` {detail}")
            time.sleep(0.4)
        return status


def render(ledger, ai_online, sidecar):
    ss = st.session_state
    st.markdown("## Team of experts")
    st.caption("A lead agent plans the work, hands tasks to experts, a separate Critic can send work back, and the answer cites its evidence.")
    goal = st.text_area("Your goal", value=ss.get("team_goal", EXAMPLES[0]), height=90, key="team_goal_box")
    st.caption("Examples: " + " · ".join(f"“{e[:60]}…”" for e in EXAMPLES))

    if st.button("Make a plan", type="primary", disabled=not ai_online or not goal.strip()):
        ss.pop("team_out", None)
        events = []
        ss.team_events = events
        lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=ROOT, runs_dir=os.path.join(ROOT, "runs"), on_event=events.append)
        with st.spinner("The lead is planning…"):
            th, box = _run_in_thread(lambda: lead.plan(goal))
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
            status = _stream(th, ss.team_events, "Experts are working… planning, delegating, reviewing")
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
    ev = [e for e in ss.team_events if e["kind"] in ("llm", "delegate", "critic", "retry", "stuck", "escalate", "task_failed", "task_rejected")]
    st.dataframe(pd.DataFrame([{"t (s)": e["t"], "event": e["kind"], "task": e.get("task", ""), "lane": e.get("lane", ""),
                                "model": e.get("model", ""), "detail": str(e.get("reason") or e.get("verdict") or e.get("agent") or "")[:140]} for e in ev]),
                 hide_index=True, width="stretch")
    st.caption("Models that served this run: " + ", ".join(out["models_used"]) + f" · trace file: `{os.path.relpath(ss.team_dir, ROOT)}/trace.jsonl`")
