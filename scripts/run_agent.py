"""Run the full INVERSE agent. Usage: PYTHONPATH=core .venv/bin/python scripts/run_agent.py "question" [--reset EQUIPMENT]"""
import argparse, json
from dotenv import load_dotenv
load_dotenv(".env")
from inverse_core.clients.meterless import MeterlessClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.ledger import SidecarLedger
from inverse_core.clients.world import WorldClient
from inverse_core.orchestrator import Orchestrator

ap = argparse.ArgumentParser()
ap.add_argument("question")
ap.add_argument("--reset", metavar="EQUIPMENT")
a = ap.parse_args()
led = SidecarLedger()
if a.reset:
    print("reset: deleted", led.reset(a.reset), "ledger records")
v = Orchestrator(ZetarisClient(), led, MeterlessClient(), world=WorldClient()).run(a.question)
print(json.dumps({k: v.get(k) for k in ("verdict", "equipment", "model", "action", "tests_failed", "stats", "models_used", "injection_blocked", "run_dir", "world_model", "prior_refutations")}, indent=1, default=str)[:3500])
print("VETOED:", [(x["form"][:40], round(x["rmse"], 4), [f["validator"] for f in x["failed"]]) for x in v.get("vetoed", [])])
print("NARRATIVE:", v["narrative"], "| unverified numbers:", v["narrative_unverified_numbers"])
