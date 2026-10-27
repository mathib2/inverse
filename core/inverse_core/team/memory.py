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

    def add_finding(self, claim, evidence, source="fitter", confidence=0.7, expert="", not_checked=None):
        """A finding and, when its author left something unchecked, those notes, so a summary can say what is still open."""
        return self.ledger.record(self.key, {"form": claim, "status": "supported", "evidence": evidence, "expert": expert,
                                             "not_checked": [str(n)[:200] for n in (not_checked or [])][:4]}, source, confidence)

    def refute(self, claim, reason, source="llm_critic", confidence=0.6, expert=""):
        return self.ledger.record(self.key, {"form": claim, "status": "refuted", "tests_failed": [reason], "expert": expert}, source, confidence)

    def refuted(self):
        return self.ledger.refuted_forms(self.key)

    def refutations(self):
        """Every refuted claim with the reason it was refuted for, oldest first: [{"form", "reason", "expert"}]."""
        return [{"form": r["hypothesis"]["form"], "reason": str((r["hypothesis"].get("tests_failed") or [""])[0]), "expert": r["hypothesis"].get("expert", "")}
                for r in self.ledger.recall(self.key) if r["hypothesis"]["status"] == "refuted"]

    def findings(self):
        return [r["hypothesis"] for r in self.ledger.recall(self.key) if r["hypothesis"]["status"] == "supported"]

    def unchecked(self):
        """What the findings' authors said they did not check, oldest first, each note once."""
        out = []
        for h in self.findings():
            for n in h.get("not_checked") or []:
                if str(n) and str(n) not in out:
                    out.append(str(n))
        return out

    def add_lesson(self, expert, lesson, source="llm_critic", confidence=0.6):
        """A reviewer's reason, kept for the expert it was addressed to."""
        return self.ledger.record(f"team:lessons:{expert}", {"form": str(lesson)[:300], "status": "supported", "kind": "lesson", "expert": expert}, source, confidence)

    def lessons(self, expert, n=3, goal=None):
        """The latest n lessons for an expert, oldest first. With a goal, only lessons from a task like it: a lesson starts with its
        own task's goal, and at least two content words must match. Shown to every task, a review of a summary ("The cube root of
        27 is not 3") primed a plain multiplication, and the benchmark's arithmetic case answered 3."""
        rows = [r["hypothesis"]["form"] for r in self.ledger.recall(f"team:lessons:{expert}") if r["hypothesis"].get("kind") == "lesson"]
        if goal is not None:
            want = _content_words(goal)
            rows = [r for r in rows if len(_content_words(str(r).split("\u00ab", 1)[0]) & want) >= 2]
        return rows[-n:]

    def reset(self):
        reset = getattr(self.ledger, "reset", None)
        return reset(self.key) if reset else 0


_BOILERPLATE = set(("using accepted results from earlier tasks answer this plain words with that this what which their there from into about "
                    "find give show list tell compute count look values report exactly queries return another task whole goal").split())


def _content_words(text):
    """Lower-case words of four letters or more that say what a task is about (P-104, sensor, maintenance), without the phrases every
    planned task shares ("Using the accepted results from the earlier tasks, answer this in plain words")."""
    import re
    return {w for w in re.findall(r"[a-z0-9][a-z0-9_-]{3,}", str(text or "").lower()) if w not in _BOILERPLATE}
