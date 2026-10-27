"""Offline smoke: real CLI/index/retrieval and real agent orchestration, scripted LLM only.

No production services, downloads, H-MEM writes or model inference. Temporary artifacts only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from inverse_core.knowledge import search

CASES = [
    ("mechanics", "Newtonian force acceleration", "Newtonian force"),
    ("beam", "cantilever beam bending stress", "Cantilever beam bending stress"),
    ("thermal", "sensible thermal energy specific heat", "Sensible thermal energy"),
    ("fluids", "laminar pipe pressure drop Darcy", "Laminar pipe pressure drop"),
    ("inverse", "damped oscillator parameter identification", "Damped oscillator parameter identification"),
]


def missions(database, temporary):
    from inverse_core.budget import Budget
    from inverse_core.ledger import InMemoryLedger
    from inverse_core.team.expert import Task
    from inverse_core.team.lanes import Lanes
    from inverse_core.team.lead import Lead
    from inverse_core.team.llmcall import Ctx
    from inverse_core.team.memory import TeamMemory
    from inverse_core.team.plan import Plan
    from inverse_core.team.registry import Registry
    from inverse_core.trace import Trace

    class ScriptedModel:
        model = "scripted-smoke-model"

        def chat(self, messages, **kwargs):
            system = messages[0]["content"]
            if system.startswith("Write the final answer"):
                payload = json.loads(messages[-1]["content"])
                citations = " ".join(f"[{key}]" for result in payload["results"] for key in result["evidence"])
                text = "The nominal bending stress is 45 MPa under the stated cantilever assumptions. " + citations
            elif system.startswith("You are an adversarial reviewer"):
                payload = json.loads(messages[-1]["content"])
                assert any(e.get("reference", {}).get("source_url") for e in payload["evidence"])
                text = {"verdict": "accept", "problems": []}
            elif system.startswith("You are the Reasoning expert"):
                assert "UNTRUSTED DATA" in messages[1]["content"]
                text = {"steps": [{"claim": "nominal rectangular beam stress in MPa", "calc": "6*500*0.3/(0.05*0.02**2)", "unit":"MPa", "expect": 45}],
                        "answer": "The nominal bending stress is 75 MPa under the stated cantilever assumptions.", "confidence": 0.8,
                        "assumptions": ["Linear elasticity, slender beam and ideal fixed support"]}
            elif len(messages) == 2:
                text = {"tool": "engineering_reference_search", "args": {"query": "cantilever beam bending stress"}}
            else:
                assert "UNTRUSTED REFERENCE DATA" in messages[-1]["content"]
                text = {"answer": "Cantilever bending guidance requires an explicit bending axis and elastic assumptions.", "confidence": 0.7}
            return {"text": text if isinstance(text, str) else json.dumps(text), "model": self.model, "usage": {"total_tokens": 100}, "latency_s": 0, "finish_reason": "stop"}

    results = []
    for name, tasks in (("scout-euler-vera-atlas", [Task("T1", "Find reference documentation for cantilever beam bending stress", "research"),
                                                   Task("T2", "Calculate nominal bending stress for a rectangular cantilever: F=500 N, L=0.3 m, b=0.05 m, h=0.02 m. Use linear elasticity and an ideal fixed support.", "reasoning", ["T1"])]),
                        ("ada-vera-atlas", [Task("T1", "Retrieve cantilever beam bending guidance", "solver")])):
        start = time.perf_counter()
        lanes = Lanes(factory=lambda _: ScriptedModel())
        ctx = Ctx(lanes, Trace(str(temporary / name)), Budget(max_llm_calls=10), root=str(ROOT))
        registry = ctx.registry = Registry(ctx, str(ROOT / "experts"), str(ROOT))
        lead = Lead(ctx, registry, TeamMemory(InMemoryLedger()))
        plan = Plan(name, tasks)
        lead.run(plan)
        answer = lead.compose(plan)
        assert all(t.status == "done" for t in tasks), [(t.id, t.status, t.feedback) for t in tasks]
        assert answer["references"] and "https://github.com/mathib2/inverse" in answer["answer"]
        assert lead.memory.findings() == [], "reference guidance must not become validated experience"
        if name.startswith("scout"):
            assert tasks[1].references and "45 MPa" in tasks[1].result["answer"]
            calculated = [e for e in tasks[1].result["evidence"] if e["type"] == "calc"]
            assert len(calculated) == 1 and float(calculated[0]["detail"][2:].split()[0]) == 45.0
            assert "45 MPa" in answer["answer"] and any(key.startswith("T2.E") for key in answer["citations"])
        results.append({"mission": name, "status": "pass", "model": "scripted, no inference",
                        "model_calls": sum(e["kind"] == "llm" for e in ctx.trace.events),
                        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3)})
    return results


def main():
    with tempfile.TemporaryDirectory(prefix="inverse-knowledge-smoke-") as temporary:
        temp = Path(temporary)
        database = temp / "knowledge.sqlite3"
        os.environ["INVERSE_ENGINEERING_ENABLED"] = "1"
        os.environ["INVERSE_ENGINEERING_DB"] = str(database)
        os.environ["INVERSE_EXPERTS_LOCAL"] = str(temp / "experts.local")
        os.environ["INVERSE_PRIORITY"] = ""
        # Check the actual public CLI in two fresh processes, not an in-memory shortcut.
        cli = [sys.executable, str(ROOT / "scripts/admin/engineering_knowledge.py"), "--database", str(database)]
        build = json.loads(subprocess.check_output(cli + ["rebuild"], cwd=ROOT, text=True))
        persisted = json.loads(subprocess.check_output(cli + ["search", "cantilever beam bending stress"], cwd=ROOT, text=True))
        assert build["documents"] == 5 and build["chunks"] == 24 and persisted["results"]
        tracemalloc.start()
        cases, cold, warm = [], [], []
        for name, query, expected in CASES:
            before = time.perf_counter()
            result = search(database, query)
            cold.append((time.perf_counter() - before) * 1000)
            assert result["status"] == "ok" and expected in result["results"][0]["section"], result
            assert result["estimated_tokens"] <= 1000 and len(result["results"]) <= 3
            for _ in range(20):
                before = time.perf_counter()
                assert search(database, query)["results"] == result["results"]
                warm.append((time.perf_counter() - before) * 1000)
            cases.append({"case": name, "top_section": result["results"][0]["section"], "estimated_tokens": result["estimated_tokens"]})
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert search(database, "unicorn telepathy zqxwy")["results"] == []
        print(json.dumps({"status": "pass", "index": build, "index_bytes": database.stat().st_size,
                          "retrieval_cases": cases, "top1_retrieval": "5/5",
                          "cold_median_ms": round(statistics.median(cold), 3),
                          "warm_median_ms": round(statistics.median(warm), 3),
                          "python_retrieval_allocation_peak_bytes": peak,
                          "missions": missions(database, temp),
                          "limitations": "Scripted-model smoke, not live-model answer accuracy or inference speed. tracemalloc excludes native SQLite allocations."}, indent=2))


if __name__ == "__main__":
    main()
