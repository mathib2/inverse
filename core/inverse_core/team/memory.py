"""TeamMemory: findings and refuted claims shared by experts within a run and across runs.
Backed by the existing H-MEM ledger (SidecarLedger) under equipment="team:<scope>", so its trust rules apply:
a refutation written by a deterministic check cannot be overwritten by an LLM claim."""
from __future__ import annotations

from ..ledger import InMemoryLedger


class TeamMemory:
    def __init__(self, ledger=None, scope="shared"):
        self.ledger, self.key = ledger or InMemoryLedger(), "team:" + scope

    def add_finding(self, claim, evidence, source="fitter", confidence=0.7, expert=""):
        return self.ledger.record(self.key, {"form": claim, "status": "supported", "evidence": evidence, "expert": expert}, source, confidence)

    def refute(self, claim, reason, source="llm_critic", confidence=0.6, expert=""):
        return self.ledger.record(self.key, {"form": claim, "status": "refuted", "tests_failed": [reason], "expert": expert}, source, confidence)

    def refuted(self):
        return self.ledger.refuted_forms(self.key)

    def findings(self):
        return [r["hypothesis"] for r in self.ledger.recall(self.key) if r["hypothesis"]["status"] == "supported"]

    def reset(self):
        reset = getattr(self.ledger, "reset", None)
        return reset(self.key) if reset else 0
