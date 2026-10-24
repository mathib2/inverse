"""Planted-scenario evaluation of the deterministic INVERSE pipeline (no LLM, no network; reproducible).

Each scenario plants a known truth with the same generator the demo data comes from, runs `analysis.analyze`
unchanged, and grades the verdict against what was planted. Writes docs/evidence/EVAL.md and eval_results.json.

Usage: PYTHONPATH=core .venv/bin/python scripts/eval_report.py [--seeds 20] [--trap-seeds 80] [--out docs/evidence]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time

import numpy as np

from inverse_core import analysis as A, datasets as D, ledger as L
from inverse_core.inference import identifiability as I
from inverse_core.models import linear


def baseline_of(verdict):
    """The stored-baseline shape: {param: (value, sd)} from a fitted model's 95% intervals."""
    return {p["name"]: (p["value"], (p["ci95"][1] - p["ci95"][0]) / 3.92) for p in verdict["model"]["parameters"]}


def param(verdict, name):
    return next(p for p in verdict["model"]["parameters"] if p["name"] == name)


def covers(verdict, truth):
    """Does each fitted 95% interval contain the planted value?"""
    return {n: param(verdict, n)["ci95"][0] <= truth[n] <= param(verdict, n)["ci95"][1] for n in ("c", "k")}


def rel_err(verdict, truth):
    return {n: abs(param(verdict, n)["value"] - truth[n]) / abs(truth[n]) for n in ("c", "k")}


def wear(seeds, planted_change, sx=0.01, offset=0):
    """Baseline month, then a current month whose damping changed by `planted_change` (0 = no wear). Expect a flag iff wear.
    sx is the sensor noise (the demo data uses 0.01 m on a 1 m release; 0.1 m is a realistic, noisy sensor). `offset` gives
    each scenario its own noise realisations; the current month is analysed on a fresh ledger, as the app does."""
    rows = []
    for s in seeds:
        t0 = time.time()
        b = A.analyze(D.oscillator(c=2.0, seed=1000 + offset + s, sx=sx), "E", L.InMemoryLedger())
        cur = D.oscillator(c=2.0 * (1 + planted_change), seed=2000 + offset + s, sx=sx)
        v = A.analyze(cur, "E", L.InMemoryLedger(), baseline=baseline_of(b)) if b["verdict"] == "ACCEPT" else {"verdict": b["verdict"]}
        flagged = v.get("action", {}).get("type") == "maintenance_flag"
        drift_c = next((d for d in v.get("action", {}).get("drift", []) if d["param"] == "c"), None)
        rows.append({"seed": s, "baseline_verdict": b["verdict"], "verdict": v.get("verdict"), "flagged": flagged,
                     "direction": drift_c["direction"] if drift_c and flagged else None,
                     "sigmas": round(drift_c["sigmas"], 1) if drift_c else None,
                     "coverage": covers(v, cur["truth"]) if v.get("verdict") == "ACCEPT" else None,
                     "rel_err": rel_err(v, cur["truth"]) if v.get("verdict") == "ACCEPT" else None,
                     "conformal": (v["model"].get("conformal") or {}).get("coverage") if v.get("verdict") == "ACCEPT" else None,
                     "seconds": round(time.time() - t0, 2)})
    return rows


def trap(seeds):
    """Noisy, short, weakly damped data: the flexible model often fits better but with negative damping. It must never be accepted."""
    rows = []
    for s in seeds:
        d = D.oscillator(c=0.15, seed=s, n=200, sx=0.04, sv=0.4)
        d["sigma"] = 0.04
        t0 = time.time()
        v = A.analyze(d, "T", L.InMemoryLedger())
        accepted_form = v["model"]["form"] if v["verdict"] == "ACCEPT" else None
        wrong = bool(accepted_form and "a*x^3" in accepted_form and param(v, "c")["value"] < 0)
        bait = [e for e in v.get("vetoed", []) if "a*x^3" in e["form"] and e["theta"].get("c", 0) < 0]
        better_fit = bool(bait and accepted_form and bait[0]["rmse"] < v["model"]["rmse"])
        rows.append({"seed": s, "verdict": v["verdict"], "accepted": accepted_form, "wrong_model_accepted": wrong,
                     "negative_damping_vetoed": bool(bait), "bait_fit_better": better_fit,
                     "vetoed_by": sorted({f["validator"] for e in bait for f in e["failed"]}),
                     "coverage": covers(v, d["truth"]) if v["verdict"] == "ACCEPT" and "a*x^3" not in accepted_form else None,
                     "seconds": round(time.time() - t0, 2)})
    return rows


