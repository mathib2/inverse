"""Plain-language text for the INVERSE UI: provider wording, the glossary, errors that say what to do, and one sentence per
trace event of a crew mission. tests/test_ui_plain.py keeps these honest."""
from __future__ import annotations

TOOL_WORDS = {"run_sql": "data queries", "calc": "calculator", "memory": "shared memory", "ask_expert": "asks the others", "post_message": "leaves notes",
              "read_messages": "reads notes", "scan": "code scan", "read_file": "reads code", "grep": "searches code", "list_files": "lists files",
              "list_experts": "sees the crew", "design_expert": "designs agents", "create_expert": "builds agents", "test_expert": "test-drives agents",
              "propose": "proposes changes to the crew", "support": "backs proposals"}
TOOL_VERBS = {"run_sql": "ran a data query", "calc": "used the calculator", "memory": "checked shared memory", "ask_expert": "asked another agent",
              "post_message": "left a note", "read_messages": "read its notes", "scan": "scanned the code", "read_file": "read a file", "grep": "searched the code",
              "list_files": "listed files", "list_experts": "looked at the crew", "design_expert": "designed an agent", "create_expert": "built an agent",
              "test_expert": "test-drove an agent", "propose": "filed a proposal", "support": "backed a proposal"}
RUN_STEPS = ("planned", "working", "reviewing", "answered")                 # the run panel's timeline, in order
TASK_WORDS = {"pending": "pending", "running": "running", "reviewing": "in review", "accepted": "accepted", "sent_back": "sent back",
              "rejected": "rejected", "failed": "failed", "skipped": "skipped"}   # a task's state on its card in the run panel

PANEL_EMPTY = "Ask the crew below, or try one of the examples on the left: the answer, its evidence, who did what and the steps will appear here."

GLOSSARY = [
    ("Mission", "A goal given to the crew: Atlas plans it, the agents work, Vera checks, and the answer cites its evidence."),
    ("Evidence", "What an agent's answer rests on: a query and its rows, a calculation, a file and line, or a tool result. Every claim must point at one."),
    ("Review", "Vera's check of each result: fixed rules first, then its own model lane. Weak work goes back with a reason."),
    ("Shared memory", "H-MEM: what the crew found and ruled out, kept across missions with a trust order (a checked fact outranks a model's claim)."),
    ("Zetaris", "The data platform the crew queries: the equipment registry, sensor specifications, maintenance history and samples."),
    ("Messages", "What the agents say to each other during a mission: results announced to all, Vera's notes, questions and answers."),
]


def provider_words() -> dict:
    """Wording for the configured model provider (a local server such as Ollama, or Nightshift), from the client's table."""
    from inverse_core.clients.meterless import provider
    return provider()


def glossary_terms() -> list[tuple[str, str]]:
    P = provider_words()
    entry = ("Nightshift", "The Meterless app that runs the AI (NVIDIA Nemotron) for INVERSE.") if P["id"] == "nightshift" \
        else (P["name"], f"The model server INVERSE talks to: {P['model_line']}.")
    return GLOSSARY + [entry]


def error(exc: Exception, known_equipment=()) -> tuple[str, str]:
    """(title, what to do) for a failed mission."""
    name = type(exc).__name__
    if name == "NightshiftOffline":
        return "The AI went offline", (f"INVERSE lost its connection to {provider_words()['name']}, which runs the AI. "
                                       "Reconnect it (see AI under Connections in the sidebar), then try again.")
    if name == "BudgetExceeded":
        return "The run took too long", "It hit its time or AI-call limit. Try again, or ask a simpler question."
    if name == "PlanError":
        return "No usable plan", f"The lead could not turn the goal into a plan it can run. {str(exc)[:200]}"
    if name == "BadReply":
        return "Couldn't read the AI's reply", "The AI answered in a form INVERSE couldn't read. Try again; the trace keeps a preview of the reply."
    if name == "ConfigError":
        return "An expert's settings are invalid", f"{str(exc)[:200]}"
    if name in ("ConnectionError", "ConnectTimeout", "ReadTimeout"):
        return "A service didn't respond", "Zetaris or the memory service didn't answer. Check the connections in the sidebar."
    return "Something went wrong", f"{name}: {str(exc)[:200]}"


