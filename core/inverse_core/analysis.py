"""Deterministic INVERSE pipeline: identifiability -> candidates -> fit -> validators -> select -> drift -> verdict.
LLM agents plug in later by supplying `candidates`; they never decide pass/fail."""
from __future__ import annotations

import numpy as np

from . import validators as V
from .adapters import physical
from .inference import drift as D, fit as F, identifiability as I, next_measurement as N, selection as S
from .models import COEF_UNITS, linear
from .validators.validity import regime


def _params(model, f):
    return [{"name": n, "value": float(v), "ci95": [c[0], c[1]], "unit": COEF_UNITS[n]} for n, v, c in zip(model.free, f["theta"], f["ci95"])]


def new_stats():
    return {"fits": 0, "rounds": 1, "skipped_refuted": 0, "llm_calls": 0}


def identify(data, equipment, ledger, mass_known, stats):
    """Step 1, BEFORE any fitting. Returns a UNIDENTIFIABLE verdict or None."""
    m = data["m"]
    t, y0, sigma = data["t"], data["y0"], data["sigma"]
    base = {"dataset_id": data.get("dataset", "unnamed")}
    target = linear(m=m) if mass_known else linear(free_m=True)
    th0 = [m or 1.0, 2.0, 100.0] if not mass_known else [2.0, 100.0]     # nominal point; registry mass may be NULL
    ident = I.check(target, th0, t, y0, sigma, data["u"])
    if ident["identifiable"]:
        return None
    nm = N.rank(target, th0, y0, sigma, float(t[-1]), float(t[1] - t[0]))
    best = nm[0]
    ledger.record(equipment, {"form": target.form() + " [free m]", "status": "unidentifiable", "unresolved": ident["unresolved_directions"]}, "validator", 0.95)
    return {**base, "verdict": "UNIDENTIFIABLE", "model": None,
            "evidence": [{"validator": "identifiability", "passed": False,
                          "detail": f"Jacobian rank {ident['rank']} of {ident['n_params']}; unresolved log-parameter direction(s) {ident['unresolved_directions']} (only ratios are determined); smallest singular-value ratio {ident['singular_value_ratios'][-1]:.2g}"}],
            "tests_failed": ["identifiability"], "not_checked": ["any fit (refused before fitting)"],
            "falsifier": "a fit would not change the answer: parameters move together without changing the data",
            "regime": regime(data), "action": {"type": "next_measurement", "detail": f"{best['experiment']} ({best['needs']})", "ranking": nm},
            "stats": stats, "models_used": []}


def evaluate(data, equipment, ledger, cands, stats, tried=None):
    """Fit + validate each candidate not already refuted (memory) or tried this run. Vetoes are written to the ledger."""
    tried = tried if tried is not None else set()
    refuted = ledger.refuted_forms(equipment)
    t, x, sigma, y0 = data["t"], data["x"], data["sigma"], data["y0"]
    fitted, vetoed = [], []
    for model, th_start in cands:
        form = model.form()
        if form in tried:
            continue
        if form in refuted:
            stats["skipped_refuted"] += 1
            tried.add(form)
            continue
        tried.add(form)
        f = F.fit(model, t, x, sigma, y0, th_start, data["u"], fit_y0=True)    # data["y0"] is only the starting guess
        stats["fits"] += 1
        dfit = dict(data, y0=f["y0"])                                          # validators and rollouts start from the fitted state
        vs = V.run_all(model, f["theta"], dfit)
        failed = [v for v in vs if not v["passed"]]
        aic, bic = S.aic_bic(f["chi2"], f["n"], f["n_fitted"])
        ho = S.heldout_rollout_rmse(model, f["theta"], dfit)
        entry = {"model": model, "fit": f, "validators": vs, "aic": aic, "bic": bic, "heldout_rmse": ho, "failed": failed, "data": dfit}
        if failed:
            vetoed.append(entry)
            ledger.record(equipment, {"form": form, "status": "refuted", "tests_failed": [v["validator"] for v in failed],
                                      "evidence": [v["evidence"] for v in failed], "rmse": f["rmse"], "aic": aic}, "validator", 0.95)
        else:
            fitted.append(entry)
    return fitted, vetoed


