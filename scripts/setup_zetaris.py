"""Create the Zetaris objects for INVERSE: runs zetaris/sql/*.sql one statement at a time. Idempotent:
statements that fail because the object already exists are reported as SKIP.
Usage: PYTHONPATH=core .venv/bin/python scripts/setup_zetaris.py"""
import glob, os
from dotenv import load_dotenv
load_dotenv(".env")
from inverse_core.clients.zetaris import ZetarisClient

z = ZetarisClient()
ok = skip = 0
for f in sorted(glob.glob("zetaris/sql/0*.sql")):
    for line in open(f):
        s = line.strip().rstrip(";")
        if not s or s.startswith("--"):
            continue
        try:
            z.sql(s, limit=5)
            ok += 1
            print("OK   ", s[:80])
        except Exception as e:
            skip += 1
            print("SKIP ", s[:60], "-", str(e)[:70])
print(f"done: {ok} applied, {skip} skipped (already exist or failed; check SKIP lines)")
print("check:", z.sql("SELECT COUNT(*) AS n FROM obs.p104_current_samples")[0])
