import numpy as np
import pytest
import pysindy as ps
from scipy.integrate import solve_ivp

from inverse_core import analysis as A, datasets as D, ledger as L, models as M, validators as V
from inverse_core.inference import fit as F, identifiability as I, drift as DR, sindy as S


def test_oscillator_recovered_with_intervals():
    d = D.p104_current()
    f = F.fit(M.linear(m=1.0), d["t"], d["x"], d["sigma"], d["y0"], [1.0, 80.0])
    for name, val, (lo, hi) in zip(["c", "k"], [2.8, 100.0], f["ci95"]):
        assert lo - 0.5 * (hi - lo) <= val <= hi + 0.5 * (hi - lo), (name, val, lo, hi)  # within ~2 sigma
    assert abs(f["theta"][0] - 2.8) < 0.1 and abs(f["theta"][1] - 100) < 1


def test_lorenz_recovered_by_sindy():
    t = np.arange(0, 10, 0.002)
    sol = solve_ivp(lambda t, x: [10 * (x[1] - x[0]), x[0] * (28 - x[2]) - x[1], x[0] * x[1] - 8 / 3 * x[2]],
                    (0, 10), [-8, 8, 27], t_eval=t, rtol=1e-10, atol=1e-10).y.T
    m = ps.SINDy(optimizer=ps.STLSQ(threshold=0.1), feature_library=ps.PolynomialLibrary(2))
    m.fit(sol, t=0.002)
    c = m.coefficients()
    names = m.get_feature_names()
    idx = {n: i for i, n in enumerate(names)}
    assert abs(c[0][idx["x0"]] + 10) < 0.1 and abs(c[0][idx["x1"]] - 10) < 0.1
    assert abs(c[1][idx["x0"]] - 28) < 0.1 and abs(c[2][idx["x2"]] + 8 / 3) < 0.05


def test_fisher_matrix_symmetric_psd():
    d = D.p104_current()
    J = I.jacobian_log(M.linear(m=1.0), [2.8, 100.0], d["t"], d["y0"], d["sigma"])
    Fm = J.T @ J
    assert np.allclose(Fm, Fm.T)
    assert np.all(np.linalg.eigvalsh(Fm) > -1e-9)


def test_unidentifiable_refused_with_forced_response_suggestion():
    r = A.analyze(D.p104_current(), "T-unid", L.InMemoryLedger(), mass_known=False)
    assert r["verdict"] == "UNIDENTIFIABLE"
    assert r["model"] is None and r["stats"]["fits"] == 0          # refused BEFORE fitting
    assert "forced response" in r["action"]["detail"]
    assert r["action"]["ranking"][0]["identifiable"] is True


def test_units_checker_rejects_inconsistent_equation():
    d = D.p104_current()
    bad = M.OscillatorModel("bad", ["c", "k"], {"m": 1.0})
    bad.units = dict(bad.units, c="N/m")          # c*x' with c in N/m is not a force
    out = V.units.check(bad, [2.0, 100.0], d)
    assert not out["passed"] and "not force" in out["evidence"]
    assert V.units.check(M.linear(m=1.0), [2.0, 100.0], d)["passed"]


def test_trap_better_fit_is_vetoed_by_physics():
    r = A.analyze(D.trap(), "TRAP", L.InMemoryLedger())
    assert r["verdict"] == "ACCEPT" and "a*x^3" not in r["model"]["form"]       # the honest linear model survives
    v = r["vetoed"][0]
    assert v["rmse"] < r["model"]["rmse"] and v["theta"]["c"] < 0               # better fit, wrong damping sign
    assert {f["validator"] for f in v["failed"]} >= {"stability", "energy"}


def test_validator_refutation_cannot_be_overwritten_by_llm():
    led = L.InMemoryLedger()
    led.record("E", {"form": "F1", "status": "refuted"}, "validator", 0.95)
    out = led.record("E", {"form": "F1", "status": "supported"}, "llm_proposer", 0.99)
    assert out["accepted"] is False
    assert led.refuted_forms("E") == {"F1"}


def test_warm_run_uses_fewer_fits_than_cold_run():
    led = L.InMemoryLedger()
    cold = A.analyze(D.trap(), "TRAP", led)
    warm = A.analyze(D.trap(), "TRAP", led)
    assert warm["stats"]["fits"] < cold["stats"]["fits"] and warm["stats"]["skipped_refuted"] >= 1


def test_drift_flagged_beyond_uncertainty_and_not_without():
    led = L.InMemoryLedger()
    b = A.analyze(D.p104_baseline(), "P", led)
    led.record("P", {"form": "BASELINE", "status": "supported", "baseline": {p["name"]: [p["value"], (p["ci95"][1] - p["ci95"][0]) / 3.92] for p in b["model"]["parameters"]}}, "validator", 0.9)
    worn = A.analyze(D.p104_current(), "P", led)
    assert worn["action"]["type"] == "maintenance_flag" and "c up +4" in worn["action"]["detail"]
    same = A.analyze(D.oscillator(c=2.0, seed=5), "P", led)
    assert same["action"]["type"] == "none"
    assert DR.drift({"c": (2.8, 0.02)}, {"c": (2.0, 0.02)}, ["c"])[0]["flagged"]


def test_energy_validator_flags_negative_damping():
    d = D.p104_current()
    out = V.energy.check(M.linear(m=1.0), [-0.5, 100.0], d)
    assert not out["passed"]
