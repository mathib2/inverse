"""Benchmark the crew on checkable goals (scripts/measure/bench_cases.yaml): run each goal as a mission, check the final answer, and record
how long it took, how many model calls and tokens it cost, and what the reviewer decided. Results land in
docs/evidence/bench/<label>.json so two runs can be compared.

  PYTHONPATH=core .venv/bin/python scripts/measure/bench.py --label baseline [--only arithmetic,registry] [--collaborate auto|on|off] [--parallel 2]
  PYTHONPATH=core .venv/bin/python scripts/measure/bench.py --compare docs/evidence/bench/baseline.json docs/evidence/bench/tuned.json

A case passes when every expected item is in the answer (a number within 1 %, text as a case-insensitive substring) and at least
one task was accepted; it is clean when no task failed. Stop Warden first, or its missions share the CPU with the benchmark."""
import argparse
import json
import os
import re
import statistics
import sys
import time

import yaml
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # scripts/<group>/<this file> -> the checkout
sys.path.insert(0, os.path.join(ROOT, "core"))
load_dotenv(os.path.join(ROOT, ".env"))

NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def found(item, text):
    """A number in the text that is the expected value rounded to the precision the text writes it with (122.6 or 122.63 for
    122.625, never 122.55: a 1 % tolerance once passed 122.55), or a case-insensitive substring."""
    from inverse_core.team.verify import rounds_to
    try:
        want = float(item)
    except ValueError:
        return str(item).lower() in str(text).lower()
    return any(rounds_to(tok.lstrip("-"), abs(want)) for tok in NUMBER.findall(str(text)))


def run_case(case, collaborate, parallel, reset):
    from inverse_core.clients.world import WorldClient
    from inverse_core.clients.zetaris import ZetarisClient
    from inverse_core.ledger import SidecarLedger
    from inverse_core.team.build import build

    events = []
    lead, ctx = build(ZetarisClient(), SidecarLedger(), WorldClient(), root=ROOT, runs_dir=os.path.join(ROOT, "runs"), on_event=events.append)
    if reset:
        lead.memory.reset()
    t0 = time.time()
    rec = {"name": case["name"], "goal": case["goal"], "run_dir": os.path.relpath(ctx.trace.dir, ROOT)}   # relative: no home folder or login name in the evidence
    try:
        plan = lead.plan(case["goal"], collaborate=False)
        if collaborate == "on" or (collaborate == "auto" and len(plan.tasks) >= 3):
            plan = lead.review_plan(plan)
        plan.save(ctx.trace.dir)
        lead.run(plan, ctx.trace.dir, parallel=parallel)
        out = lead.compose(plan, ctx.trace.dir)
        answer = out["answer"]
        rec.update(tasks=[(t.id, t.expert, t.status, t.attempts) for t in plan.tasks], fallback=bool(next((e for e in events if e["kind"] == "compose"), {}).get("fallback")),
                   accepted=sum(1 for t in plan.tasks if t.status == "done"), unfinished=sum(1 for t in plan.tasks if t.status != "done"),
                   plan_by=next((e.get("by") or "model" for e in events if e["kind"] == "plan"), None), answer=answer[:600])
    except Exception as e:                                                    # a crashed mission is a failed case, not a crashed benchmark
        rec.update(tasks=[], fallback=True, accepted=0, unfinished=1, plan_by=None, answer="", error=f"{type(e).__name__}: {str(e)[:200]}")
        answer = ""
    llm = [e for e in events if e["kind"] == "llm"]
    checks = {str(item): found(item, answer) for item in case.get("expect") or []}
    rec.update(duration=round(time.time() - t0, 1), calls=len(llm),
               prompt_tokens=sum(int(e.get("prompt_tokens") or 0) for e in llm), completion_tokens=sum(int(e.get("completion_tokens") or 0) for e in llm),
               latency={}, verdicts=[(e.get("verdict"), e.get("by")) for e in events if e["kind"] == "critic"],
               reasks=sum(1 for e in events if e["kind"] == "critic_reask"), parse_errors=sum(1 for e in events if e["kind"] == "llm_parse_error"),
               checks=checks, expert_used=(not case.get("expert")) or any(t[1] == case["expert"] for t in rec["tasks"]))
    for e in llm:
        rec["latency"].setdefault(str(e.get("agent")).split("_")[0], []).append(e.get("latency_s") or 0)
    rec["pass"] = all(checks.values()) and rec["accepted"] >= 1
    rec["clean"] = rec["pass"] and rec["unfinished"] == 0
    return rec


def totals(cases):
    n = max(1, len(cases))
    return {"cases": len(cases), "pass": sum(c["pass"] for c in cases), "clean": sum(c["clean"] for c in cases),
            "expert_used": sum(bool(c["expert_used"]) for c in cases), "mean_duration": round(sum(c["duration"] for c in cases) / n, 1),
            "total_duration": round(sum(c["duration"] for c in cases), 1), "mean_calls": round(sum(c["calls"] for c in cases) / n, 2),
            "prompt_tokens": sum(c["prompt_tokens"] for c in cases), "completion_tokens": sum(c["completion_tokens"] for c in cases),
            "fallbacks": sum(bool(c["fallback"]) for c in cases), "reasks": sum(c["reasks"] for c in cases), "parse_errors": sum(c["parse_errors"] for c in cases),
            "call_latency_median": round(statistics.median([l for c in cases for ls in c["latency"].values() for l in ls] or [0]), 1)}


