"""The council on the crew page: open proposals, decisions, a session on demand, a proposal form for people, and undo."""
import os
import time

import pandas as pd
import streamlit as st

from inverse_core.team.council import Council
from inverse_core.team.crew import name as crew_name

KINDS = {"cfg": "change an agent's settings", "mission": "add or change a standing mission", "note": "a note for shared memory",
         "agent": "keep an agent Forge built", "code": "a code change (for people)"}


def _who(by, configs):
    return "a rule" if str(by).startswith("rule:") else ("you" if by == "human" else crew_name(by, configs))


def render(root, configs, ledger, sidecar):
    ss = st.session_state
    c = Council(root)
    s = c.summary()
    st.caption("Any agent can file a proposal while it works, at no cost. The council decides in short sessions that a rule starts: Vera votes on the "
               "whole agenda in one call, the agent a change concerns votes on its own items, and a fixed rule adopts, rejects or defers. "
               "Adopted changes are applied by code and can be undone. Code changes are never applied by agents; they become a task card for people.")
    due = s["due"]
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"**Open proposals:** {len(s['open'])}" + (f" · a session is due ({due})" if due else " · nothing is due" if s["open"] else ""))
    if c2.button("Hold a session now", disabled=not s["open"], width="stretch", help="Costs at most four model calls. Warden also holds one when the rules say so."):
        ss.council_session = True
    if ss.pop("council_session", False):
        import team
        from inverse_core.clients.world import WorldClient
        from inverse_core.clients.zetaris import ZetarisClient
        from inverse_core.team.build import build
        from inverse_core.team.lanes import Lanes
        try:
            lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=team.ROOT, runs_dir=team.RUNS_DIR, lanes=Lanes())
            with st.spinner("The council is in session…"):
                rec = ctx.council.session(ctx, lead.registry, lead.memory, WorldClient(sidecar), reason="a person asked", by="human")
            st.success(f"Session {rec['s']}: " + (", ".join(f"{d['id']} {d['d']}" for d in rec["decisions"]) or "nothing to decide") + f" · {rec['calls']} model call(s)")
            c, s = Council(root), Council(root).summary()
        except Exception as e:
            st.error(f"**The session could not run.** {type(e).__name__}: {str(e)[:200]}")
    if s["open"]:
        st.dataframe(pd.DataFrame([{"id": p["id"], "by": _who(p["by"], configs), "kind": KINDS.get(p["k"], p["k"]), "about": p["t"], "change": p["w"][:90],
                                    "why": p["y"][:70], "backers": len(p["backers"]), "status": p["status"]} for p in s["open"]]), hide_index=True, width="stretch")
    with st.expander("Propose a change yourself"):
        k = st.selectbox("Kind", list(KINDS), format_func=lambda x: KINDS[x], key="prop_kind")
        t = st.text_input("About (an agent id, a mission name, 'shared' or 'repo')", key="prop_target", value="shared" if k == "note" else "repo" if k == "code" else "")
        w = st.text_input("The change, in a few words", key="prop_what")
        y = st.text_input("Why", key="prop_why")
        p = st.text_input("Exact change as JSON, for cfg or mission (e.g. {\"budget.tool_calls\": 8} or {\"every\": 6})", key="prop_patch")
        if st.button("File it", disabled=not (w.strip() and t.strip())):
            import json
            try:
                patch = json.loads(p) if p.strip() else None
            except ValueError:
                patch = None
                st.error("The exact change must be JSON.")
            else:
                filed = Council(root).file({"k": k, "t": t.strip(), "w": w.strip(), "y": y.strip(), "p": patch}, by="human")
                if filed:
                    st.success(f"Filed {filed['id']} ({len(filed['backers'])} backer(s)). The council decides it at its next session.")
                else:
                    st.error("Not filed: the wire protocol refused it (check the kind, the target and the exact change).")
    if s["decided"]:
        st.caption("Decided lately:")
        rows = []
        for p in s["decided"][:12]:
            d = p.get("decision") or {}
            eff = p.get("effect") or {}
            rows.append({"id": p["id"], "by": _who(p["by"], configs), "change": p["w"][:80], "decision": p["status"], "why": str(d.get("r") or "")[:80],
                         "effect": str(eff.get("summary") or eff.get("x") or "")[:60]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        applied = [p for p in s["decided"] if (p.get("effect") or {}).get("x") == "applied" and p["k"] in ("cfg", "mission", "agent")]
        if applied:
            pick = st.selectbox("Undo an applied change", applied, format_func=lambda p: f"{p['id']} · {p['w'][:70]}", key="undo_pick")
            if st.button("Undo it"):
                import team
                from inverse_core.team.lanes import Lanes
                from inverse_core.team.llmcall import Ctx
                from inverse_core.team.registry import Registry
                from inverse_core.budget import Budget
                from inverse_core.trace import Trace
                ctx = Ctx(Lanes(), Trace(team.RUNS_DIR), Budget())
                reg = Registry(ctx, team.EXPERTS_DIR, team.ROOT)
                st.success("Undone." if Council(root).revert(pick["id"], reg) else "Nothing to undo.")
    if s["sessions"]:
        last = s["sessions"][-1]
        st.caption(f"Last session {last.get('s')} ({last.get('reason')}, {last.get('calls', 0)} model call(s)): "
                   + (", ".join(f"{d['id']} {d['d']}" for d in last.get("decisions") or []) or "nothing to decide"))
    human = os.path.join(root, "council", "human.md")
    if os.path.exists(human):
        with st.expander("Task cards for people (code changes the council wants)"):
            st.markdown(open(human).read()[-4000:])
