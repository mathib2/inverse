"""The council: the CW/1 wire protocol, zero-cost filing, bounded sessions decided by rule, reversible effects, and the rules
that file proposals from what a run showed. No model and no network: the model is scripted, the data platform is faked."""
import json
import os
import shutil
import time

from inverse_core.budget import Budget
from inverse_core.ledger import InMemoryLedger
from inverse_core.team import council as CO, wire
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lanes import DEFAULTS as NEMOTRON_LANES, Lanes
from inverse_core.team.lead import Lead
from inverse_core.team.llmcall import Ctx
from inverse_core.team.memory import TeamMemory
from inverse_core.team.plan import Plan
from inverse_core.team.registry import Registry
from inverse_core.team.tools import Tools
from inverse_core.trace import Trace
from inverse_core.missions import load_missions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeLLM:
    def __init__(self, model, script):
        self.model, self.script = model, script

    def chat(self, messages, **kw):
        return {"text": self.script(self.model, messages), "model": self.model, "usage": {"total_tokens": 100}, "finish_reason": "stop", "latency_s": 0.0}

    def health(self):
        return {"status": "online", "models": [self.model]}


class FakeZetaris:
    def sql(self, statement, limit=2000):
        return [{"equipment_id": "P-104", "mass_kg": 12.5}]


class FakeWorld:
    def __init__(self):
        self.records = []

    def record(self, *a, **k):
        self.records.append((a, k))
        return {"hypothesis_id": "h", "entities": 1}


def crew(tmp_path, script):
    """A crew bound to a temporary experts folder, so experts.local and council files land in tmp_path."""
    experts = tmp_path / "experts"
    shutil.copytree(os.path.join(ROOT, "experts"), experts)
    lanes = Lanes(factory=lambda model: FakeLLM(model, script), mapping=dict(NEMOTRON_LANES))
    trace = Trace(str(tmp_path / "runs"))
    ctx = Ctx(lanes, trace, Budget(max_llm_calls=40), zetaris=FakeZetaris(), guard=lambda n: (n, []), equipment=["P-104"], root=ROOT)
    ctx.registry = Registry(ctx, str(experts), ROOT)
    ctx.council = CO.Council(str(tmp_path), trace, ctx.bus)
    return ctx, Lead(ctx, ctx.registry, TeamMemory(InMemoryLedger()))


def events(ctx, kind):
    return [e for e in ctx.trace.events if e["kind"] == kind]