def refusal(seeds):
    """Free decay with the mass unknown is unidentifiable (only c/m and k/m exist): expect a refusal, with the measurement named.
    The same question with a known forcing input is identifiable, so the refusal is specific, not a blanket no. The check depends on
    the record's shape, not its noise, so each seed varies the shape: length, sampling step, release amplitude and mass."""
    rows = []
    for s in seeds:
        shape = {"n": 200 + 20 * s, "dt": 0.01 * (1 + 0.1 * (s % 3)), "x0": 0.5 + 0.05 * s, "m": 1.0 + 0.1 * (s % 5)}
        d = D.oscillator(seed=3000 + s, **shape)
        t0 = time.time()
        v = A.analyze(d, "U", L.InMemoryLedger(), mass_known=False)
        forced = D.oscillator(seed=3000 + s, u=lambda t: 1.0 * np.sin(2 * np.pi * 1.5 * t), **shape)
        ident = I.check(linear(free_m=True), [shape["m"], 2.0, 100.0], forced["t"], forced["y0"], forced["sigma"], forced["u"])
        rows.append({"seed": s, "verdict": v["verdict"], "refused_before_fitting": v["verdict"] == "UNIDENTIFIABLE" and v["stats"]["fits"] == 0,
                     "next_measurement": v.get("action", {}).get("detail", "")[:80] if v["verdict"] == "UNIDENTIFIABLE" else None,
                     "forced_is_identifiable": ident["identifiable"], "seconds": round(time.time() - t0, 2)})
    return rows


def pct(n, d):
    return f"{100.0 * n / d:.0f}% ({n} of {d})" if d else "n/a"


def summarize(res):
    w, nw, sm, tr, rf = res["wear_40pct"], res["no_wear"], res["small_wear_5pct"], res["trap"], res["refusal"]
    nz, nzn = res.get("noisy_wear_40pct", []), res.get("noisy_no_wear", [])
    acc = [r for r in w + nw + sm if r["verdict"] == "ACCEPT"]
    nacc = [r for r in nz + nzn if r["verdict"] == "ACCEPT"]
    cov_c = sum(r["coverage"]["c"] for r in acc)
    cov_k = sum(r["coverage"]["k"] for r in acc)
    trap_acc = [r for r in tr if r["coverage"]]
    cov_trap = sum(r["coverage"]["c"] and r["coverage"]["k"] for r in trap_acc)
    return {
        "wear flagged when damping rose 40%": pct(sum(r["flagged"] and r["direction"] == "up" for r in w), len(w)),
        "false alarm when nothing changed": pct(sum(r["flagged"] for r in nw), len(nw)),
        "small wear (+5%) flagged": pct(sum(r["flagged"] for r in sm), len(sm)),
        "10x noisier sensor: wear flagged when damping rose 40%": pct(sum(r["flagged"] and r["direction"] == "up" for r in nz), len(nz)),
        "10x noisier sensor: false alarm when nothing changed": pct(sum(r["flagged"] for r in nzn), len(nzn)),
        "10x noisier sensor: median sigmas of the +40% flag (vs clean)": f"{float(np.median([r['sigmas'] for r in nz if r['sigmas'] is not None])):.0f} vs {float(np.median([r['sigmas'] for r in w if r['sigmas'] is not None])):.0f}" if nz and w else "n/a",
        "10x noisier sensor: 95% interval for c contains the planted value": pct(sum(r["coverage"]["c"] for r in nacc), len(nacc)),
        "wrong (negative-damping) model accepted on trap data": pct(sum(r["wrong_model_accepted"] for r in tr), len(tr)),
        "trap data where the bait fit better and was still vetoed": pct(sum(r["bait_fit_better"] for r in tr), len(tr)),
        "trap data with a negative-damping model vetoed": pct(sum(r["negative_damping_vetoed"] for r in tr), len(tr)),
        "trap verdicts": {k: sum(r["verdict"] == k for r in tr) for k in ("ACCEPT", "REJECT", "UNIDENTIFIABLE")},
        "mass unknown: refused before any fit (20 record shapes)": pct(sum(r["refused_before_fitting"] for r in rf), len(rf)),
        "mass unknown but forced: identifiable (same 20 shapes)": pct(sum(r["forced_is_identifiable"] for r in rf), len(rf)),
        "95% interval for c contains the planted value": pct(cov_c, len(acc)),
        "95% interval for k contains the planted value": pct(cov_k, len(acc)),
        "95% intervals (c and k) cover truth on accepted trap fits": pct(cov_trap, len(trap_acc)),
        "90% conformal band: mean coverage of the unseen tail (nominal >=90%)": f"{100 * float(np.mean([r['conformal'] for r in acc if r.get('conformal') is not None])):.0f}%" if any(r.get('conformal') is not None for r in acc) else "n/a",
        "median relative error of c / k on accepted fits": f"{100 * float(np.median([r['rel_err']['c'] for r in acc])):.2f}% / {100 * float(np.median([r['rel_err']['k'] for r in acc])):.3f}%" if acc else "n/a",
        "median seconds per analysis": round(float(np.median([r["seconds"] for r in w + nw + sm + tr + rf])), 2),
    }


