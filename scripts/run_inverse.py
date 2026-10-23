"""End-to-end (deterministic, no LLM): Zetaris join -> pipeline -> H-MEM ledger.  Usage:
   PYTHONPATH=core .venv/bin/python scripts/run_inverse.py [--reset] [--equipment P-104] [--unknown-mass]"""
import argparse, json
from dotenv import load_dotenv
load_dotenv()
from inverse_core import analysis as A
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.ledger import SidecarLedger

ap = argparse.ArgumentParser()
ap.add_argument("--equipment", default="P-104")
ap.add_argument("--reset", action="store_true")
ap.add_argument("--unknown-mass", action="store_true")
a = ap.parse_args()
z, led = ZetarisClient(), SidecarLedger()
if a.reset:
    print("reset: deleted", led.reset(a.equipment), "ledger records")
if not led.baseline(a.equipment):
    b = z.load(a.equipment, "baseline")
    rb = A.analyze(b, a.equipment, led)
    base = {p["name"]: [p["value"], (p["ci95"][1] - p["ci95"][0]) / 3.92] for p in rb["model"]["parameters"]}
    led.record(a.equipment, {"form": "BASELINE", "status": "supported", "baseline": base}, "validator", 0.9)
    print("baseline stored in H-MEM:", {k: round(v[0], 3) for k, v in base.items()})
d = z.load(a.equipment, "current")
r = A.analyze(d, a.equipment, led, mass_known=not a.unknown_mass)
r.pop("vetoed", None)
print(json.dumps({k: r[k] for k in ("verdict", "model", "action", "stats")}, indent=1, default=str)[:2500])
