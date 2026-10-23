"""INVERSE orchestrator. LLM agents (Proposer/Critic/Reporter) propose and explain; solvers + validators decide.
Flow: health -> Planner -> Zetaris join -> guard -> identifiability (refuse early) -> rounds [SINDy+Proposer -> fit -> validate]
      -> Critic falsification -> verdict -> Reporter. Every step is traced; every veto goes to the H-MEM ledger."""
from __future__ import annotations

from . import analysis as A
from .adapters import physical
from .agents import critic, guard, planner, proposer, reporter
from .budget import Budget
from .clients.meterless import NightshiftOffline
from .ledger import InMemoryLedger
from .trace import Trace


class Orchestrator:
    def __init__(self, zetaris, ledger, llm, runs_dir="runs", max_rounds=3, max_llm_calls=10):
        self.z, self.ledger, self.llm, self.runs_dir = zetaris, ledger, llm, runs_dir
        self.max_rounds, self.max_llm_calls = max_rounds, max_llm_calls

    def _ensure_baseline(self, eq, trace):
        if self.ledger.baseline(eq):
            return
        if self.z.dataset_id(eq, "baseline") in ("none", "", None):
            trace.event("no_baseline", equipment=eq)
            return
        b = self.z.load(eq, "baseline")
        r = A.analyze(b, eq, InMemoryLedger())            # scratch ledger: baseline run must not pollute refutation memory
        base = {p["name"]: [p["value"], (p["ci95"][1] - p["ci95"][0]) / 3.92] for p in r["model"]["parameters"]}
        self.ledger.record(eq, {"form": "BASELINE", "status": "supported", "baseline": base}, "validator", 0.9)
        trace.event("baseline_stored", equipment=eq, baseline=base, dataset=b["dataset"])

    def run(self, question):
        trace, budget = Trace(self.runs_dir), Budget(self.max_rounds, self.max_llm_calls)
        h = self.llm.health()
        trace.event("nightshift_health", **{k: v for k, v in h.items() if k != "models"})
        if h["status"] != "online":
            raise NightshiftOffline(f"Nightshift is {h['status']}: {h.get('detail', '')}. Start Nightshift on the laptop and reopen the SSH tunnel.")
        models_used = []

        def note_model(m):
            if m and m not in models_used:
                models_used.append(m)

        eqs = [r["equipment_id"] for r in self.z.sql("SELECT equipment_id FROM obs.equipment_table")]
        plan = planner.plan(question, eqs)
        eq = plan["equipment"]
        trace.event("plan", **plan)
        data = self.z.load(eq, "current")
        trace.event("zetaris_join", equipment=eq, dataset=data["dataset"], rows=len(data["t"]), sigma_x=data["sigma"], mass_kg=data["m"])
        notes, blocked = guard.sanitize(self.z.maintenance(eq))
        trace.event("injection_guard", blocked=blocked, notes=len(notes))
        self._ensure_baseline(eq, trace)
        stats = A.new_stats()

        verdict = A.identify(data, eq, self.ledger, plan["mass_known"], stats)
        if verdict:
            trace.event("refused_before_fitting", reason="identifiability", action=verdict["action"]["detail"])
        else:
            verdict = self._search(data, eq, notes, stats, trace, budget, note_model)
        text, bad, m = reporter.report(self.llm, trace, budget, verdict, question)
        note_model(m)
        stats["llm_calls"] = budget.llm_calls
        verdict.update({"question": question, "equipment": eq, "narrative": text, "narrative_unverified_numbers": bad,
                        "models_used": models_used, "injection_blocked": blocked, "run_dir": trace.dir,
                        "nightshift": {"status": h["status"], "route": self.llm.model}})
        verdict.pop("vetoed_entries", None)
        trace.event("verdict", verdict=verdict["verdict"], action=verdict["action"]["type"], stats=stats)
        return verdict

    def _search(self, data, eq, notes, stats, trace, budget, note_model):
        from .validators.validity import regime
        tried, fitted, vetoed, feedback = set(), [], [], ""
        for r in range(1, self.max_rounds + 1):
            stats["rounds"] = r
            budget.rounds = r
            cands = physical.candidate_library(data, data["m"]) if r == 1 else []     # SINDy proposes (tool, no LLM)
            refuted = self.ledger.refuted_forms(eq)
            prop, m = proposer.propose(self.llm, trace, budget, regime(data), data["sigma"], notes, refuted, feedback, data["m"])
            note_model(m)
            cands += prop
            f, v = A.evaluate(data, eq, self.ledger, cands, stats, tried)
            fitted += f
            vetoed += v
            for e in v:
                trace.event("veto", form=e["model"].form(), rmse=e["fit"]["rmse"], failed=[x["validator"] for x in e["failed"]])
            for e in f:
                trace.event("survivor", form=e["model"].form(), bic=e["bic"], rmse=e["fit"]["rmse"])
            if not v:
                break                                                   # a round with no new veto: stop (stuck detector otherwise forces another round)
            feedback = "; ".join(f"{e['model'].form()} vetoed by {[x['validator'] for x in e['failed']]}" for e in v)
        extra, tests_done = [], set()
        while fitted:                                                   # Critic: try to break the best survivor
            best = min(fitted, key=lambda e: (e["bic"], e["heldout_rmse"]))
            if budget.llm_calls >= self.max_llm_calls - 1:
                break
            res, reason, m = critic.critique(self.llm, trace, budget, best, data, tests_done)
            note_model(m)
            tests_done.add(res["validator"].split(":")[1])
            if res["passed"]:
                extra.append({"validator": res["validator"], "passed": True, "detail": res["evidence"] + f" (Critic: {reason})"})
                break
            best["failed"] = [res]
            vetoed.append(best)
            fitted.remove(best)
            self.ledger.record(eq, {"form": best["model"].form(), "status": "refuted", "tests_failed": [res["validator"]], "evidence": [res["evidence"]]}, "validator", 0.95)
            trace.event("veto", form=best["model"].form(), failed=[res["validator"]], by="critic_test")
        return A.finalize(data, eq, self.ledger, fitted, vetoed, stats, extra_evidence=extra)
