"""The shape every agent shares (docs/AGENT_STRUCTURE.md): the record, the budget, evidence required, the system prompt. No model and no network unless a test says so."""
import glob
import os

import pytest
import yaml

from inverse_core.budget import BudgetExceeded
from inverse_core.team.crew import CREW
from inverse_core.team.expert import ExpertBudget, ExpertResult, NoEvidence, require_evidence
from inverse_core.team.registry import KINDS

from fakes import crew

FIELDS = ["name", "callsign", "kind", "role", "system_prompt_file", "tools", "model_lane", "budget", "enabled"]


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_agent_exposes_the_system_prompt_a_warm_up_sends(tmp_path):
    from inverse_core.team import critic as CR
    from inverse_core.team.sql_guard import SCHEMA
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    assert "Experts:" in lead.plan_system() and "research" in lead.plan_system()
    assert SCHEMA in lead.registry.experts["research"].system() and "steps" in lead.registry.experts["reasoning"].system()
    assert "TOOLS:" in lead.registry.experts["solver"].system() and CR.SYSTEM.startswith("You are an adversarial reviewer")


def test_every_expert_record_has_the_same_fields_and_a_prompt_that_exists():
    files = sorted(glob.glob(os.path.join(ROOT, "experts", "*.yaml")))
    assert len(files) >= 5
    for f in files:
        with open(f, encoding="utf-8") as fh:
            c = yaml.safe_load(fh)
        missing = [k for k in FIELDS if k not in c]
        assert not missing, f"{os.path.basename(f)} lacks {missing}"
        assert c["kind"] in KINDS and c["model_lane"] in ("fast", "deep", "critic") and isinstance(c["tools"], list)
        assert os.path.exists(os.path.join(ROOT, c["system_prompt_file"])), f"{c['name']}: prompt file missing"
        assert isinstance(c["budget"], dict) and c["budget"], f"{c['name']}: no budget"
        assert c["name"] in CREW and CREW[c["name"]]["name"] == c["callsign"]


def test_every_built_in_agent_has_a_probe_set():
    import importlib.util
    spec = importlib.util.spec_from_file_location("probe", os.path.join(ROOT, "scripts", "measure", "probe.py"))
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    for name in ("EULER", "SCOUT", "ADA", "SENTINEL", "ATLAS", "VERA"):
        assert getattr(probe, name), name
    assert callable(probe.probe_forge) and callable(probe.probe_atlas) and callable(probe.probe_vera)


def test_expert_budget_enforced():
    b = ExpertBudget(tool_calls=1, tokens=150)
    b.charge_tool()
    with pytest.raises(BudgetExceeded):
        b.charge_tool()
    b2 = ExpertBudget(tokens=150)
    b2.charge_tokens({"total_tokens": 100})
    with pytest.raises(BudgetExceeded):
        b2.charge_tokens({"total_tokens": 100})


def test_result_without_evidence_is_refused():
    with pytest.raises(NoEvidence):
        require_evidence(ExpertResult("claim", []))
