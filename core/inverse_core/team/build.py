"""Wire a team run from the pieces the app already has (Zetaris client, ledger, Nightshift client). No second copy of any of them."""
from __future__ import annotations

import os

from ..agents import guard
from ..budget import Budget
from ..clients.markovian import MarkovianClient
from ..orchestrator import Orchestrator
from ..trace import Trace
from .critic import Critic
from .lanes import Lanes
from .lead import Lead
from .llmcall import Ctx
from .memory import TeamMemory
from .registry import Registry


def build(zetaris, ledger, world=None, root=".", runs_dir="runs", on_event=None, lanes=None, max_llm_calls=40, max_seconds=900):
    lanes = lanes or Lanes()
    trace = Trace(runs_dir, on_event)
    equipment = [r["equipment_id"] for r in zetaris.sql("SELECT equipment_id FROM obs.equipment_table")]

    def physics(question):                                            # the single-agent pipeline, unchanged, on its own lane client
        return Orchestrator(zetaris, ledger, lanes.client("deep"), runs_dir=runs_dir, world=world).run(question)

    markovian = None
    try:                                                              # Meterless Markovian service (markovian/serve.ts), if it is running
        mk = MarkovianClient(os.environ.get("MARKOVIAN_URL", "http://127.0.0.1:8101"), timeout=120)
        mk.health()
        markovian = mk
    except Exception:
        pass
    trace.event("engines", hmem=type(ledger).__name__, markovian=markovian is not None)
    ctx = Ctx(lanes, trace, Budget(max_llm_calls=max_llm_calls, max_seconds=max_seconds), zetaris=zetaris, physics_runner=physics,
              guard=guard.sanitize, equipment=equipment, root=root, markovian=markovian)
    registry = Registry(ctx, os.path.join(root, "experts"), root)
    memory = TeamMemory(ledger)
    return Lead(ctx, registry, memory, Critic(ctx)), ctx
