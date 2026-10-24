"""The research-backed additions: the closed-form linear solver matches the integrator; the conformal band reports honest
coverage; reviewers' reasons become lessons the expert sees next time; plan voting keeps the majority structure."""
import json
import os

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from test_team import events, make_ctx

from inverse_core import analysis as A, datasets as D, ledger as L, models as M
from inverse_core.inference import conformal as C
from inverse_core.ledger import InMemoryLedger
from inverse_core.team.expert import Task
from inverse_core.team.lead import Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.registry import Registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lsoda(model, theta, t, y0):
    p = model.full(theta)
    sol = solve_ivp(lambda tt, y: model.rhs(tt, y, p, None), (t[0], t[-1]), y0, t_eval=t, rtol=1e-12, atol=1e-14, method="LSODA")
    return sol.y


@pytest.mark.parametrize("c,k", [(2.0, 100.0), (0.0, 100.0), (25.0, 100.0), (20.0, 100.0), (-0.3, 100.0), (2.0, -5.0)])
def test_closed_form_matches_the_integrator_in_every_damping_regime(c, k):
    model, t, y0 = M.linear(m=1.0), np.linspace(0, 2.0, 201), [0.8, -0.2]
    assert M.closed_form(model.full([c, k]))
    exact, num = M.simulate(model, [c, k], t, y0), lsoda(model, [c, k], t, y0)
    assert np.allclose(exact, num, rtol=1e-7, atol=1e-9)
    assert not M.closed_form(M.nonlinear(1.0).full([c, k, 0.1, 0.0]))        # a nonlinear term still integrates
    assert not M.closed_form(model.full([c, k]), u=lambda tt: 1.0)             # so does a forced input


def test_closed_form_overflow_raises_like_a_failed_integration():
    with pytest.raises(RuntimeError, match="integration failed"):
        M.simulate(M.linear(m=1.0), [-50.0, 100.0], np.linspace(0, 100, 50), [1.0, 0.0])


def test_conformal_band_covers_held_out_samples_of_a_correct_model():
    d = D.oscillator(c=2.0, seed=7)
    b = C.band(M.linear(m=1.0), [2.0, 100.0], d)
    assert b["n_fit"] == 200 and b["n_cal"] == 80 and b["n_test"] == 120 and 0 < b["halfwidth"] < 0.05
    assert b["coverage"] >= 0.8                                                # nominal 90%; measured, never asserted at exactly 90
    assert "conformal" in C.describe(b) and C.band(M.linear(m=1.0), [2.0, 100.0], {**d, "t": d["t"][:40], "x": d["x"][:40]}) is None


def test_accept_verdict_carries_the_conformal_band_and_its_plain_name():
    import sys
    sys.path.insert(0, os.path.join(ROOT, "ui"))
    import plain
    v = A.analyze(D.p104_current(), "P-104", L.InMemoryLedger())
    assert v["verdict"] == "ACCEPT" and 0.5 <= v["model"]["conformal"]["coverage"] <= 1.0
    item = next(e for e in v["evidence"] if e["validator"] == "conformal")
    assert item["passed"] and "unseen tail samples" in item["detail"] and plain.check("conformal")[0]


def test_reviewer_reasons_become_lessons_the_expert_sees_next_time(tmp_path):
    seen = []

    def script(model, messages):
        sys, user = messages[0]["content"], messages[-1]["content"]
        if sys.startswith("You are the Reasoning expert"):
            seen.append(user)
            return json.dumps({"steps": [{"claim": "c", "calc": "1+1", "expect": 2}], "answer": f"answer {len(seen)}", "confidence": 0.9, "assumptions": []})
        if sys.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept" if len(seen) > 1 else "revise", "reason": "state the units"})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    mem = TeamMemory(InMemoryLedger())
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), mem)
    lead._execute(Task("T1", "first", "reasoning"))
    assert mem.lessons("reasoning") == ["first: state the units"] and "LESSONS" not in seen[0]
    lead._execute(Task("T2", "second", "reasoning"))
    assert "LESSONS FROM EARLIER REVIEWS" in seen[-1] and "state the units" in seen[-1] and events(ctx, "lessons")[0]["count"] == 1
    assert mem.lessons("research") == []                                        # lessons are per expert


def test_plan_voting_keeps_the_majority_structure(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(messages[0]["content"][:12])
        n = len(calls)
        if n == 2:                                                               # the odd one out: a single research task
            return json.dumps({"tasks": [{"id": "T1", "goal": "mass of P-104", "expert": "research", "depends_on": []}]})
        return json.dumps({"tasks": [{"id": "T1", "goal": "mass of P-104", "expert": "research", "depends_on": []},
                                      {"id": "T2", "goal": "weight", "expert": "reasoning", "depends_on": ["T1"]}]})
    ctx = make_ctx(tmp_path / "runs", script)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    plan = lead.plan("What does P-104 weigh?", votes=3)
    assert [t.expert for t in plan.tasks] == ["research", "reasoning"] and len(calls) == 3
    v = events(ctx, "plan_votes")[0]
    assert v["samples"] == 3 and v["agreement"] == 2 and v["chosen"] == "reasoning:1 research:0" and events(ctx, "plan")[0]["votes"] == 3
