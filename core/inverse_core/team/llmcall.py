"""One place where team agents call a model: charges both budgets and records the serving model in the trace."""
from __future__ import annotations

from ..clients.meterless import extract_json


class Ctx:
    """What an expert needs from the host app. Built once per run and passed to the registry."""

    def __init__(self, lanes, trace, budget, zetaris=None, physics_runner=None, guard=None, equipment=()):
        self.lanes, self.trace, self.budget = lanes, trace, budget
        self.zetaris, self.physics_runner, self.guard, self.equipment = zetaris, physics_runner, guard, list(equipment)


def ask(ctx, lane, messages, who, ebudget=None, max_tokens=None, json_reply=False):
    ctx.budget.charge_llm()
    kw = {"max_tokens": max_tokens} if max_tokens else {}
    r = ctx.lanes.client(lane).chat(messages, **kw)
    if ebudget:
        ebudget.charge_tokens(r.get("usage"))
    ctx.trace.event("llm", agent=who, lane=lane, model=r.get("model"), latency_s=r.get("latency_s"), finish=r.get("finish_reason"))
    out = {"text": r["text"], "model": r.get("model")}
    if json_reply:
        out["json"] = extract_json(r["text"])
    return out
