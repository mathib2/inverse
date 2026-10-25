"""One place where team agents call a model: charges both budgets and records the serving model in the trace."""
from __future__ import annotations

import threading

from ..clients.meterless import extract_json
from .bus import Bus


class BadReply(ValueError):
    """The model's reply could not be read as JSON (traced with a preview before it is raised)."""


class Ctx:
    """What an expert needs from the host app. Built once per run and passed to the registry."""

    def __init__(self, lanes, trace, budget, zetaris=None, guard=None, equipment=(), root=".", markovian=None, bus=None):
        self.lanes, self.trace, self.budget = lanes, trace, budget
        self.zetaris, self.guard, self.equipment = zetaris, guard, list(equipment)
        self.root = root                                                      # the repository experts may read (code we own)
        self.markovian = markovian                                            # Meterless Markovian client when the service is up, else None
        self.sql_cache = {}                                                   # per-run: the same read-only query is sent to Zetaris once
        self.bus = bus or Bus(getattr(trace, "dir", None), trace)             # how experts talk to each other (messages.jsonl next to the trace)
        self.registry = None                                                  # attached by build(); the architect's tools and ask_expert act on it
        self.council = None                                                   # attached by build(); proposals go there, sessions decide them
        self.stop = threading.Event()                                         # set by a person: the Lead finishes the step in progress and skips the rest


def ask(ctx, lane, messages, who, ebudget=None, max_tokens=None, json_reply=False, temperature=None):
    """json_reply asks the runtime for one JSON object and parses it; a reply that still cannot be parsed is traced
    (first 300 characters) before the error propagates, so a failed run explains itself."""
    ctx.budget.charge_llm()
    kw = {"max_tokens": max_tokens} if max_tokens else {}
    if json_reply:
        kw["json_object"] = True
    if temperature is not None:
        kw["temperature"] = temperature
    r = ctx.lanes.client(lane).chat(messages, **kw)
    if ebudget:
        ebudget.charge_tokens(r.get("usage"))
    ctx.trace.event("llm", agent=who, lane=lane, model=r.get("model"), latency_s=r.get("latency_s"), finish=r.get("finish_reason"))
    out = {"text": r["text"], "model": r.get("model"), "usage": r.get("usage")}
    if json_reply:
        try:
            out["json"] = extract_json(r["text"])
        except ValueError as e:
            ctx.trace.event("llm_parse_error", agent=who, lane=lane, model=r.get("model"), finish=r.get("finish_reason"), preview=(r["text"] or "")[:300])
            raise BadReply(str(e)) from e
    return out
