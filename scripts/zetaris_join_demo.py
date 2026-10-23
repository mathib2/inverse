"""Show the Zetaris join feeding the pipeline (demo step 2). Run from repo root: PYTHONPATH=core .venv/bin/python scripts/zetaris_join_demo.py"""
from dotenv import load_dotenv
load_dotenv()
from inverse_core.clients.zetaris import ZetarisClient
z = ZetarisClient()
d = z.load("P-104", "current")
print(f"dataset={d['dataset']} rows={len(d['t'])} sigma_x={d['sigma']} {d['unit_x']} mass={d['m']} kg  (sigma and mass come from Zetaris specs)")
for r in z.maintenance("P-104"):
    print(r["date"], r["record_id"], r["note"][:80])