# --- the wire -----------------------------------------------------------------------------------------------------------
def test_wire_parses_caps_and_refuses_what_it_cannot_apply():
    p, err = wire.parse_proposal({"k": "cfg", "t": "research", "w": "raise the tool-call budget to 8", "y": "ran out twice", "p": {"budget.tool_calls": 8}, "e": ["T1.E2", "nope"]}, "solver", "runs/x")
    assert err is None and p["id"].startswith("P-") and len(p["id"]) == 8 and p["e"] == ["T1.E2"] and p["by"] == "solver" and p["p"] == {"budget.tool_calls": 8}
    same, _ = wire.parse_proposal({"kind": "cfg", "target": "research", "what": "Raise the tool-call budget to 8!", "patch": {"budget.tool_calls": 8}}, "ada")
    assert same["id"] == p["id"]                                                            # the same idea has the same id, whoever files it
    assert wire.parse_proposal({"k": "magic", "t": "x", "w": "do things"}, "a")[1].startswith("unknown kind")
    assert wire.parse_proposal({"k": "cfg", "t": "research", "w": "more calls", "p": {"budget.tool_calls": 99}}, "a")[1] == "budget.tool_calls must be between 1 and 16"
    assert wire.parse_proposal({"k": "cfg", "t": "research", "w": "give it the scan tool", "p": {"tools+": "scan"}}, "a")[1].startswith("tool 'scan' is not one the council may grant")
    assert wire.parse_proposal({"k": "cfg", "t": "research", "w": "take its data tool away", "p": {"tools-": "run_sql"}}, "a")[0]["p"] == {"tools-": "run_sql"}
    assert wire.parse_proposal({"k": "mission", "t": "data check", "w": "run it twice a day", "p": {"every": 12}}, "a")[0]["t"] == "data_check"
    v, _ = wire.parse_votes({"votes": {"P-000001": "accept", "P-000002": "reject: no evidence", "P-000003": "y|n:reason|r:change|?", "P-000004": "Approve."}}, ["P-000001", "P-000002", "P-000003", "P-000004"])
    assert v["P-000001"] == ("y", "") and v["P-000002"] == ("n", "no evidence") and v["P-000003"] == ("?", "") and v["P-000004"] == ("y", "")
    assert wire.parse_proposal({"k": "cfg", "t": "research", "w": "add a rule", "p": {"enabled": False}}, "a")[1].startswith("patch key 'enabled' is not allowed")
    assert wire.parse_proposal({"k": "note", "t": "shared", "w": "x" * 500}, "a")[0]["w"] == "x" * 140                # too long is truncated, never refused
    assert wire.parse_proposal({"k": "note", "w": "remember that T-200 has no baseline"}, "scout")[0]["t"] == "shared"
    votes, problem = wire.parse_votes({"votes": {"P-000001": "y", "P-000002": "n: no evidence", "P-000003": "r:say which machine", "P-000004": "maybe"}}, ["P-000001", "P-000002", "P-000003", "P-000004", "P-000005"])
    assert problem is None and votes["P-000001"] == ("y", "") and votes["P-000002"] == ("n", "no evidence") and votes["P-000003"] == ("r", "say which machine")
    assert votes["P-000004"] == ("?", "") and votes["P-000005"] == ("?", "")                 # unreadable or missing is an abstention
    assert wire.parse_votes("garbage", ["P-000001"])[0]["P-000001"] == ("?", "")


# --- filing is free and persistent ---------------------------------------------------------------------------------------
def test_filing_dedups_into_backers_persists_in_the_book_and_rides_on_an_accepted_result(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "c", "calc": "2*3", "expect": 6}], "answer": "6", "confidence": 0.9, "assumptions": [],
                               "propose": [{"k": "note", "t": "shared", "w": "the registry mass of P-104 is 12.5 kg", "y": "looked up in T1", "e": ["T1.E1"]},
                                           {"k": "cfg", "t": "research", "w": "raise the tool-call budget to 8", "y": "ran out", "p": {"budget.tool_calls": 8}}, {"k": "x"}]})
        if system.startswith("You are an adversarial reviewer"):
            return json.dumps({"verdict": "accept", "reason": "fine"})
        raise AssertionError(system[:40])

    ctx, lead = crew(tmp_path, script)
    lead._execute(Task("T1", "what is 2*3", "reasoning"))
    c = ctx.council
    assert [(p["k"], p["by"], len(p["backers"])) for p in c.open()] == [("note", "reasoning", 1), ("cfg", "reasoning", 1)]
    assert len(events(ctx, "proposal_filed")) == 2 and not events(ctx, "proposal_dropped")   # the third entry was cut by proposals_of (n=2)
    same = c.file({"k": "cfg", "t": "research", "w": "raise the tool-call budget to 8", "p": {"budget.tool_calls": 8}}, by="solver")
    assert same["backers"] == ["reasoning", "solver"] and events(ctx, "proposal_backed")[0]["support"] == 2
    assert c.file({"k": "cfg", "t": "research", "w": "raise the tool-call budget to 8", "p": {"budget.tool_calls": 8}}, by="solver")["backers"] == ["reasoning", "solver"]
    again = CO.Council(str(tmp_path))                                                        # a new process replays the book
    assert {p["id"] for p in again.open()} == {p["id"] for p in c.open()} and again.proposals[same["id"]]["backers"] == ["reasoning", "solver"]
    assert c.due() == "a proposal has two backers"


