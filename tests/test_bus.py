"""The agents talk: the message bus, delivery by Atlas, and the ask_expert / post_message / read_messages tools. No model and no network unless a test says so."""
import json
import os

from inverse_core.budget import Budget
from inverse_core.ledger import InMemoryLedger
from inverse_core.team import tools as T
from inverse_core.team.bus import Bus
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lanes import DEFAULTS as NEMOTRON_LANES
from inverse_core.team.lanes import Lanes
from inverse_core.team.lead import Lead
from inverse_core.team.llmcall import Ctx
from inverse_core.team.memory import TeamMemory
from inverse_core.team.registry import Registry
from inverse_core.team.tools import Tools
from inverse_core.trace import Trace

from fakes import crew


def events(ctx, kind):
    return [e for e in ctx.trace.events if e["kind"] == kind]


def make_ctx(tmp_path, script):
    lanes = Lanes(factory=lambda model: FakeLLM(model, script), mapping=dict(NEMOTRON_LANES))
    ctx = Ctx(lanes, Trace(str(tmp_path)), Budget(max_llm_calls=40), zetaris=FakeZetaris(), guard=lambda n: (n, []), equipment=["P-104"])
    ctx.registry = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    return ctx


REASONING = json.dumps({"steps": [{"claim": "product", "calc": "2*3", "expect": 6}], "answer": "6", "confidence": 0.9, "assumptions": []})


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


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_bus_persists_messages_mirrors_them_in_the_trace_and_filters_inboxes(tmp_path):
    trace = Trace(str(tmp_path))
    bus = Bus(trace.dir, trace)
    bus.post("physics", "all", "P-104: ACCEPT, damping up 40%", type="result", task="T1")
    bus.post("critic", "research", "cite the query", type="review", task="T2")
    bus.post("research", "physics", "which dataset did you use?", type="question", task="T2")
    assert [m["to"] for m in bus.inbox("physics")] == ["physics"]                          # its own broadcast is not in its inbox
    assert [m["type"] for m in bus.inbox("research")] == ["result", "review"]
    assert [m["type"] for m in bus.inbox("reasoning")] == ["result"]
    assert [e["type"] for e in trace.events if e["kind"] == "message"] == ["result", "review", "question"]
    assert [m["n"] for m in Bus.load(trace.dir)] == [1, 2, 3] and Bus.load(str(tmp_path / "nowhere")) == []


def test_lead_puts_results_and_reviews_on_the_bus_and_delivers_them_with_the_next_task(tmp_path):
    seen, critic = [], []

    def script(model, messages):
        system, user = messages[0]["content"], messages[-1]["content"]
        if system.startswith("You are the Reasoning expert"):                                   # a retry must not repeat itself verbatim
            again = "REVIEWER SENT THIS BACK" in user
            return json.dumps({"steps": [{"claim": "c", "calc": "2*3", "expect": 6}], "answer": "six is 6, shown as 2*3" if again else "six is 6, as the manual says", "confidence": 0.9, "assumptions": []})
        if system.startswith("You are the Solver"):
            seen.append(user)
            return json.dumps({"answer": "noted", "confidence": 0.6, "assumptions": [], "not_checked": []})
        if system.startswith("You are an adversarial reviewer"):
            critic.append(1)
            return json.dumps({"verdict": "revise", "problems": [{"quote": "as the manual says", "why": "show the arithmetic"}], "reason": "show the arithmetic"}
                              if len(critic) == 1 else {"verdict": "accept", "reason": "fine"})    # the objection quotes unsupported words, so it stands
        raise AssertionError(system[:40])

    ctx = make_ctx(tmp_path, script)
    lead = Lead(ctx, ctx.registry, TeamMemory(InMemoryLedger()))
    t1 = Task("T1", "multiply", "reasoning")
    lead._execute(t1)
    assert t1.status == "done" and t1.attempts == 2
    assert [(m["from"], m["to"], m["type"]) for m in ctx.bus.all()] == [("critic", "reasoning", "review"), ("reasoning", "all", "result")]
    t2 = Task("T2", "take note", "solver")                                                  # no dependency: the result reaches it as a message
    lead._execute(t2)
    assert t2.status == "done" and len(t2.messages) == 1 and t2.messages[0]["text"] == "six is 6, shown as 2*3"
    assert "MESSAGES FROM TEAMMATES" in seen[0] and "six is 6" in seen[0] and "show the arithmetic" not in seen[0]
    assert os.path.exists(os.path.join(ctx.trace.dir, "messages.jsonl"))
    assert [e.get("messages") for e in events(ctx, "delegate")] == [None, None, 1]