def run_ended(took: str, stopped=False) -> str:
    """The one line (and the toast) when a mission is over."""
    return f"Stopped after {took}" if stopped else f"The crew answered in {took}"


def agent_word(agent) -> str:
    """The agent behind a model-call label: 'lead_plan' and 'lead_compose' are the lead, 'council_vera' is the critic, '<x>_plan_review' is x."""
    a = str(agent or "")
    for suffix in ("_plan_review", "_plan_sample"):
        if suffix in a:
            return a.split(suffix)[0]
    if a.startswith("lead"):
        return "lead"
    if a == "council_vera":
        return "critic"
    if a.startswith("council_"):
        return a[len("council_"):]
    return a or "an expert"


def by_word(by, agents=None) -> str:
    """Who filed or backed a proposal: an agent id (renamed later), a rule, or a person. With the set of agent ids, anything
    else (a login name from the shell, for one) is "a person": names of people never reach a screen."""
    s = str(by or "")
    if s.startswith("rule:"):
        return "a rule (" + s.split(":", 1)[1].replace("_", " ") + ")"
    if s in ("human", "ui") or not s or (agents is not None and s not in agents):
        return "a person"
    return s


def team_step(e: dict, agents=None) -> str | None:
    """One plain line of live progress for a mission trace event, or None for events too technical to show."""
    k, task, who = e.get("kind"), e.get("task", ""), e.get("expert") or e.get("agent") or "an expert"
    if k == "llm":
        lat = e.get("latency_s")
        return f"{agent_word(e.get('agent'))}'s model replied" + (f" after {lat:.0f} s" if isinstance(lat, (int, float)) else "")
    if k == "memory_write":
        n = e.get("findings") or 0
        return f"Shared memory keeps {n} finding{'s' if n != 1 else ''} from {task}"
    if k == "markovian_start":
        return f"{who} starts a long review in {e.get('working_sets')} bounded chunk(s) through Markovian"
    if k == "markovian_chunk":
        return f"{who} reviewed chunk {e.get('step')}" + (f": {e.get('file')}" if e.get("file") else "")
    if k == "markovian_done":
        return f"{who}'s long review finished after {e.get('chunks')} chunk(s)"
    if k == "composing":
        n = e.get("accepted") or 0
        return f"The lead writes the answer from {n} accepted result{'s' if n != 1 else ''}" + (f"; {e['unfinished']} did not finish" if e.get("unfinished") else "")
    if k == "proposal_filed":
        return f"{by_word(e.get('by'), agents)} proposed to the council: {e.get('what')}"
    if k == "proposal_backed":
        return f"{by_word(e.get('by'), agents)} backed proposal {e.get('id')} ({e.get('support')} backers)"
    if k == "proposal_dropped":
        return f"A proposal from {by_word(e.get('by'), agents)} was not readable: {e.get('reason')}"
    if k == "proposal_expired":
        return f"Proposal {e.get('id')} expired unheard"
    if k == "council_session":
        n = len(e.get("items") or [])
        return f"The council is in session: {n} proposal{'s' if n != 1 else ''} on the agenda ({e.get('reason')})"
    if k == "council_decision":
        word = {"adopt": "adopted", "reject": "rejected", "defer": "deferred", "expire": "expired", "needs_human": "left to people"}.get(e.get("decision"), str(e.get("decision")))
        return f"The council {word} {e.get('id')}" + (f": {e.get('reason')}" if e.get("reason") else "")
    if k == "council_effect":
        x = e.get("x")
        if x == "applied":
            return f"Change {e.get('id')} applied: {e.get('summary')}"
        if x == "reverted":
            return f"Change {e.get('id')} undone"
        return f"Change {e.get('id')} could not be applied: {e.get('error')}"
    if k == "council_vote_unreadable":
        return f"{e.get('who')}'s vote could not be read: {e.get('reason')}"
    if k == "council_done":
        return f"The council session ended after {e.get('calls') or 0} model call(s)" + (f": {e['note']}" if e.get("note") else "")
    if k == "plan":
        n = len(e.get("tasks") or [])
        return f"The lead drafted a plan with {n} task{'s' if n != 1 else ''}" + (" by the fixed rule, because the model's plans were not usable" if e.get("by") == "rule" else "")
    if k == "expert_created":
        return f"The lead created a new expert, {e.get('name')}: {e.get('role')}"
    if k == "plan_review":
        changed = e.get("changed") or []
        s = f"{who} reviewed the plan: " + (f"reworded {', '.join(changed)}" if changed else ("fine as drafted" if e.get("ok", True) else "had concerns"))
        return s + (f"; needs {'; '.join(e['missing'])}" if e.get("missing") else "")
    if k == "plan_approved":
        return "Plan approved; the experts start"
    if k == "level":
        return f"{', '.join(e.get('tasks') or [])} run at the same time"
    if k == "sql_cache_hit":
        return "Reused a query result from earlier in this run"
    if k == "delegate":
        return f"{who} starts {task}" + (f" (attempt {e['attempt']}, with the reviewer's notes)" if (e.get("attempt") or 1) > 1 else "")
    if k == "tool":
        return f"{who} {TOOL_VERBS.get(e.get('tool'), 'used ' + str(e.get('tool')))}" + (", which failed" if e.get("error") else "")
    if k == "plan_review_ignored":
        return f"{who}'s rewording of {task} was ignored ({e.get('reason')})"
    if k == "injection_guard":
        return f"Text that read as instructions for the AI was withheld from {who}"
    if k == "refused_scope":
        return f"{who} refused {task}: {e.get('reason')}"
    if k == "expert_result":
        n = e.get("evidence") or 0
        return f"{who} finished {task} with {n} piece{'s' if n != 1 else ''} of evidence"
    if k == "critic":
        if e.get("by") == "code":
            return f"{task} accepted: {e.get('reason')}"
        if e.get("by") == "error" or e.get("verdict") == "unreviewed":
            return f"{task} kept without review: {e.get('reason')}"
        by = "a fixed rule" if e.get("by") == "rule" else "the reviewer"
        return {"accept": f"{task} accepted by {by}", "revise": f"{task} sent back by {by}: {e.get('reason')}",
                "reject": f"{task} rejected by {by}: {e.get('reason')}"}.get(e.get("verdict"))
    if k == "critic_reask":
        return f"{task}: the reviewer's verdict could not be read, asking once more"
    if k == "retry":
        return f"{task} will be retried"
    if k == "stuck":
        return f"{task}: the expert repeated itself, so it must change strategy"
    if k == "escalate":
        return f"{task} stopped: the expert kept repeating the same answer"
    if k == "expert_error":
        return f"{task}: the expert hit an error and will try again"
    if k == "task_failed":
        return f"{task} failed: {e.get('reason')}"
    if k == "task_rejected":
        return f"{task} rejected: {e.get('reason')}"
    if k == "task_skipped":
        return f"{task} was not started: a person stopped the mission" if e.get("reason") == "stopped" else f"{task} skipped: it needed a task that did not finish"
    if k == "message":
        who, to, text, kind = e.get("from"), e.get("to"), str(e.get("text") or "")[:140], e.get("type")
        if kind == "review":                                                  # the Critic line already says why
            return None
        verb = {"question": f"asked {to}", "answer": f"answered {to}", "result": "told the team", "note": f"left {to} a note"}.get(kind, f"wrote to {to}")
        return f"{who} {verb}: {text}"
    if k == "consult":
        return f"{e.get('from')} consulted {e.get('to')}" + (" and got an answer" if e.get("ok") else ", who could not answer")
    if k == "compose":
        n = e.get("unfinished") or 0
        return "The lead wrote the final answer" + (f" ({n} task{'s' if n != 1 else ''} unfinished)" if n else "")
    return None
