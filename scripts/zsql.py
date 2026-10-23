"""Run one Zetaris SQL statement over REST. Usage: zsql.py "SQL" [limit]"""
import os, sys, uuid, json, requests
from dotenv import load_dotenv

load_dotenv()
sql = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
r = requests.post(
    os.environ["ZETARIS_REST_URL"].rstrip("/") + "/sql-editor/sqls/run",
    headers={
        "Authorization": "Bearer " + os.environ["ZETARIS_API_KEY"],
        "X-Org-ID": os.environ["ZETARIS_ORG_ID"],
        "X-Request-ID": str(uuid.uuid4()),
    },
    json={"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit},
    timeout=180,
)
print("HTTP", r.status_code)
print(r.text[:1500])
