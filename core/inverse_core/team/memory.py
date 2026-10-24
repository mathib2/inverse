"""TeamMemory: findings and refuted claims shared by experts within a run and across runs, plus lessons.
Backed by the existing H-MEM ledger (SidecarLedger) under equipment="team:<scope>", so its trust rules apply:
a refutation written by a deterministic check cannot be overwritten by an LLM claim.
Lessons (Reflexion, Shinn et al. 2023): when the Critic sends an expert's work back, the reason is kept under
"team:lessons:<expert>" and shown to that expert on its next tasks, so the team learns from review instead of repeating it."""
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

    def add_lesson(self, expert, lesson, source="llm_critic", confidence=0.6):
        """A reviewer's reason, kept for the expert it was addressed to."""
        return self.ledger.record(f"team:lessons:{expert}", {"form": str(lesson)[:300], "status": "supported", "kind": "lesson", "expert": expert}, source, confidence)

    def lessons(self, expert, n=3):
        """The latest n lessons for an expert, oldest first."""
        rows = [r["hypothesis"]["form"] for r in self.ledger.recall(f"team:lessons:{expert}") if r["hypothesis"].get("kind") == "lesson"]
        return rows[-n:]

    def reset(self):
        reset = getattr(self.ledger, "reset", None)
        return reset(self.key) if reset else 0