def test_the_propose_and_support_tools_file_for_the_owner(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    tools = Tools(ctx, ["propose", "support"], owner="solver")
    out = tools.call("propose", {"k": "mission", "t": "digest", "w": "run the memory digest every 6 hours", "y": "memory grows fast", "p": {"every": 6}}, ExpertBudget(), who="solver")
    assert out["id"].startswith("P-") and out["backers"] == 1 and ctx.council.proposals[out["id"]]["by"] == "solver"
    assert "wire protocol" in tools.call("propose", {"k": "cfg", "t": "research", "w": "x"}, ExpertBudget(), who="solver")["error"]
    assert Tools(ctx, ["support"], owner="research").call("support", {"id": out["id"]}, ExpertBudget(), who="research")["backers"] == 2
    assert "no open proposal" in tools.call("support", {"id": "P-ffffff"}, ExpertBudget(), who="solver")["error"]


# --- sessions: bounded, batched, decided by rule, effects by code ---------------------------------------------------------
def test_a_session_votes_in_batches_decides_by_rule_and_applies_reversible_effects(tmp_path):
    calls = []

    def script(model, messages):
        system, user = messages[0]["content"], messages[-1]["content"]
        agenda = json.loads(user)["agenda"]
        ids = {p["w"]: p["id"] for p in agenda}
        if system.startswith("You are the council's reviewer"):
            calls.append("vera")
            return json.dumps({"votes": {ids["raise the tool-call budget to 8"]: "y", ids["run the digest every 6 hours"]: "y",
                                         ids["remember that T-200 has no baseline"]: "y", ids["use a bigger model"]: "n: no evidence it helps"}})
        if "The council asks whether these changes to YOU" in system:
            calls.append("owner")
            return json.dumps({"votes": {i: "y" for i in ids.values()}})
        raise AssertionError(system[:40])

    ctx, lead = crew(tmp_path, script)
    c, reg, mem, world = ctx.council, lead.registry, lead.memory, FakeWorld()
    a = c.file({"k": "cfg", "t": "research", "w": "raise the tool-call budget to 8", "y": "ran out", "p": {"budget.tool_calls": 8}}, by="solver")
    b = c.file({"k": "mission", "t": "digest", "w": "run the digest every 6 hours", "y": "memory grows", "p": {"name": "digest", "every": 6, "goal": "Summarize what we know."}}, by="human")
    n = c.file({"k": "note", "t": "shared", "w": "remember that T-200 has no baseline", "y": "seen in T2", "e": ["T2.E1"]}, by="research")
    m = c.file({"k": "cfg", "t": "reasoning", "w": "use a bigger model", "y": "would be nicer", "p": {"model_lane": "deep"}}, by="reasoning")
    k = c.file({"k": "code", "t": "repo", "w": "add a retry to the zetaris client", "y": "timeouts"}, by="solver")
    assert c.due() == "5 proposals are open"
    rec = c.session(ctx, reg, mem, world, reason="test")
    assert calls == ["vera", "owner"] and rec["calls"] == 2                                     # Vera once, then the one affected agent that did not file it
    d = {x["id"]: x["d"] for x in rec["decisions"]}
    assert d[a["id"]] == "adopt" and d[b["id"]] == "adopt" and d[n["id"]] == "adopt" and d[m["id"]] == "reject" and d[k["id"]] == "needs_human"
    assert c.proposals[b["id"]]["decision"]["r"] == "Vera yes"                                # a person filed it, so it needed no second backer
    assert reg.configs["research"]["budget"]["tool_calls"] == 8 and os.path.exists(tmp_path / "experts.local" / "research.yaml")   # applied and reloaded
    assert next(x for x in load_missions(str(tmp_path)) if x["name"] == "digest")["every"] == 6
    assert any("T-200 has no baseline" in f["form"] for f in mem.findings())
    assert "add a retry" in open(tmp_path / "council" / "human.md").read()
    assert c.proposals[m["id"]]["decision"]["r"].startswith("Vera: no evidence")
    assert len(world.records) == 5 and world.records[0][0][1] == "council"                     # the World Model holds every decision and vote
    kinds = [e["kind"] for e in ctx.trace.events]
    assert "council_session" in kinds and kinds.count("council_decision") == 5 and "council_done" in kinds
    assert any(msg["from"] == "council" and msg["type"] == "result" for msg in ctx.bus.all())    # adoptions are announced to everyone
    assert c.revert(a["id"], reg) and reg.configs["research"]["budget"]["tool_calls"] == 6 and not os.path.exists(tmp_path / "experts.local" / "research.yaml")
    assert c.proposals[a["id"]]["status"] == "reverted" and c.due() is None


def test_rails_and_abstentions_never_adopt_without_a_vote(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(messages[0]["content"][:30])
        return "not json at all"                                                            # the model cannot be read: an abstention

    ctx, lead = crew(tmp_path, script)
    c, reg, mem = ctx.council, lead.registry, lead.memory
    jump = c.file({"k": "cfg", "t": "research", "w": "raise the tool-call budget to 16", "y": "more", "p": {"budget.tool_calls": 16}}, by="solver")
    forge = c.file({"k": "cfg", "t": "architect", "w": "give the architect a bigger budget", "y": "x", "p": {"budget.tool_calls": 10}}, by="solver")
    note = c.file({"k": "note", "t": "shared", "w": "something worth remembering", "y": "y", "e": ["T1.E1"]}, by="research")
    rec = c.session(ctx, reg, mem, None, reason="asked", by="human")
    d = {x["id"]: x for x in rec["decisions"]}
    assert d[jump["id"]]["d"] == "reject" and "half at most" in d[jump["id"]]["r"]              # by code, no model asked
    assert d[forge["id"]]["d"] == "reject" and "architect" in d[forge["id"]]["r"]
    assert d[note["id"]]["d"] == "defer" and "could not judge" in d[note["id"]]["r"]           # an unreadable reviewer is not a vote
    assert rec["calls"] == 1 and len(calls) == 1 and events(ctx, "council_vote_unreadable")
    assert c.proposals[note["id"]]["defers"] == 1 and c.proposals[note["id"]]["status"] == "deferred"
    c.last_session = 0
    c.session(ctx, reg, mem, None, reason="again", by="human")
    c.last_session = 0
    assert c.proposals[note["id"]]["defers"] == 2 and c.agenda() == [] and c.proposals[note["id"]]["status"] == "expired"   # deferred twice: expired by code


def test_sessions_are_rare_by_rule(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    c = ctx.council
    assert c.due() is None
    p = c.file({"k": "note", "t": "shared", "w": "one lonely note", "y": "y"}, by="research")
    assert c.due() is None and c.due(forced=True) == "asked"                                 # one fresh proposal: nothing happens on its own
    assert c.due(now=time.time() + CO.STALE + 1) == "a proposal has waited a day"
    c.last_session = time.time()
    c.file({"k": "note", "t": "shared", "w": "the second note to remember", "y": "y"}, by="a")
    c.file({"k": "note", "t": "shared", "w": "the third note to remember", "y": "y"}, by="b")
    assert c.due() is None and c.due(now=time.time() + CO.MIN_GAP + 1) == "3 proposals are open"   # at most one session an hour


def test_rules_file_proposals_from_what_a_run_showed(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    c = ctx.council
    plan = Plan("g", [Task("T1", "find it", "research"), Task("T2", "convert", "unit_converter")])
    plan.tasks[0].status, plan.tasks[1].status = "failed", "done"
    cfg = {"name": "unit_converter", "kind": "custom", "role": "Converts units", "system_prompt": "Convert.", "tools": ["calc"], "model_lane": "fast", "budget": {"tool_calls": 6}, "enabled": True}
    ev = [{"kind": "task_failed", "task": "T1", "reason": "budget: tool-call budget 6 exceeded"},
          {"kind": "expert_created", "name": "unit_converter", "config": cfg, "by": "architect"}]
    filed = c.observe(plan, ev, run="runs/20261024-1")
    assert len(filed) == 2
    budget = next(p for p in c.open() if p["k"] == "cfg")
    assert budget["by"] == "rule:budget" and budget["p"] == {"budget.tool_calls": 8} and budget["t"] == "research"
    keep = next(p for p in c.open() if p["k"] == "agent")
    assert keep["by"] == "rule:keep" and keep["p"]["config"]["name"] == "unit_converter"
    assert c.observe(plan, ev, run="runs/20261024-1") == []                                   # the same proposals are not filed twice


def test_self_serving_changes_need_a_second_backer_and_rule_filed_ones_too(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the council's reviewer"):
            agenda = json.loads(messages[-1]["content"])["agenda"]
            return json.dumps({"votes": {p["id"]: "accept" for p in agenda}})
        raise AssertionError(system[:40])

    ctx, lead = crew(tmp_path, script)
    c, reg, mem = ctx.council, lead.registry, lead.memory
    mine = c.file({"k": "cfg", "t": "reasoning", "w": "give myself the deep lane", "y": "harder tasks", "p": {"model_lane": "deep"}}, by="reasoning")
    rule = c.file({"k": "cfg", "t": "research", "w": "raise the tool-call budget to 8", "y": "ran out", "p": {"budget.tool_calls": 8}}, by="rule:budget")
    rec = c.session(ctx, reg, mem, None, reason="asked", by="human")
    d = {x["id"]: x for x in rec["decisions"]}
    assert d[mine["id"]]["d"] == "defer" and "second backer" in d[mine["id"]]["r"] and rec["calls"] == 2    # Vera, and research as the owner of the rule's change
    assert d[rule["id"]]["d"] == "defer" and "second backer" in d[rule["id"]]["r"]
    c.support(rule["id"], "solver")
    c.last_session = 0
    rec = c.session(ctx, reg, mem, None, reason="asked", by="human")
    assert {x["id"]: x["d"] for x in rec["decisions"]}[rule["id"]] == "adopt" and reg.configs["research"]["budget"]["tool_calls"] == 8


def test_prompt_and_tool_grants_and_new_missions_become_task_cards_unless_a_person_filed_them(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: json.dumps({"votes": {}}))
    c, reg, mem = ctx.council, lead.registry, lead.memory
    p1 = c.file({"k": "cfg", "t": "research", "w": "add a sentence to its prompt", "y": "y", "p": {"system_prompt+": "Always cite the row count."}}, by="solver")
    p2 = c.file({"k": "mission", "t": "night_check", "w": "add a night check every hour", "y": "y", "p": {"name": "night_check", "every": 1, "goal": "Check everything."}}, by="solver")
    p3 = c.file({"k": "agent", "t": "helper", "w": "keep the helper agent", "y": "y", "p": {"config": {"name": "helper", "kind": "custom", "role": "r", "tools": ["calc"]}}}, by="solver")
    rec = c.session(ctx, reg, mem, None, reason="asked", by="human")
    d = {x["id"]: x for x in rec["decisions"]}
    assert d[p1["id"]]["d"] == "needs_human" and d[p2["id"]]["d"] == "needs_human" and d[p3["id"]]["d"] == "reject" and rec["calls"] == 0
    cards = open(tmp_path / "council" / "human.md").read()
    assert p1["id"] in cards and p2["id"] in cards and not os.path.exists(tmp_path / "missions.local.yaml")


def test_the_book_survives_a_bad_line_and_a_second_filing_from_another_process(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    c = ctx.council
    p = c.file({"k": "note", "t": "shared", "w": "a note worth keeping", "y": "y", "e": ["T1.E1"]}, by="research")
    with open(c.book_path, "a") as f:
        f.write("{this line was cut off\n")
    other = CO.Council(str(tmp_path))                                                    # another process: same book, its own state
    other.file({"k": "note", "t": "shared", "w": "a note worth keeping", "y": "y"}, by="solver")
    assert other.skipped == 1 and other.proposals[p["id"]]["backers"] == ["research", "solver"]
    assert c.open()[0]["backers"] == ["research", "solver"]                                 # the first process sees the new backer on its next look
