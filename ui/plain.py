"""Plain-language text for the INVERSE UI: provider wording, the glossary, errors that say what to do, and one sentence per
trace event of a crew mission. tests/test_ui_plain.py keeps these honest."""
from __future__ import annotations

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


def team_step(e: dict) -> str | None:
    """One plain line of live progress for a mission trace event, or None for events too technical to show."""
    k, task, who = e.get("kind"), e.get("task", ""), e.get("expert") or e.get("agent") or "an expert"
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
        return f"{who} used {e.get('tool')}" + (", which failed" if e.get("error") else "")
    if k == "refused_scope":
        return f"{who} refused {task}: {e.get('reason')}"
    if k == "expert_result":
        n = e.get("evidence") or 0
        return f"{who} finished {task} with {n} piece{'s' if n != 1 else ''} of evidence"
    if k == "critic":
        by = "a fixed rule" if e.get("by") == "rule" else "the reviewer"
        return {"accept": f"{task} accepted by {by}", "revise": f"{task} sent back by {by}: {e.get('reason')}",
                "reject": f"{task} rejected by {by}: {e.get('reason')}"}.get(e.get("verdict"))
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
        return f"{task} skipped: it needed a task that did not finish"
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
