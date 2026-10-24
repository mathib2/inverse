"""The UI wording layer: no raw jargon reaches the page, and the plain sentences match the agent's results."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"))
import plain  # noqa: E402

from inverse_core import analysis as A, datasets as D, ledger as L, validators as V  # noqa: E402
from inverse_core.inference.falsify import MENU  # noqa: E402

RAW = ("fit_quality", "falsifier:", "ACCEPT", "UNIDENTIFIABLE", "x''", "llm_", "rmse")


def test_every_physics_check_has_a_plain_name():
    names = [m.__name__.rsplit(".", 1)[-1] for m in V.ALL] + ["falsifier:" + k for k in MENU] + ["identifiability"]
    assert [n for n in names if n not in plain.CHECKS] == []


def test_every_verdict_and_scenario_has_wording():
    assert set(plain.VERDICTS) == {"ACCEPT", "REJECT", "UNIDENTIFIABLE"}
    for s in plain.SCENARIOS.values():
        assert s["equipment"] in s["question"]


def test_wear_sentence_from_a_real_baseline_comparison():
    led = L.InMemoryLedger()
    b = A.analyze(D.p104_baseline(), "P-104", led)
    led.record("P-104", {"form": "BASELINE", "status": "supported",
                         "baseline": {p["name"]: [p["value"], (p["ci95"][1] - p["ci95"][0]) / 3.92] for p in b["model"]["parameters"]}},
               "validator", 0.9)
    v = A.analyze(D.p104_current(), "P-104", led)
    a = plain.action(v)
    assert a["title"] == "Maintenance recommended" and a["body"].startswith("Damping has gone up 40%")
    damping = next(p for p in plain.parameters(v) if p["label"] == "Damping")
    assert damping["value"].endswith("N·s/m") and damping["flagged"] and damping["delta"].startswith("+40%")


def test_refusal_names_the_measurement_in_plain_words():
    v = A.analyze(D.p104_current(), "U", L.InMemoryLedger(), mass_known=False)
    a = plain.action(v)
    assert a["title"] == "What to measure next" and "known force (1 N at 1.5 Hz)" in a["body"]


def test_no_baseline_says_wear_cannot_be_checked_and_the_trap_is_surfaced():
    v = A.analyze(D.trap(), "T", L.InMemoryLedger())
    assert plain.action(v)["title"] == "Wear can't be checked yet"
    assert plain.model_name(v["model"]["form"]) == "Simple spring-and-damper"
    assert plain.model_name(v["vetoed"][0]["form"]) == "Spring-and-damper with extra stiffness and extra damping"
    c = plain.caught(v)
    assert c and "Settles down" in c["body"] and "negative" in c["body"]


def test_no_arrow_for_a_change_that_is_not_real():
    led = L.InMemoryLedger()
    b = A.analyze(D.p104_baseline(), "P", led)
    led.record("P", {"form": "BASELINE", "status": "supported",
                     "baseline": {p["name"]: [p["value"], (p["ci95"][1] - p["ci95"][0]) / 3.92] for p in b["model"]["parameters"]}},
               "validator", 0.9)
    v = A.analyze(D.p104_current(), "P", led)
    stiffness = next(p for p in plain.parameters(v) if p["label"] == "Stiffness")
    assert stiffness["delta"] is None and "no real change" in stiffness["range"]
    assert plain.caught(v) is None


def test_live_progress_lines_are_plain(tmp_path):
    from test_agents import FakeZ, StubLLM
    from inverse_core.orchestrator import Orchestrator
    events = []
    Orchestrator(FakeZ(), L.InMemoryLedger(), StubLLM(), runs_dir=str(tmp_path), on_event=events.append).run("Rig T-200: what governs it?")
    lines = [line for line in map(plain.step, events) if line]
    assert any(line.startswith("Ruled out:") for line in lines) and any("Blocked 1 maintenance note" in line for line in lines)
    assert [line for line in lines if any(r in line for r in RAW)] == []


@pytest.mark.parametrize("exc,title", [("UnknownEquipment", "Which machine?"), ("NightshiftOffline", "The AI went offline"),
                                       ("BudgetExceeded", "The run took too long")])
def test_errors_say_what_to_do(exc, title):
    assert plain.error(type(exc, (Exception,), {})("x"), ["P-104", "T-200"])[0] == title


def test_team_progress_lines_are_plain(tmp_path):
    from test_team import make_ctx, script
    from inverse_core.team.lead import Lead
    from inverse_core.team.memory import TeamMemory
    from inverse_core.team.registry import Registry
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ctx = make_ctx(tmp_path, script)
    lead = Lead(ctx, Registry(ctx, os.path.join(root, "experts"), root), TeamMemory(L.InMemoryLedger()))
    plan = lead.plan("What does P-104 weigh?")
    lead.run(plan, str(tmp_path))
    lead.compose(plan)
    lines = [line for line in map(plain.team_step, ctx.trace.events) if line]
    assert any(line.startswith("T1 sent back by a fixed rule") for line in lines) and any("will be retried" in line for line in lines)
    assert lines[-1].startswith("The lead wrote the final answer")
    assert [line for line in lines if any(r in line for r in RAW)] == []


def test_the_unknown_mass_limit_is_said_plainly():
    title, what = plain.error(NotImplementedError("Mass is unknown but identifiable from this data; fitting with a free mass is not implemented."))
    assert title == "Not supported in this version" and "registry" in what and "NotImplementedError" not in what
