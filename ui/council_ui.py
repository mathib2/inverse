"""The council on the crew page, in plain words: what is open, what was decided, a session on demand, a form built from choices
for people who want to propose a change, and undo."""
import os

import pandas as pd
import streamlit as st

from inverse_core.missions import load_missions
from inverse_core.team import council_wire as wire
from inverse_core.team.council import Council
from inverse_core.team.crew import CREW
from inverse_core.team.crew import name as crew_name

KINDS = {"cfg": "change an agent's settings", "mission": "add or change a standing mission", "note": "a note for the crew's shared memory",
         "agent": "keep an agent Forge built", "code": "a code change (people make it)"}
CFG = {"budget.tool_calls": "how many tool calls it may make", "budget.tokens": "how many tokens it may spend", "budget.seconds": "how many seconds it may take",
       "model_lane": "which model lane it uses", "tools+": "a tool to add", "tools-": "a tool to remove", "system_prompt+": "a sentence to add to its instructions"}
DECISIONS = {"adopted": "adopted", "rejected": "rejected", "deferred": "deferred", "expired": "expired", "needs_human": "for people to decide",
             "withdrawn": "withdrawn", "reverted": "undone", "open": "open"}


def _who(by, configs):
    s = str(by)
    if s.startswith("rule:"):
        return "a rule (" + s.split(":", 1)[1] + ")"
    if s in ("human", "ui") or (s not in CREW and s not in (configs or {})):  # a login name from the shell is "a person", never shown
        return "a person"
    return crew_name(s, configs)


def _about(p, configs):
    if p["k"] in ("cfg", "agent"):
        return crew_name(p["t"], configs)
    if p["k"] == "note":
        return "shared memory"
    if p["k"] == "code":
        return "the code"
    return "mission " + str(p["t"]).replace("_", " ")


WORDS = {"adopt": "adopted", "reject": "rejected", "defer": "deferred", "expire": "expired", "needs_human": "left to people"}


def _sid(s):
    """'S-20261025-153000' -> '2026-10-25 15:30'."""
    s = str(s or "")
    return f"{s[2:6]}-{s[6:8]}-{s[8:10]} {s[11:13]}:{s[13:15]}" if s.startswith("S-") and len(s) >= 17 else s


def _decisions_line(sess):
    return ", ".join(f"{d['id']} {WORDS.get(d.get('d'), d.get('d'))}" for d in sess.get("decisions") or []) or "nothing to decide"


def _form(root, configs):
    kind = st.selectbox("What kind of change", [k for k in KINDS if k != "agent"], format_func=lambda k: KINDS[k], key="prop_kind")
    agents = [i for i, c in configs.items() if c.get("kind") != "architect" and "list_experts" not in (c.get("tools") or [])]
    names = [m["name"] for m in load_missions(root)]
    obj = {"k": kind, "p": {}}
    if kind == "cfg":
        ident = st.selectbox("Which agent", agents, format_func=lambda i: crew_name(i, configs), key="prop_agent")
        obj["t"] = ident
        change = st.selectbox("What to change", list(CFG), format_func=lambda k: CFG[k], key="prop_change")
        if change.startswith("budget."):
            cur = (configs.get(ident, {}).get("budget") or {}).get(change.split(".", 1)[1])
            lo, hi = wire.BUDGET_RANGE[change]
            val = st.number_input("New value" + (f" (now {cur})" if cur else ""), min_value=lo, max_value=hi, value=min(hi, max(lo, int(cur or lo))), key=f"prop_{change}")
        elif change == "model_lane":
            val = st.selectbox("Lane", wire.LANES, key="prop_lane")
        elif change in ("tools+", "tools-"):
            val = st.selectbox("Tool", list(wire.GRANTABLE), key="prop_tool")
        else:
            val = st.text_input("The sentence", key="prop_sentence")
        obj["p"] = {change: val}
        obj["w"] = f"{CFG[change]}: {val}"[:140]
    elif kind == "mission":
        pick = st.selectbox("Which mission", names + ["a new mission"], format_func=lambda n: n.replace("_", " "), key="prop_mission")
        name = st.text_input("Name (letters, digits, underscores)", key="prop_mission_name") if pick == "a new mission" else pick
        every = st.number_input("Every (hours)", min_value=0.5, max_value=168.0, value=12.0, step=0.5, key="prop_every")
        goal = st.text_input("Goal" + (" (leave empty to keep it)" if pick != "a new mission" else ""), key="prop_goal")
        obj["t"] = name or "mission"
        obj["p"] = {"every": every}
        if pick == "a new mission":
            obj["p"]["name"] = name
        if goal.strip():
            obj["p"]["goal"] = goal.strip()
        obj["w"] = (f"run {name} every {every:g} hours" if pick != "a new mission" else f"add the mission {name}")[:140]
    else:
        obj["t"] = "shared" if kind == "note" else "repo"
        obj["w"] = st.text_input("The note" if kind == "note" else "The change, in a few words", key="prop_text")
    obj["y"] = st.text_input("Why (one sentence)", key="prop_why")
    if st.button("File it", disabled=not str(obj.get("w") or "").strip()):
        c = Council(root)
        filed = c.file(obj, by="human")
        if filed:
            st.success(f"Filed {filed['id']} ({len(filed['backers'])} backer{'s' if len(filed['backers']) != 1 else ''}). "
                       + ("A session is due; press **Hold a session now** to decide it." if c.due(forced=False) else "The council decides it at its next session."))
        else:
            st.error(f"Not filed: {c.last_problem or 'the proposal was not accepted'}.")


