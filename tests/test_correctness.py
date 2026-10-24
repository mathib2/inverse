"""Regression tests for the correctness fixes: fitted initial state, goodness-of-fit gate, honest
intervals, real held-out split, planner refusal, reporter number check, Critic menu."""
import numpy as np
import pytest

from inverse_core import analysis as A, datasets as D, ledger as L, models as M
from inverse_core.agents import critic, planner, reporter
from inverse_core.inference import fit as F, selection as S
from inverse_core.inference.falsify import MENU
from inverse_core.validators import fit_quality


def test_wrong_release_guess_does_not_buy_a_fake_nonlinear_model():
    """Released from 0.8 m, but the pipeline is told 1.0 m. Before the fix the agent ACCEPTED a cubic
    model (a=28.6) with damping biased -12%; now the initial state is fitted and the linear model wins."""
    d = dict(D.oscillator(c=2.8, seed=2, x0=0.8), y0=[1.0, 0.0])
    r = A.analyze(d, "Y", L.InMemoryLedger())
    assert r["verdict"] == "ACCEPT" and "a*x^3" not in r["model"]["form"]
    c = next(p for p in r["model"]["parameters"] if p["name"] == "c")
    assert c["ci95"][0] <= 2.8 <= c["ci95"][1]
    assert abs(r["model"]["initial_state"][0] - 0.8) < 0.02


def test_fit_quality_vetoes_structured_misfit_and_passes_a_good_fit():
    d = D.p104_current()
    bad = fit_quality.check(M.linear(m=1.0), [2.8, 80.0], d)              # wrong stiffness: residual is a beat, not noise
    assert not bad["passed"] and "structured" in bad["evidence"]
    assert fit_quality.check(M.linear(m=1.0), [2.8, 100.0], d)["passed"]


def test_noise_above_spec_widens_intervals_instead_of_vetoing():
    d = D.oscillator(c=2.8, seed=7, sx=0.02)
    d["sigma"] = 0.01                                                     # the spec understates the noise 2x
    f = F.fit(M.linear(m=1.0), d["t"], d["x"], d["sigma"], d["y0"], [1.0, 80.0], fit_y0=True)
    assert 3.0 < f["chi2_red"] < 5.5
    out = fit_quality.check(M.linear(m=1.0), f["theta"], dict(d, y0=f["y0"]))
    assert out["passed"] and "white" in out["evidence"]
    g = F.fit(M.linear(m=1.0), d["t"], d["x"], 0.02, d["y0"], [1.0, 80.0], fit_y0=True)     # the true sigma
    assert f["sd"][0] == pytest.approx(g["sd"][0], rel=0.25)             # Birge-scaled sd matches the true-sigma sd


def test_heldout_refits_on_the_head_only():
    """theta is only a warm start: the head is refitted, so the score does not depend on it
    (before the fix it scored the full-data fit on its own tail)."""
    d = D.p104_current()
    a = S.heldout_rollout_rmse(M.linear(m=1.0), [2.8, 100.0], d)
    b = S.heldout_rollout_rmse(M.linear(m=1.0), [2.5, 95.0], d)
    assert a == pytest.approx(b, rel=1e-3) and a < 2 * d["sigma"]


@pytest.mark.parametrize("q,eq,known", [
    ("We never weighed pump P-104. What governs it?", "P-104", False),
    ("P-104 mass is a mystery to us", "P-104", False),
    ("Pump P-999 is shaking, what governs it?", None, True),
    ("Pump P-1040 is shaking", None, True),
    ("We don't know why P-104 shakes", "P-104", True),
    ("p104 vibration changed", "P-104", True),
    ("Pump P-104 vibration changed. What governs it now, and has it worn?", "P-104", True)])
def test_planner_whole_ids_and_mass_phrasings(q, eq, known):
    p = planner.plan(q, ["P-104", "T-200"])
    assert p["equipment"] == eq and p["mass_known"] is known


def test_orchestrator_refuses_unknown_equipment(tmp_path):
    from test_agents import FakeZ, StubLLM
    from inverse_core.orchestrator import Orchestrator
    llm = StubLLM()
    with pytest.raises(planner.UnknownEquipment, match="T-200"):
        Orchestrator(FakeZ(), L.InMemoryLedger(), llm, runs_dir=str(tmp_path)).run("Pump P-999 is shaking")
    assert llm.seen == []                                                 # refused before any model call


def test_reporter_number_check_ignores_ids_dates_and_conventions():
    verdict = {"model": {"parameters": [{"value": 2.8, "ci95": [2.76, 2.84]}]}}
    text = "Pump P-104 (record 2026-10-08.) has c=2.8 within its 95% interval, flagged at 3 sigma."
    assert reporter.unverified_numbers(text, verdict) == []
    assert reporter.unverified_numbers("damping rose to 9.9", verdict) == ["9.9"]


def test_critic_stops_cleanly_when_a_candidate_faced_every_test():
    assert critic.critique(None, None, None, None, None, tried_tests=set(MENU)) is None