def markdown(res, meta):
    s = res["summary"]
    lines = ["# Planted-scenario evaluation (deterministic pipeline, no LLM)", "",
             f"Run {meta['date']} on {meta['machine']} with `scripts/eval_report.py --seeds {meta['seeds']} --trap-seeds {meta['trap_seeds']}` "
             f"({meta['seconds']} s). Every scenario is generated by `core/inverse_core/datasets.py`, the same generator behind the demo data, "
             "with the planted truth written down before `analysis.analyze` runs. The pipeline, thresholds and candidate library are the ones the app uses; "
             "nothing was tuned on these seeds. Failures stay in the denominator.", "",
             "| Measure | Result |", "|---|---|"]
    for k, v in s.items():
        lines.append(f"| {k} | {v if not isinstance(v, dict) else ', '.join(f'{a} {b}' for a, b in v.items())} |")
    lines += ["", "## What each scenario plants", "",
              "- **Wear (+40%)**: baseline month c=2.0 N·s/m, then a month with c=2.8 (the P-104 story). Expect `maintenance_flag`, direction up, well beyond 3σ.",
              "- **No wear**: a second month with c=2.0 and new noise. Any flag is a false alarm.",
              "- **Small wear (+5%)**: c=2.1. Near the 3σ rule's edge at this noise level; reported, not asserted.",
              "- **10x noisier sensor**: the same wear and no-wear months with σ=0.1 m instead of 0.01 m. Intervals must widen (fewer sigmas) without false alarms.",
              "- **Trap**: c=0.15, σ=0.04 m, 200 samples, many seeds (the T-200 story). The 4-parameter model may fit better with negative damping; "
              "the stability and energy validators must veto it every time. `bait fit better` counts the seeds where the trap is actually baited.",
              "- **Refusal**: free decay with unknown mass, over 20 record shapes (length 200-580 samples, step 10-12 ms, release 0.5-1.45 m, mass 1-1.4 kg). "
              "Only ratios are determined, so the agent must refuse before fitting and name the measurement; the same record with a known 1 N, 1.5 Hz "
              "forcing is identifiable, which shows the refusal is specific. (The check depends on the record's shape, not its noise.)",
              "", "## Honest notes", "",
              "- Synthetic data only; the generator and the fitted model family share the same physics, so this measures the decision logic, not real-plant realism.",
              "- Interval coverage below 95% means the Laplace intervals are optimistic on this data; it is reported as measured.",
              "- Per-seed rows are in `eval_results.json`."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--trap-seeds", type=int, default=80)
    ap.add_argument("--out", default="docs/evidence")
    a = ap.parse_args()
    t0 = time.time()
    seeds = list(range(a.seeds))
    res = {"wear_40pct": wear(seeds, 0.40), "no_wear": wear(seeds, 0.0, offset=100), "small_wear_5pct": wear(seeds, 0.05, offset=200),
           "noisy_wear_40pct": wear(seeds, 0.40, sx=0.1, offset=300), "noisy_no_wear": wear(seeds, 0.0, sx=0.1, offset=400),
           "trap": trap(list(range(a.trap_seeds))), "refusal": refusal(seeds)}
    res["summary"] = summarize(res)
    meta = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "machine": platform.platform(),
            "seeds": a.seeds, "trap_seeds": a.trap_seeds, "seconds": round(time.time() - t0, 1)}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "eval_results.json"), "w") as f:
        json.dump({"meta": meta, **res}, f, indent=1, default=str)
    with open(os.path.join(a.out, "EVAL.md"), "w") as f:
        f.write(markdown(res, meta))
    print(json.dumps(res["summary"], indent=1))
    print(f"wrote {a.out}/EVAL.md and eval_results.json in {meta['seconds']} s")


if __name__ == "__main__":
    main()
