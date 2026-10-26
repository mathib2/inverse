"""One chat log for everything the crew says, across missions, Warden, the council and the improvement loop: `state/chat.jsonl`
under the checkout root. The Live tab of the UI tails it. Every line is data a person reads, never an instruction to an agent."""
from __future__ import annotations

import json
import os
import threading
import time

MAX_TEXT = 600
_lock = threading.Lock()
NAMES = {"lead": "Atlas", "critic": "Vera", "watch": "Warden", "research": "Scout", "reasoning": "Euler", "solver": "Ada",
         "vulnerability": "Sentinel", "architect": "Forge", "tinker": "Tinker"}
QUIET = ("summary_by_code", "scout_numbers_dropped", "forge_by_rule", "sql_completed", "sql_pinned", "calc_nudge", "bare_answer", "critic_reask",
         "stuck", "escalate", "tool_repeat")


def _n(x):
    return NAMES.get(str(x or ""), str(x or ""))


def narrate(e, root_dir=None, run=None):
    """A chat line for the trace events a person wants to see as they happen: the plan, the hand-outs, tool calls, results,
    reviews, retries and the answer. None for the rest (model calls, timings). Messages between agents are written by the bus."""
    k = e.get("kind")
    who, to, kind, text = "lead", "all", "note", None
    if k == "plan":
        tasks = e.get("tasks") or []
        text = ("Plan by rule: " if e.get("by") == "rule" else "Plan: ") + "; ".join(f"{t.get('id')} {_n(t.get('expert'))}: {str(t.get('goal') or '')[:80]}" for t in tasks[:5])
    elif k == "plan_guard":
        text = "Routing by rule: " + "; ".join(str(c) for c in (e.get("changes") or []))[:400]
    elif k == "delegate":
        who, to, kind = "lead", e.get("expert") or "all", "question"
        text = f"{e.get('task')}: {str(e.get('goal') or '')[:160]}" if e.get("goal") else f"{e.get('task')} is yours"
    elif k == "tool":
        who, kind = e.get("agent") or "lead", "log"
        err = e.get("error")
        text = f"{e.get('tool')}({str(e.get('args') or '')[:140]})" + (f" -> {str(err)[:120]}" if err not in (None, "", "None") else "")
    elif k == "expert_result":
        who, kind = e.get("expert") or "lead", "result"
        try:
            conf = f"{float(e.get('confidence')):.2f}"
        except (TypeError, ValueError):
            conf = str(e.get("confidence"))
        text = f"Finished {e.get('task')}: confidence {conf}, {e.get('evidence')} evidence item(s), {e.get('tool_calls') or 0} tool call(s)"
    elif k == "critic":
        who, to, kind = "critic", "lead", "review"
        by = {"rule": "by rule", "code": "by code", "error": "unreviewed", "llm": "by judgement"}.get(str(e.get("by")), str(e.get("by") or ""))
        text = f"{str(e.get('verdict') or '').upper()} {e.get('task')} ({by}): {str(e.get('reason') or '')[:220]}"
    elif k == "retry":
        text = f"{e.get('task')} goes back for attempt {e.get('next_attempt')}: {str(e.get('reason') or '')[:160]}"
    elif k in ("task_failed", "task_rejected", "task_skipped"):
        kind = "note" if k == "task_skipped" else "alert"
        text = f"{e.get('task')} {k.split('_', 1)[1]}: {str(e.get('reason') or e.get('blocked_by') or '')[:160]}"
    elif k == "composing":
        kind, text = "log", "Writing the answer"
    elif k == "compose":
        kind = "result"
        text = (f"Answer ready: {e.get('cited', 0)} citation(s)" + ("; composed by code" if e.get("fallback") else "")
                + (f"; {e.get('unfinished')} task(s) unfinished" if e.get("unfinished") else ""))
    elif k in QUIET:
        who, kind = e.get("expert") or e.get("agent") or "lead", "log"
        detail = {kk: vv for kk, vv in e.items() if kk not in ("kind", "t", "expert", "agent", "task")}
        text = k.replace("_", " ") + (f" on {e.get('task')}" if e.get("task") else "") + (": " + json.dumps(detail, default=str)[:160] if detail else "")
    if not text:
        return None
    return say(who, text, to=to, kind=kind, root_dir=root_dir, run=run)


def root():
    return os.environ.get("INVERSE_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def path(root_dir=None):
    return os.path.join(root_dir or root(), "state", "chat.jsonl")


def say(who, text, to="all", kind="note", root_dir=None, **extra):
    """Append one line: who said what to whom, with a kind (note, result, review, question, answer, log, alert, proposal) and anything
    else the caller wants kept (task, run, url). Never raises: a chat line is not worth a failed mission."""
    line = {"ts": round(time.time(), 3), "who": str(who), "to": str(to or "all"), "kind": str(kind), "text": str(text)[:MAX_TEXT], **extra}
    try:
        p = path(root_dir)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with _lock, open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")
    except OSError:
        pass
    return line


def tail(n=200, root_dir=None):
    """The last n lines, oldest first; bad lines are skipped."""
    p = path(root_dir)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            size, chunk, data = f.tell(), 65536, b""
            while size > 0 and data.count(b"\n") <= n:
                step = min(chunk, size)
                size -= step
                f.seek(size)
                data = f.read(step) + data
    except OSError:
        return []
    out = []
    for raw in data.decode("utf-8", "replace").splitlines()[-n:]:
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out
