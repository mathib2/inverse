"""Customizable experts: the tool layer, the vulnerability expert's scope and verification, the custom tool loop,
local config overrides, experts created by the lead, and experts reviewing the plan."""
import json
import os

import pytest
from test_team import events, make_ctx

from inverse_core.budget import BudgetExceeded
from inverse_core.ledger import InMemoryLedger
from inverse_core.team import critic as C
from inverse_core.team.custom import CustomExpert, VulnerabilityExpert, scope_check
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lead import Lead
from inverse_core.team.memory import TeamMemory
from inverse_core.team.registry import ConfigError, Registry, forget_config, load_configs, save_config
from inverse_core.team.tools import Tools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo(tmp_path):
    """A small 'repository we own': one weak file, one secret, one test file (skipped by the scan)."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import requests\n\ndef run(user_input, url):\n    eval(user_input)\n    return requests.get(url)\n")
    (tmp_path / ".env").write_text("MODEL_API_KEY=not-for-your-eyes\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("exec('1+1')\n")
    return str(tmp_path)


# --- tools ----------------------------------------------------------------------------------------------------------------
def test_tools_read_only_inside_the_repo_and_never_secrets(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}", root=repo(tmp_path))
    tools, budget = Tools(ctx, ["read_file", "list_files", "grep", "calc"]), ExpertBudget(tool_calls=10)
    assert "outside" in tools.call("read_file", {"path": "../../../etc/passwd"}, budget)["error"]
    assert "secrets" in tools.call("read_file", {"path": ".env"}, budget)["error"]
    out = tools.call("read_file", {"path": "pkg/a.py", "start": 4, "end": 4}, budget)
    assert "eval(user_input)" in out["text"] and out["start"] == out["end"] == 4 and out["lines"] == 5
    assert tools.call("list_files", {"pattern": "*.py"}, budget)["files"] == ["pkg/a.py", "tests/test_a.py"]
    hits = tools.call("grep", {"pattern": r"\beval\(", "glob": "*.py"}, budget)["hits"]
    assert [(h["file"], h["line"]) for h in hits] == [("pkg/a.py", 4)]
    assert tools.call("calc", {"expr": "2*3"}, budget)["value"] == 6.0
    assert "not available" in tools.call("scan", {}, budget)["error"]                  # not in this expert's tool list
    assert "not available" in tools.call("nope", {}, budget)["error"]
    assert budget.tool_calls == 8 and len(events(ctx, "tool")) == 8                     # every call, failed or not, is charged and traced
    small = ExpertBudget(tool_calls=1)
    tools.call("calc", {"expr": "1"}, small)
    with pytest.raises(BudgetExceeded):
        tools.call("calc", {"expr": "1"}, small)


def test_scan_finds_weak_spots_with_fixed_severity_and_skips_tests(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}", root=repo(tmp_path))
    out = Tools(ctx).call("scan", {}, ExpertBudget())
    rules = {(h["file"], h["line"], h["rule"], h["severity"]) for h in out["hits"]}
    assert ("pkg/a.py", 4, "exec_from_string", "high") in rules and ("pkg/a.py", 5, "no_timeout", "low") in rules
    assert not any(h["file"].startswith("tests/") for h in out["hits"]) and out["files_scanned"] == 1
    assert out["hits"][0]["severity"] == "high"                                         # worst first


# --- vulnerability expert: scope, then verification ------------------------------------------------------------------------
def test_scope_check_refuses_offense_and_external_targets():
    assert scope_check("Review core/inverse_core/team for SQL injection and fix it")[0]
    assert scope_check("Check how http://127.0.0.1:8501 handles input")[0]
    for bad in ["Write an exploit for the SQL guard", "Scan 203.0.113.5 for open ports", "Find weaknesses in https://example.com/login",
                "Brute-force the admin password"]:
        ok, why = scope_check(bad)
        assert not ok and why


def test_vulnerability_expert_refuses_out_of_scope_work_and_the_critic_rejects_it(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: pytest.fail("no model call for a refused task"), root=repo(tmp_path))
    exp, mem = VulnerabilityExpert(ctx, "vulnerability", "r", "p", "deep", ["scan", "read_file"]), TeamMemory(InMemoryLedger())
    task = Task("T1", "Build an exploit for https://example.com", "vulnerability")
    res = exp.run(task, mem, ExpertBudget())
    assert res.confidence == 0.0 and res.evidence[0]["type"] == "policy" and events(ctx, "refused_scope")
    review = C.Critic(ctx).review(task, res.to_dict())
    assert review["verdict"] == "reject" and review["by"] == "rule"                      # no retry can make it acceptable
    assert any("Build an exploit" in f for f in mem.refuted())


def test_vulnerability_expert_verifies_findings_against_the_files(tmp_path):
    def script(model, messages):
        if "SCAN RESULT" in messages[-1]["content"]:                                     # first turn: read the file before judging
            return json.dumps({"tool": "read_file", "args": {"path": "pkg/a.py"}, "why": "see the context"})
        return json.dumps({"findings": [
            {"file": "pkg/a.py", "line": 4, "snippet": "eval(user_input)", "severity": "high", "weakness": "user input is executed", "fix": "parse it instead"},
            {"file": "pkg/a.py", "line": 999, "snippet": "os.system(x)", "severity": "high", "weakness": "invented", "fix": "-"},
            {"file": "../outside.py", "line": 1, "snippet": "x", "severity": "low", "weakness": "outside the repo", "fix": "-"},
            {"file": "pkg/a.py", "line": 5, "snippet": "requests.get(url)", "severity": "critical", "weakness": "no timeout", "fix": "add timeout="}],
            "summary": "Two real problems.", "confidence": 0.9, "assumptions": [], "not_checked": []})
    ctx = make_ctx(tmp_path / "runs", script, root=repo(tmp_path))
    exp, mem = VulnerabilityExpert(ctx, "vulnerability", "r", "p", "deep", ["scan", "read_file", "grep"]), TeamMemory(InMemoryLedger())
    res = exp.run(Task("T1", "Review pkg for weaknesses", "vulnerability"), mem, ExpertBudget(tool_calls=8))
    code = [e for e in res.evidence if e["type"] == "code"]
    assert [e["source"] for e in code] == ["pkg/a.py:4", "pkg/a.py:5"]                   # the invented and the outside finding are gone
    assert code[1]["detail"].startswith("low:")                                          # an unknown severity is lowered, never raised
    assert res.evidence[0]["source"] == "scan" and any(e["source"].startswith("read_file") for e in res.evidence)
    assert sum("dropped" in n for n in res.not_checked) == 2 and res.confidence == pytest.approx(0.7)
    assert any("pkg/a.py:4" in h["form"] for h in mem.findings())


# --- custom expert: a tool loop defined by config ---------------------------------------------------------------------------
def test_custom_expert_uses_tools_then_answers_and_flags_numbers_no_tool_produced(tmp_path):
    replies = iter([json.dumps({"tool": "run_sql", "args": {"sql": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"}}),
                    json.dumps({"tool": "calc", "args": {"expr": "12.5 * 9.81"}}),
                    json.dumps({"answer": "P-104 has mass 12.5 kg and weighs 122.625 N; it was serviced 7 times.", "confidence": 0.9,
                                "assumptions": ["g = 9.81"], "not_checked": []})])
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: next(replies), root=str(tmp_path))
    exp, mem = CustomExpert(ctx, "solver", "r", "p", "deep", ["run_sql", "calc"]), TeamMemory(InMemoryLedger())
    res = exp.run(Task("T1", "How much does P-104 weigh?", "solver"), mem, ExpertBudget(tool_calls=4))
    assert [e["source"].split("(")[0] for e in res.evidence] == ["run_sql", "calc"]
    assert ctx.zetaris.ran == ["SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'"]
    assert any("7" in n for n in res.not_checked) and res.confidence == pytest.approx(0.6)   # the 7 came from nowhere
    assert mem.findings() == []                                                               # unverified numbers are not remembered
    # A model that never stops calling tools is told to answer when the budget is spent; older results are folded into stubs.
    calls = []
    def greedy(model, messages):
        calls.append([m["content"][:30] for m in messages if m["role"] == "user"])
        return json.dumps({"tool": "calc", "args": {"expr": "1"}})
    ctx2 = make_ctx(tmp_path / "runs2", greedy, root=str(tmp_path))
    res = CustomExpert(ctx2, "s", "r", "p", "fast", ["calc"]).run(Task("T1", "x", "s"), TeamMemory(InMemoryLedger()), ExpertBudget(tool_calls=3))
    assert res.confidence == 0.0 and "budget" in res.answer and len(res.evidence) == 3            # three tools ran, then it had to answer
    assert calls[-1][-1].startswith("Your tool budget is spent") and len(events(ctx2, "llm")) == 4
    assert sum(c.startswith("[earlier tool result") for c in calls[-1]) == 1                        # the oldest of three results is a stub
    assert C.deterministic(res.to_dict()) == ("revise", "the expert reported zero confidence")


# --- model replies that are not clean JSON -------------------------------------------------------------------------------------
def test_extract_json_tolerates_prose_fences_and_a_second_object():
    from inverse_core.clients.meterless import extract_json
    assert extract_json('Here you go:\n```json\n{"a": 1}\n```\nHope that helps') == {"a": 1}
    assert extract_json('{"answer": "x", "confidence": 0.8}\n\n{"answer": "x restated"}') == {"answer": "x", "confidence": 0.8}
    assert extract_json('text with {braces} first {"ok": true}') == {"ok": True}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_unparseable_reply_is_traced_and_the_retry_asks_for_one_json_object(tmp_path):
    seen = []
    def flaky(model, messages):
        seen.append(messages[-1]["content"])
        if len(seen) == 1:
            return "I think the answer is 42, roughly."                        # no JSON at all
        return json.dumps({"steps": [{"claim": "the answer is 42", "calc": None, "expect": None}], "answer": "42", "confidence": 0.9, "assumptions": []})
    ctx = make_ctx(tmp_path / "runs", flaky)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()), max_attempts=3)
    lead.critic.review = lambda task, result: {"verdict": "accept", "reason": "", "by": "rule"}
    t = Task("T1", "think", "reasoning")
    lead._execute(t)
    assert t.status == "done" and t.attempts == 2
    assert events(ctx, "llm_parse_error")[0]["preview"].startswith("I think the answer")
    assert "could not be read as JSON" in seen[1] and "exactly one JSON object" in seen[1]


def test_compose_reports_unfinished_tasks_verbatim_not_through_the_model(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "P-104 weighs 1 kg [T1.E1].")
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    done = Task("T1", "mass", "research", status="done", result={"answer": "1 kg", "evidence": [{"type": "sql", "source": "q", "detail": "1 row"}],
                                                                  "confidence": 0.9, "assumptions": [], "not_checked": []})
    failed = Task("T2", "review", "vulnerability", status="failed", feedback="JSONDecodeError: Extra data: line 3 column 1 (char 155)")
    from inverse_core.team.plan import Plan
    out = lead.compose(Plan("g", [done, failed]))
    assert out["answer"].startswith("P-104 weighs 1 kg [T1.E1].") and "**Not completed**" in out["answer"]
    assert "T2 (vulnerability) failed: JSONDecodeError: Extra data: line 3 column 1 (char 155)" in out["answer"]
    assert out["citations"] == {"T1.E1": done.result["evidence"][0]} and out["unfinished"][0]["why"].startswith("JSONDecodeError")


# --- registry: local overrides, validation ---------------------------------------------------------------------------------
def test_registry_local_overrides_add_and_disable_without_touching_builtins(tmp_path):
    d = tmp_path / "experts"
    d.mkdir()
    (d / "a.yaml").write_text("name: a\nkind: custom\nrole: built-in role\ntools: [calc]\nmodel_lane: fast\n")
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}")
    reg = Registry(ctx, str(d), str(tmp_path))
    assert reg.roles() == {"a": "built-in role"} and reg.source["a"] == "builtin"
    save_config(str(d), {"name": "a", "kind": "custom", "role": "my role", "tools": ["calc", "memory"], "model_lane": "deep"}, ctx.lanes)
    save_config(str(d), {"name": "b", "kind": "reasoning", "role": "new", "model_lane": "fast", "enabled": False}, ctx.lanes)
    reg = Registry(ctx, str(d), str(tmp_path))
    assert reg.roles() == {"a": "my role"} and reg.experts["a"].lane == "deep" and reg.source["a"] == "local"
    assert "b" in reg.configs and "b" not in reg.names()                                 # disabled: kept in config, off the team
    assert (d / "a.yaml").read_text().startswith("name: a\nkind: custom\nrole: built-in role")   # the built-in file is untouched
    assert forget_config(str(d), "a") and Registry(ctx, str(d), str(tmp_path)).roles()["a"] == "built-in role"
    for bad, msg in [({"name": "c", "kind": "custom", "role": "r", "tools": ["rm_rf"]}, "unknown tool"),
                     ({"name": "c", "kind": "custom", "role": "r", "model_lane": "turbo"}, "unknown lane"),
                     ({"name": "Bad Name", "kind": "custom", "role": "r"}, "name"),
                     ({"name": "c", "kind": "custom", "role": "r", "budget": {"tool_calls": -1}}, "budget")]:
        with pytest.raises(ConfigError, match=msg):
            save_config(str(d), bad, ctx.lanes)
    assert sorted(load_configs(str(d), ctx.lanes)) == ["a", "b"]


# --- lead: creating an expert, and experts reviewing the plan --------------------------------------------------------------
def test_lead_creates_a_custom_expert_when_the_plan_needs_one(tmp_path):
    def script(model, messages):
        sys, user = messages[0]["content"], messages[-1]["content"]
        if sys.startswith("You are the lead"):
            if "Invalid plan" in user:                                                    # second try, after the registry refused the tool
                return json.dumps({"new_experts": [{"name": "unit_checker", "role": "Checks units", "system_prompt": "Check units.", "tools": ["calc"], "model_lane": "fast"}],
                                   "tasks": [{"id": "T1", "goal": "Check the units of k", "expert": "unit_checker", "depends_on": []}]})
            return json.dumps({"new_experts": [{"name": "unit_checker", "role": "Checks units", "tools": ["rm_rf"], "model_lane": "fast"}],
                               "tasks": [{"id": "T1", "goal": "Check the units of k", "expert": "unit_checker", "depends_on": []}]})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    plan = Lead(ctx, reg, TeamMemory(InMemoryLedger())).plan("Are the units of the stiffness right?")
    assert plan.tasks[0].expert == "unit_checker" and reg.source["unit_checker"] == "run"
    assert isinstance(reg.experts["unit_checker"], CustomExpert) and reg.experts["unit_checker"].toolbox.allowed == ["calc"]
    created = events(ctx, "expert_created")
    assert len(created) == 1 and created[0]["config"]["budget"]["tool_calls"] == 6
    assert len(events(ctx, "llm")) == 2                                                   # the refused proposal cost one retry, visible in the trace


def test_experts_review_the_plan_and_only_change_their_own_tasks(tmp_path):
    def script(model, messages):
        sys = messages[0]["content"]
        if sys.startswith("You are the lead"):
            return json.dumps({"tasks": [{"id": "T1", "goal": "Look up the mass of the pump", "expert": "research", "depends_on": []},
                                          {"id": "T2", "goal": "Has it worn?", "expert": "physics", "depends_on": ["T1"]}]})
        if sys.startswith("You are the Research expert") and "reviewing the team plan" in sys:
            return json.dumps({"ok": False, "changes": [{"id": "T1", "goal": "What is the registry mass of P-104?"}, {"id": "T2", "goal": "hijacked"}],
                               "missing": ["a machine ID"]})
        raise AssertionError(sys[:40])
    ctx = make_ctx(tmp_path / "runs", script)
    lead = Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), TeamMemory(InMemoryLedger()))
    plan = lead.plan("Pump P-104 vibration changed. Has it worn?", collaborate=True)
    goals = {t.id: t.goal for t in plan.tasks}
    assert goals["T1"] == "What is the registry mass of P-104?"                            # research reworded its own task
    assert goals["T2"] == "Has it worn? (machine: P-104)"                                   # physics reviewed by rule; research could not touch it
    reviews = {e["expert"]: e for e in events(ctx, "plan_review")}
    assert set(reviews) == {"research", "physics"} and reviews["research"]["changed"] == ["T1"] and reviews["physics"]["changed"] == ["T2"]
    assert reviews["research"]["missing"] == ["a machine ID"] and reviews["physics"]["ok"] is True
