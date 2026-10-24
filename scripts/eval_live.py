"""Live faithfulness evaluation: the demo questions, end to end through Zetaris, Nightshift/Nemotron and H-MEM, repeated.

Grades what a judge would check: the verdict is the same every time, every number the AI wrote appears in the verified
result, every citation in the team answer points at evidence that exists, and how long each run took.
Writes docs/evidence/EVAL_LIVE.md and eval_live.json. Costs real model calls.

Usage: PYTHONPATH=core .venv/bin/python scripts/eval_live.py [--repeats 2] [--team] [--out docs/evidence]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time

from dotenv import load_dotenv
load_dotenv(".env")
from inverse_core.agents.reporter import unverified_numbers
from inverse_core.clients.meterless import MeterlessClient
from inverse_core.clients.world import WorldClient
from inverse_core.clients.zetaris import ZetarisClient
from inverse_core.ledger import SidecarLedger
from inverse_core.orchestrator import Orchestrator
from inverse_core.team.build import build

QUESTIONS = {
    "wear": ("Pump P-104 vibration changed. What governs it now, and has it worn?", "ACCEPT"),
    "trap": ("Rig T-200 was reassembled. What governs its vibration, and has it worn?", "ACCEPT"),
    "unknown": ("Pump P-104: we cannot measure the mass. What governs its vibration?", "UNIDENTIFIABLE"),
}
TEAM_GOAL = "Pump P-104 vibration changed. Has it worn, and what does its registry mass imply for the spring force at 5 mm displacement given the fitted stiffness?"


def single(repeats):
    rows = []
    for key, (q, expected) in QUESTIONS.items():
        for i in range(repeats):
            t0 = time.time()
            try:
                v = Orchestrator(ZetarisClient(), SidecarLedger(), MeterlessClient(), world=WorldClient()).run(q)
                bad = unverified_numbers(v.get("narrative") or "", v)
                rows.append({"scenario": key, "repeat": i + 1, "verdict": v["verdict"], "expected": expected, "as_expected": v["verdict"] == expected,
                             "form": (v.get("model") or {}).get("form"), "numbers_in_narrative_not_in_result": bad,
                             "llm_calls": v["stats"]["llm_calls"], "models": sorted(set(v.get("models_used") or [])),
                             "seconds": round(time.time() - t0, 1), "run_dir": v.get("run_dir")})
            except Exception as e:                                       # a crash is a result too
                rows.append({"scenario": key, "repeat": i + 1, "verdict": f"ERROR {type(e).__name__}", "expected": expected, "as_expected": False,
                             "error": str(e)[:200], "seconds": round(time.time() - t0, 1)})
            print(json.dumps(rows[-1], default=str)[:300], flush=True)
    return rows


def team(goal):
    t0 = time.time()
    lead, ctx = build(ZetarisClient(), SidecarLedger(), WorldClient())
    plan = lead.plan(goal, collaborate=True)
    lead.run(plan, ctx.trace.dir)
    out = lead.compose(plan)
    ev = ctx.trace.events
    return {"goal": goal, "tasks": [(t.id, t.expert, t.status, t.attempts) for t in plan.tasks],
            "citations_valid": f"{len(out['citations'])} of {len(out['citations']) + len(out['unknown_citations'])}",
            "unknown_citations": out["unknown_citations"], "unfinished": out["unfinished"],
            "critic_verdicts": [(e["task"], e["verdict"], e["by"]) for e in ev if e["kind"] == "critic"],
            "retries": sum(e["kind"] == "retry" for e in ev), "plan_reviews": [(e["expert"], e["changed"]) for e in ev if e["kind"] == "plan_review"],
            "models": out["models_used"], "llm_calls": sum(e["kind"] == "llm" for e in ev), "seconds": round(time.time() - t0, 1), "run_dir": ctx.trace.dir}


def markdown(rows, trow, meta):
    ok = sum(r["as_expected"] for r in rows)
    clean = sum(1 for r in rows if r.get("numbers_in_narrative_not_in_result") == [])
    lines = [f"# Live evaluation ({meta['date']})", "",
             f"`scripts/eval_live.py --repeats {meta['repeats']}` on {meta['machine']}: Zetaris, Nightshift and the H-MEM sidecar live, "
             f"{meta['seconds']} s in all. Nothing cached between repeats; H-MEM was not reset, so repeats see the earlier run's memory (as a user would).", "",
             "| Measure | Result |", "|---|---|",
             f"| Verdict as expected | {ok} of {len(rows)} |",
             f"| Narratives whose every number is in the verified result | {clean} of {len(rows)} |",
             f"| Median seconds per run | {sorted(r['seconds'] for r in rows)[len(rows) // 2] if rows else 'n/a'} |",
             f"| Models that served calls | {', '.join(sorted({m for r in rows for m in r.get('models', [])}))} |", "",
             "| Scenario | Repeat | Verdict | Expected | Model form | Unverified numbers | LLM calls | Seconds |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['scenario']} | {r['repeat']} | {r['verdict']} | {r['expected']} | {r.get('form') or '-'} | "
                     f"{r.get('numbers_in_narrative_not_in_result', r.get('error', '-'))} | {r.get('llm_calls', '-')} | {r['seconds']} |")
    if trow:
        lines += ["", "## Team run", "", f"Goal: {trow['goal']}", "",
                  f"- Tasks: {trow['tasks']}", f"- Citations valid: {trow['citations_valid']} (unknown: {trow['unknown_citations']})",
                  f"- Critic verdicts: {trow['critic_verdicts']}; retries: {trow['retries']}", f"- Plan reviews: {trow['plan_reviews']}",
                  f"- Unfinished tasks: {trow['unfinished']}", f"- Models: {trow['models']}; LLM calls: {trow['llm_calls']}; {trow['seconds']} s; trace `{trow['run_dir']}`"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--team", action="store_true")
    ap.add_argument("--out", default="docs/evidence")
    a = ap.parse_args()
    t0 = time.time()
    rows = single(a.repeats)
    trow = team(TEAM_GOAL) if a.team else None
    meta = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "machine": platform.node(), "repeats": a.repeats, "seconds": round(time.time() - t0)}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "eval_live.json"), "w") as f:
        json.dump({"meta": meta, "single": rows, "team": trow}, f, indent=1, default=str)
    with open(os.path.join(a.out, "EVAL_LIVE.md"), "w") as f:
        f.write(markdown(rows, trow, meta))
    print(f"wrote {a.out}/EVAL_LIVE.md in {meta['seconds']} s")


if __name__ == "__main__":
    main()
