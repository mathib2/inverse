"""Zetaris REST client (same contract as smoke_test.py). One SQL join returns samples + sensor sigma/unit + equipment mass."""
from __future__ import annotations

import os
import uuid

import numpy as np
import requests

SAMPLE_VIEWS = {
    "p104-baseline": "obs.p104_baseline_samples",
    "p104-current": "obs.p104_current_samples",
    "trap-current": "obs.trap_current_samples",
}


class ZetarisClient:
    def __init__(self, url=None, org=None, key=None, timeout=180):
        self.url = (url or os.environ["ZETARIS_REST_URL"]).rstrip("/")
        self.org = org or os.environ.get("ZETARIS_ORG_ID", "1")
        self.key = key or os.environ["ZETARIS_API_KEY"]
        self.timeout = timeout

    def sql(self, statement, limit=2000):
        r = requests.post(self.url + "/sql-editor/sqls/run", timeout=self.timeout,
                          headers={"Authorization": "Bearer " + self.key, "X-Org-ID": self.org, "X-Request-ID": str(uuid.uuid4())},
                          json={"queryId": str(uuid.uuid4()), "sql": statement, "source": "SqlEditor", "limit": limit})
        r.raise_for_status()
        j = r.json()
        return [dict(zip(j["headers"], row)) for row in j["data"]]

    def dataset_id(self, equipment_id, which="current"):
        col = "current_dataset" if which == "current" else "baseline_dataset"
        rows = self.sql(f"SELECT {col} AS d FROM obs.equipment_table WHERE equipment_id = '{equipment_id}'")
        return rows[0]["d"]

    def load(self, equipment_id, which="current"):
        """The one SQL join: samples + sensor spec (sigma, unit) + equipment registry (mass). Returns pipeline input."""
        ds = self.dataset_id(equipment_id, which)
        rows = self.sql(
            f"SELECT s.t AS t, s.x AS x, s.v AS v, sp.sigma AS sigma, sp.unit AS unit, e.mass_kg AS mass_kg "
            f"FROM {SAMPLE_VIEWS[ds]} s JOIN obs.equipment_table e ON e.equipment_id = '{equipment_id}' "
            f"JOIN obs.sensors_table sp ON sp.equipment_id = e.equipment_id AND sp.quantity = 'x' ORDER BY s.t")
        t = np.array([float(r["t"]) for r in rows])
        x = np.array([float(r["x"]) for r in rows])
        v = np.array([float(r["v"]) for r in rows])
        return {"t": t, "x": x, "v": v, "sigma": float(rows[0]["sigma"]), "unit_x": rows[0]["unit"], "m": float(rows[0]["mass_kg"]),
                "y0": [1.0, 0.0], "u": None, "dataset": ds, "equipment_id": equipment_id, "source": "zetaris"}

    def maintenance(self, equipment_id):
        return self.sql(f"SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = '{equipment_id}' ORDER BY date")
