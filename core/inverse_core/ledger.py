"""Claim ledger with trust rules (the crew's shared memory). Source `validator` (a deterministic check) outranks `fitter` (a tool result)
which outranks any `llm_*` source: a refutation written by a check cannot be overwritten by a later model claim.
Backends: InMemoryLedger (tests) and SidecarLedger (Meterless H-MEM over HTTP)."""
from __future__ import annotations

import requests

TRUST = {"validator": 3, "fitter": 2, "council": 1, "llm_critic": 1, "llm_proposer": 1, "llm_reporter": 1}


class InMemoryLedger:
    def __init__(self):
        self.rows = []

    def _find(self, equipment, form):
        for r in reversed(self.rows):
            if r["equipment"] == equipment and r["hypothesis"]["form"] == form:
                return r
        return None

    def record(self, equipment, hypothesis, source, confidence):
        prev = self._find(equipment, hypothesis["form"])
        if prev and prev["hypothesis"]["status"] == "refuted" and hypothesis["status"] != "refuted" \
                and TRUST.get(source, 0) <= TRUST.get(prev["source"], 0):
            return {"accepted": False, "reason": f"refuted by {prev['source']} (trust {TRUST.get(prev['source'])}); {source} (trust {TRUST.get(source, 0)}) cannot overwrite"}
        self.rows.append({"equipment": equipment, "hypothesis": hypothesis, "source": source, "confidence": confidence})
        return {"accepted": True}

    def recall(self, equipment):
        return [r for r in self.rows if r["equipment"] == equipment]

    def refuted_forms(self, equipment):
        return {r["hypothesis"]["form"] for r in self.recall(equipment) if r["hypothesis"]["status"] == "refuted"}

    def baseline(self, equipment, dataset=None):
        rows = [r for r in self.recall(equipment) if r["hypothesis"].get("baseline")]
        return rows[-1]["hypothesis"]["baseline"] if rows else None


class SidecarLedger(InMemoryLedger):
    """Same trust rules, persisted through the H-MEM sidecar (survives restarts)."""

    def __init__(self, url=None, timeout=10):
        from .clients.sidecars import hmem_url
        super().__init__()
        self.url, self.timeout = url or hmem_url(), timeout

    def record(self, equipment, hypothesis, source, confidence):
        self.rows = self.recall(equipment)  # refresh from H-MEM so trust rules see persisted history
        out = super().record(equipment, hypothesis, source, confidence)
        if out["accepted"]:
            r = requests.post(self.url + "/ledger/hypotheses", timeout=self.timeout, json={
                "equipment": equipment, "hypothesis": hypothesis, "source": source, "confidence": confidence})
            r.raise_for_status()
        return out

    def reset(self, equipment):
        r = requests.post(self.url + "/ledger/reset", json={"equipment": equipment}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["deleted"]

    def recall(self, equipment):
        r = requests.get(self.url + "/ledger/hypotheses", params={"equipment": equipment}, timeout=self.timeout)
        r.raise_for_status()
        return [{"equipment": equipment, "hypothesis": h["hypothesis"], "source": h["source"], "confidence": h["confidence"]}
                for h in r.json()["hypotheses"]]