def test_ask_expert_consults_another_expert_and_refuses_self_code_reviewers_architects_and_nesting(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            return REASONING
        raise AssertionError(system[:40])

    ctx = make_ctx(tmp_path, script)
    tools = Tools(ctx, ["ask_expert"], owner="solver")
    tools.memory, tools.task_id = TeamMemory(InMemoryLedger()), "T3"
    budget = ExpertBudget(tool_calls=8)
    out = tools.call("ask_expert", {"expert": "reasoning", "question": "What is 2*3?"}, budget, who="solver")
    assert out["expert"] == "reasoning" and out["answer"] == "6" and out["confidence"] == 0.9 and out["evidence"]
    assert [(m["from"], m["to"], m["type"]) for m in ctx.bus.all()] == [("solver", "reasoning", "question"), ("reasoning", "solver", "answer")]
    c = events(ctx, "consult")
    assert len(c) == 1 and c[0]["from"] == "solver" and c[0]["to"] == "reasoning" and c[0]["ok"] is True
    assert "cannot consult itself" in tools.call("ask_expert", {"expert": "solver", "question": "q"}, budget, who="solver")["error"]
    assert "takes tasks only from the lead" in tools.call("ask_expert", {"expert": "vulnerability", "question": "q"}, budget, who="solver")["error"]
    assert "takes tasks only from the lead" in tools.call("ask_expert", {"expert": "architect", "question": "q"}, budget, who="solver")["error"]
    assert "no expert named 'ghost'" in tools.call("ask_expert", {"expert": "ghost", "question": "q"}, budget, who="solver")["error"]
    T._consult.depth = 1
    try:
        assert "one level deep" in tools.call("ask_expert", {"expert": "reasoning", "question": "q"}, budget, who="solver")["error"]
    finally:
        T._consult.depth = 0
    assert budget.tool_calls == 6                                                            # every call, refused or not, is charged


def test_a_consulted_expert_that_fails_is_a_tool_error_not_a_crash(tmp_path):
    def boom(model, messages):
        raise RuntimeError("model exploded")

    ctx = make_ctx(tmp_path, boom)
    tools = Tools(ctx, ["ask_expert"], owner="solver")
    tools.memory = TeamMemory(InMemoryLedger())
    out = tools.call("ask_expert", {"expert": "reasoning", "question": "q"}, ExpertBudget(), who="solver")
    assert "could not answer" in out["error"] and "model exploded" in out["error"]
    assert events(ctx, "consult")[0]["ok"] is False and ctx.bus.all()[-1]["type"] == "answer"


def test_post_message_and_read_messages(tmp_path):
    ctx = make_ctx(tmp_path, lambda m, msgs: "{}")
    budget = ExpertBudget()
    sender = Tools(ctx, ["post_message"], owner="research")
    sender.task_id = "T1"
    assert sender.call("post_message", {"to": "reasoning", "text": "the mass is 12.5 kg"}, budget, who="research") == {"delivered_to": "reasoning", "message": 1}
    assert "no expert named 'nobody'" in sender.call("post_message", {"to": "nobody", "text": "x"}, budget, who="research")["error"]
    reader = Tools(ctx, ["read_messages"], owner="reasoning")
    got = reader.call("read_messages", {}, budget, who="reasoning")["messages"]
    assert got == [{"from": "research", "to": "reasoning", "type": "note", "task": "T1", "text": "the mass is 12.5 kg"}]
    assert Tools(ctx, ["read_messages"], owner="research").call("read_messages", {}, budget, who="research")["messages"] == []


def test_solver_consults_reasoning_inside_its_tool_loop(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            return REASONING
        if system.startswith("You are the Solver"):
            if any(m["role"] == "user" and m["content"].startswith('{"tool_result"') for m in messages):
                return json.dumps({"answer": "The product is 6, as the reasoning expert computed.", "confidence": 0.8, "assumptions": [], "not_checked": []})
            return json.dumps({"tool": "ask_expert", "args": {"expert": "reasoning", "question": "What is 2*3?"}, "why": "a derivation"})
        raise AssertionError(system[:40])

    ctx = make_ctx(tmp_path, script)
    solver = ctx.registry.experts["solver"]
    assert "ask_expert" in solver.tools and "post_message" in solver.tools
    res = solver.run(Task("T1", "What is twice three?", "solver"), TeamMemory(InMemoryLedger()), ctx.registry.budget_for("solver"))
    assert res.answer.startswith("The product is 6") and res.evidence[0]["source"].startswith("ask_expert(")
    assert not any("numbers in the answer" in n for n in res.not_checked)                  # 6 is in the consulted expert's answer
    assert [e["tool"] for e in events(ctx, "tool")] == ["ask_expert"] and events(ctx, "consult")[0]["ok"] is True
    assert [(m["from"], m["to"]) for m in ctx.bus.all()] == [("solver", "reasoning"), ("reasoning", "solver")]


def test_a_task_that_says_ask_the_reasoning_expert_asks_it_by_code(tmp_path):
    def script(model, messages):
        system = messages[0]["content"]
        if system.startswith("You are the Reasoning expert"):
            return json.dumps({"steps": [{"claim": "T = 1/f", "calc": "1/2", "expect": 0.5}], "answer": "The period is 0.5 s.", "confidence": 0.9, "assumptions": []})
        return json.dumps({"answer": "The reasoning expert says the period is 0.5 s.", "confidence": 0.9, "assumptions": [], "not_checked": []})

    ctx, lead = crew(tmp_path, script)
    res = ctx.registry.experts["solver"].run(Task("T1", "Ask the reasoning expert for the period of a 2 Hz oscillation and report the number.", "solver"), lead.memory, ExpertBudget())
    assert events(ctx, "consult_prefetched")[0]["to"] == "reasoning" and res.evidence[0]["source"].startswith("ask_expert(reasoning")
    assert "0.5" in res.answer and events(ctx, "consult")