def table(result):
    print(f"\n{result['label']}  ({result['provider']}, lanes {result['lanes']})")
    print(f"{'case':12s} {'pass':5s} {'clean':5s} {'s':>6s} {'calls':>5s} {'ptok':>6s} {'ctok':>5s} {'tasks':>5s} {'done':>4s}  checks / verdicts")
    for c in result["cases"]:
        checks = " ".join(f"{k}{'✓' if v else '✗'}" for k, v in c["checks"].items()) or "-"
        print(f"{c['name']:12s} {'yes' if c['pass'] else 'NO':5s} {'yes' if c['clean'] else 'no':5s} {c['duration']:6.0f} {c['calls']:5d} {c['prompt_tokens']:6d} {c['completion_tokens']:5d} "
              f"{len(c['tasks']):5d} {c['accepted']:4d}  {checks} / {' '.join(f'{v}:{b}' for v, b in c['verdicts']) or '-'}" + (f"  ERROR {c['error']}" if c.get("error") else ""))
    t = result["totals"]
    print(f"{'TOTAL':12s} {t['pass']}/{t['cases']} pass, {t['clean']} clean, {t['expert_used']} right expert · {t['total_duration']:.0f} s ({t['mean_duration']:.0f} s per case) · "
          f"{t['mean_calls']} calls per case, median call {t['call_latency_median']} s · {t['prompt_tokens']} prompt + {t['completion_tokens']} completion tokens · "
          f"{t['fallbacks']} answers written by code, {t['reasks']} re-asks, {t['parse_errors']} unreadable replies")


def compare(a, b):
    print(f"\n{'case':12s} {'pass':>9s} {'seconds':>15s} {'calls':>11s} {'prompt tok':>15s}")
    bc = {c["name"]: c for c in b["cases"]}
    for ca in a["cases"]:
        cb = bc.get(ca["name"])
        if not cb:
            continue
        print(f"{ca['name']:12s} {('yes' if ca['pass'] else 'NO') + '→' + ('yes' if cb['pass'] else 'NO'):>9s} {ca['duration']:6.0f} → {cb['duration']:6.0f} {ca['calls']:4d} → {cb['calls']:4d} "
              f"{ca['prompt_tokens']:6d} → {cb['prompt_tokens']:6d}")
    ta, tb = a["totals"], b["totals"]
    print(f"{'TOTAL':12s} pass {ta['pass']}→{tb['pass']} of {ta['cases']} · clean {ta['clean']}→{tb['clean']} · {ta['total_duration']:.0f} s → {tb['total_duration']:.0f} s "
          f"({100 * (tb['total_duration'] - ta['total_duration']) / max(1, ta['total_duration']):+.0f} %) · calls {ta['mean_calls']}→{tb['mean_calls']} per case · "
          f"prompt tokens {ta['prompt_tokens']}→{tb['prompt_tokens']} · median call {ta['call_latency_median']}→{tb['call_latency_median']} s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--cases", default=os.path.join(ROOT, "scripts", "measure", "bench_cases.yaml"))
    ap.add_argument("--only", default="", help="comma-separated case names")
    ap.add_argument("--collaborate", default="auto", choices=["auto", "on", "off"], help="experts review the plan: auto = only when it has 3 or more tasks")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--reset", action="store_true", help="forget shared memory before each case")
    ap.add_argument("--compare", nargs=2, metavar="JSON")
    a = ap.parse_args()
    if a.compare:
        compare(*(json.load(open(p)) for p in a.compare))
        return
    from inverse_core.clients.meterless import provider_id
    from inverse_core.team.lanes import Lanes
    cases = yaml.safe_load(open(a.cases)) or []
    if a.only:
        keep = {s.strip() for s in a.only.split(",")}
        cases = [c for c in cases if c["name"] in keep]
    result = {"label": a.label, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "provider": provider_id(), "lanes": Lanes().mapping,
              "collaborate": a.collaborate, "parallel": a.parallel, "cases": []}
    out_dir = os.path.join(ROOT, "docs", "evidence", "bench")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, re.sub(r"[^A-Za-z0-9_.-]+", "_", a.label) + ".json")
    for case in cases:
        print(f"→ {case['name']}: {case['goal'][:80]}", flush=True)
        rec = run_case(case, a.collaborate, a.parallel, a.reset)
        result["cases"].append(rec)
        result["totals"] = totals(result["cases"])
        with open(path, "w") as f:                                            # written after every case, so a stopped run still leaves data
            json.dump(result, f, indent=1, default=str)
        print(f"   {'pass' if rec['pass'] else 'FAIL'} in {rec['duration']:.0f} s, {rec['calls']} calls, checks {rec['checks']}", flush=True)
    table(result)
    print(f"\nwritten {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    from inverse_core.team import gate
    with gate.marker("bench"):                                                # Warden and Tinker step aside while a person measures
        main()
