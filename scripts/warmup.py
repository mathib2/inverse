"""Warm the model server's prefix cache with exactly the system prompts a mission sends, one two-token request each, so the first
mission after a restart (or the demo's first goal) does not pay 10 s of prompt processing per call.
  PYTHONPATH=core .venv/bin/python scripts/warmup.py"""
import os
import sys
import time

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
load_dotenv(os.path.join(ROOT, ".env"))

from inverse_core.clients.world import WorldClient  # noqa: E402
from inverse_core.clients.zetaris import ZetarisClient  # noqa: E402
from inverse_core.ledger import SidecarLedger  # noqa: E402
from inverse_core.team import critic as C  # noqa: E402
from inverse_core.team.build import build  # noqa: E402
from inverse_core.team.lead import COMPOSE_SYSTEM  # noqa: E402


def prefixes(lead):
    yield "lead_plan", lead.plan_lane, lead.plan_system()
    yield "lead_compose", lead.compose_lane, COMPOSE_SYSTEM
    yield "critic", lead.critic.lane, C.SYSTEM
    for name, expert in lead.registry.experts.items():
        system = getattr(expert, "system", None)
        if system:
            yield name, expert.lane, system()


def main():
    lead, ctx = build(ZetarisClient(), SidecarLedger(), WorldClient(), root=ROOT, runs_dir=os.path.join(ROOT, "runs"))
    for who, lane, system in prefixes(lead):
        t0 = time.time()
        try:
            ctx.lanes.client(lane).chat([{"role": "system", "content": system}, {"role": "user", "content": "Reply with the single word ready."}], max_tokens=2)
            print(f"{who:14s} {lane:7s} {len(system) // 3:5d} tok  {time.time() - t0:5.1f} s")
        except Exception as e:
            print(f"{who:14s} {lane:7s} failed: {type(e).__name__}: {str(e)[:120]}")
    print("warm")


if __name__ == "__main__":
    main()
