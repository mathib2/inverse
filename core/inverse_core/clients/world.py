"""Meterless World Model (via the Node sidecar): shared entities with stable IDs. Equipment, dataset, hypothesis and
validator_result entities are linked; writes are idempotent (content-addressed IDs)."""
import time

import requests


class WorldClient:
    def __init__(self, url=None, timeout=10):
        from .sidecars import hmem_url
        self.url, self.timeout = url or hmem_url(), timeout

    def record(self, run_id, equipment, dataset, hypothesis, validator_results, source="validator"):
        r = requests.post(self.url + "/world/record", timeout=self.timeout, json={
            "run_id": run_id, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "equipment": equipment, "dataset": dataset,
            "source": source, "hypothesis": hypothesis,
            "validator_results": [{"validator": v["validator"], "passed": v["passed"], "evidence": v["evidence"]} for v in validator_results]})
        r.raise_for_status()
        return r.json()

    def summary(self, equipment=None):
        r = requests.get(self.url + "/world/summary", params={"equipment": equipment} if equipment else {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()
