"""Run the INVERSE team. Usage: PYTHONPATH=core .venv/bin/python scripts/admin/run_team.py "goal" [--collaborate] [--reset] [--edit]
--collaborate lets each expert review its own tasks before the run; --edit pauses after planning so you can change plan.json."""
import argparse
import json

from dotenv import load_dotenv

load_dotenv(".env")
from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.ledger import SidecarLedger
from inverse_core.team.build import build
from inverse_core.team.plan import Plan

ap = argparse.ArgumentParser()
ap.add_argument("goal")
ap.add_argument("--collaborate", action="store_true", help="experts review the plan before it runs")
ap.add_argument("--votes", type=int, default=1, help="sample N plans and keep the most common structure (self-consistency)")
ap.add_argument("--parallel", type=int, default=2, help="independent tasks of one plan level run this many at a time")
ap.add_argument("--reset", action="store_true", help="forget team memory first")
ap.add_argument("--edit", action="store_true", help="approve or edit the plan before it runs")
a = ap.parse_args()
lead, ctx = build(ZetarisClient(), SidecarLedger(), WorldClient(), on_event=lambda e: print("  ·", e["kind"], {k: v for k, v in e.items() if k in ("task", "expert", "verdict", "reason", "model", "lane", "attempt", "name", "tool", "changed", "missing")}))
if a.reset:
    print("team memory reset:", lead.memory.reset())
plan = lead.plan(a.goal, collaborate=a.collaborate, votes=a.votes)
path = plan.save(ctx.trace.dir)
if a.edit:
    input(f"Plan written to {path}. Edit it if you want, then press Enter to run (Ctrl-C to cancel)... ")
    plan = Plan.load(path)
lead.run(plan, ctx.trace.dir, parallel=a.parallel)
out = lead.compose(plan, ctx.trace.dir)
print("\n" + out["answer"])
print(json.dumps({"tasks": [(t.id, t.expert, t.status, t.attempts) for t in plan.tasks], "unknown_citations": out["unknown_citations"],
                  "unfinished": out["unfinished"], "models": out["models_used"], "run_dir": ctx.trace.dir}, indent=1, default=str))
