"""Zetaris REST client (same contract as smoke_test.py). One SQL join returns samples + sensor sigma/unit + equipment mass."""
from __future__ import annotations

import os
import re
import uuid

import numpy as np
import requests

SAMPLE_VIEWS = {
    "p104-baseline": "obs.p104_baseline_samples",
    "p104-current": "obs.p104_current_samples",
    "trap-current": "obs.trap_current_samples",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _sql_id(value):
    """Identifiers are interpolated into SQL, so only plain IDs are allowed through."""
    if not _SAFE_ID.match(str(value)):
        raise ValueError(f"refusing to build SQL with identifier {value!r}")
    return value


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
        if r.status_code >= 400:                                              # the body names the bad column or table: the agent needs that, not just "400"
            raise requests.HTTPError(f"{r.status_code} {r.reason}: {r.text[:300].strip()}", response=r)
        j = r.json()
        return [dict(zip(j["headers"], row)) for row in j["data"]]

    def dataset_id(self, equipment_id, which="current"):
        col = "current_dataset" if which == "current" else "baseline_dataset"
        rows = self.sql(f"SELECT {col} AS d FROM obs.equipment_table WHERE equipment_id = '{_sql_id(equipment_id)}'")
        return rows[0]["d"]

    def load(self, equipment_id, which="current"):
        """The one SQL join: samples + sensor spec (sigma, unit) + equipment registry (mass). Returns pipeline input."""
        ds = self.dataset_id(equipment_id, which)
        if ds not in SAMPLE_VIEWS:
            raise KeyError(f"no sample view registered for dataset {ds!r} (known: {', '.join(SAMPLE_VIEWS)})")
        rows = self.sql(
            f"SELECT s.t AS t, s.x AS x, s.v AS v, sp.sigma AS sigma, sp.unit AS unit, e.mass_kg AS mass_kg "
            f"FROM {SAMPLE_VIEWS[ds]} s JOIN obs.equipment_table e ON e.equipment_id = '{_sql_id(equipment_id)}' "
            f"JOIN obs.sensors_table sp ON sp.equipment_id = e.equipment_id AND sp.quantity = 'x' ORDER BY s.t")
        t = np.array([float(r["t"]) for r in rows])
        x = np.array([float(r["x"]) for r in rows])
        v = np.array([float(r["v"]) for r in rows])
        m = rows[0]["mass_kg"]
        return {"t": t, "x": x, "v": v, "sigma": float(rows[0]["sigma"]), "unit_x": rows[0]["unit"],
                "m": float(m) if m is not None else None,                  # NULL in the registry means unknown mass
                "y0": [float(x[0]), float(v[0])],                         # starting guess from the data; the fit refines it
                "u": None, "dataset": ds, "equipment_id": equipment_id, "source": "zetaris"}

    def maintenance(self, equipment_id):
        return self.sql(f"SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = '{_sql_id(equipment_id)}' ORDER BY date")