def finalize(data, equipment, ledger, fitted, vetoed, stats, baseline=None, extra_evidence=(), models_used=()):
    base = {"dataset_id": data.get("dataset", "unnamed")}
    if not fitted:
        return {**base, "verdict": "REJECT", "model": None,
                "evidence": [{"validator": v["validator"], "passed": False, "detail": v["evidence"]} for e in vetoed for v in e["failed"]],
                "tests_failed": sorted({v["validator"] for e in vetoed for v in e["failed"]}),
                "not_checked": ["models outside the candidate library"], "falsifier": "n/a", "regime": regime(data),
                "action": {"type": "next_measurement", "detail": "widen candidate library or collect more data"},
                "stats": stats, "models_used": list(models_used), "vetoed": [_summ(e) for e in vetoed]}
    best = min(fitted, key=lambda e: (e["bic"], e["heldout_rmse"]))
    model, f = best["model"], best["fit"]
    ledger.record(equipment, {"form": model.form(), "status": "supported", "bic": best["bic"], "heldout_rmse": best["heldout_rmse"]}, "validator", 0.9)
    now = {n: (float(v), float(s)) for n, v, s in zip(model.free, f["theta"], f["sd"])}
    baseline = baseline or ledger.baseline(equipment)
    drifts = D.drift(now, {k: tuple(v) for k, v in baseline.items()}, [n for n in model.free if n in baseline]) if baseline else []
    flagged = [d for d in drifts if d["flagged"]]
    if flagged:
        d = max(flagged, key=lambda z: z["sigmas"])
        action = {"type": "maintenance_flag", "detail": f"{d['param']} {d['direction']} {d['relative_change']*100:+.0f}% vs baseline ({d['sigmas']:.0f} sigma, threshold 3)", "drift": drifts}
    else:
        action = {"type": "none", "detail": "no parameter drift beyond uncertainty" if baseline else "no baseline available", "drift": drifts}
    return {**base, "verdict": "ACCEPT",
            "model": {"form": model.form(), "parameters": _params(model, f), "rmse": f["rmse"], "bic": best["bic"], "heldout_rmse": best["heldout_rmse"],
                      "reduced_chi2": f["chi2_red"], "initial_state": f["y0"]},
            "evidence": [{"validator": v["validator"], "passed": v["passed"], "detail": v["evidence"]} for v in best["validators"]] + list(extra_evidence),
            "tests_failed": [], "not_checked": ["nonlinear damping above the sampled frequency range", "temperature dependence", "forced operation (data is free decay)"],
            "falsifier": "a no-input rollout whose energy rises, or held-out data the model mispredicts beyond noise",
            "regime": regime(data), "action": action, "stats": stats, "models_used": list(models_used),
            "vetoed": [_summ(e) for e in vetoed], "now": {k: list(v) for k, v in now.items()}}


def analyze(data, equipment, ledger, mass_known=True, candidates=None, baseline=None, question=""):
    stats = new_stats()
    un = identify(data, equipment, ledger, mass_known, stats)
    if un:
        return un
    cands = candidates or physical.candidate_library(data, data["m"])
    fitted, vetoed = evaluate(data, equipment, ledger, cands, stats)
    return finalize(data, equipment, ledger, fitted, vetoed, stats, baseline)


def _summ(e):
    return {"form": e["model"].form(), "rmse": e["fit"]["rmse"], "chi2": e["fit"]["chi2"], "aic": e["aic"],
            "theta": dict(zip(e["model"].free, map(float, e["fit"]["theta"]))), "failed": [{"validator": v["validator"], "detail": v["evidence"]} for v in e["failed"]]}