def render(root, configs, ledger, sidecar):
    ss = st.session_state
    c = Council(root)
    s = c.summary()
    st.caption("The agents propose changes to their own crew; Vera and the agent concerned vote; a rule decides; everything can be undone.")
    last = s["sessions"][-1] if s["sessions"] else None
    if ss.pop("council_session", False):
        import advanced_ui
        from inverse_core.clients.world import WorldClient
        from inverse_core.clients.zetaris import ZetarisClient
        from inverse_core.team.build import build
        from inverse_core.team.lanes import Lanes
        try:
            lead, ctx = build(ZetarisClient(), ledger, WorldClient(sidecar), root=advanced_ui.ROOT, runs_dir=advanced_ui.RUNS_DIR, lanes=Lanes())
            with st.spinner(f"The council is in session: {crew_name('critic')} is voting…"):
                rec = ctx.council.session(ctx, lead.registry, lead.memory, WorldClient(sidecar), reason="a person asked", by="human")
            st.success(f"Session of {_sid(rec['s'])}: {_decisions_line(rec)} · {rec.get('calls', 0)} model call(s)" + (f" · {rec['note']}" if rec.get("note") else ""))
            c, s = Council(root), Council(root).summary()
            last = s["sessions"][-1] if s["sessions"] else None
        except Exception as e:
            st.error(f"**The session could not run.** {type(e).__name__}: {str(e)[:200]}")
    if not s["open"]:
        st.markdown("No open proposals. " + (f"Last session, {_sid(last.get('s'))} ({last.get('reason')}): {_decisions_line(last)}." if last else
                                             "No session yet: agents file proposals while they work, and the first session happens when a rule says so."))
    else:
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"**{len(s['open'])} open proposal{'s' if len(s['open']) != 1 else ''}**" + (f" · a session is due: {s['due']}" if s["due"] else " · nothing is due yet"))
        if c2.button("Hold a session now", width="stretch", help="At most four model calls. Warden also holds one when the rules say so."):
            ss.council_session = True
            st.rerun()
        st.dataframe(pd.DataFrame([{"id": p["id"], "from": _who(p["by"], configs), "about": _about(p, configs), "change": p["w"][:90], "why": str(p.get("y") or "")[:70],
                                    "backers": len(p["backers"]), "status": DECISIONS.get(p["status"], p["status"])} for p in s["open"]]), hide_index=True, width="stretch")
    with st.expander("Propose a change yourself"):
        _form(root, configs)
    if s["decided"]:
        st.caption("Decided lately:")
        rows = []
        for p in s["decided"][:12]:
            d, eff = p.get("decision") or {}, p.get("effect") or {}
            rows.append({"id": p["id"], "from": _who(p["by"], configs), "about": _about(p, configs), "change": p["w"][:80], "decision": DECISIONS.get(p["status"], p["status"]),
                         "why": str(d.get("r") or "")[:80], "effect": str(eff.get("summary") or eff.get("x") or "")[:60]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        applied = [p for p in s["decided"] if (p.get("effect") or {}).get("x") == "applied" and p["k"] in ("cfg", "mission", "agent", "note")]
        if applied:
            c1, c2 = st.columns([5, 1])
            pick = c1.selectbox("Undo an applied change", applied, format_func=lambda p: f"{p['id']} · {_about(p, configs)} · {p['w'][:60]}", key="undo_pick", label_visibility="collapsed")
            if c2.button("Undo it", width="stretch"):
                import advanced_ui
                from inverse_core.budget import Budget
                from inverse_core.team.lanes import Lanes
                from inverse_core.team.llmcall import Ctx
                from inverse_core.team.memory import TeamMemory
                from inverse_core.team.registry import Registry
                from inverse_core.trace import Trace
                try:
                    ctx = Ctx(Lanes(), Trace(advanced_ui.RUNS_DIR), Budget())
                    reg = Registry(ctx, advanced_ui.EXPERTS_DIR, advanced_ui.ROOT)
                    ok = Council(root).revert(pick["id"], reg, memory=TeamMemory(ledger))
                    st.success("Undone." if ok else "Nothing to undo.")
                except Exception as e:
                    st.error(f"**Could not undo it.** {type(e).__name__}: {str(e)[:200]}")
    human = os.path.join(root, "council", "human.md")
    if os.path.exists(human):
        with st.expander("Task cards for people (changes the council leaves to you)"):
            st.markdown(open(human).read()[-4000:])
