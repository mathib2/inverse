"""Helpers shared by the tests: a scripted model (FakeLLM), a faked data platform (FakeZetaris), a context (make_ctx), a whole
crew with its own experts folder and council (crew), trace lookups (events), a small repository we own (repo) and a Lead on the
built-in agents (lead_for). Not a test module: pytest does not collect it."""
import os
import shutil

from inverse_core.budget import Budget
from inverse_core.ledger import InMemoryLedger
from inverse_core.team import council as CO
from inverse_core.team.lanes import DEFAULTS as NEMOTRON_LANES, Lanes
from inverse_core.team.lead import Lead
from inverse_core.team.llmcall import Ctx
from inverse_core.team.memory import TeamMemory
from inverse_core.team.registry import Registry
from inverse_core.trace import Trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeLLM:
    """Scripted model: `script(system_prompt_start, user_text) -> str`. Records the model id it was built for."""

    def __init__(self, model, script):
        self.model, self.script, self.calls = model, script, 0

    def chat(self, messages, **kw):
        self.calls += 1
        return {"text": self.script(self.model, messages), "model": self.model, "usage": {"total_tokens": 100}, "finish_reason": "stop", "latency_s": 0.0}

    def health(self):
        return {"status": "online", "models": [self.model]}


class FakeZetaris:
    def __init__(self):
        self.ran = []

    def sql(self, statement, limit=2000):
        self.ran.append(statement)
        return [{"equipment_id": "P-104", "mass_kg": 12.5}]


def make_ctx(tmp_path, script, **kw):
    # The scripted model is addressed by Nemotron route ids whatever MODEL_PROVIDER the machine's .env sets (test_integration loads it).
    lanes = Lanes(factory=lambda model: FakeLLM(model, script), mapping=dict(NEMOTRON_LANES))
    return Ctx(lanes, Trace(str(tmp_path)), Budget(max_llm_calls=40), zetaris=FakeZetaris(), guard=lambda n: (n, []), equipment=["P-104"], **kw)


def events(ctx, kind):
    return [e for e in ctx.trace.events if e["kind"] == kind]


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


def repo(tmp_path):
    """A small 'repository we own': one weak file, one secret, one test file (skipped by the scan)."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import requests\n\ndef run(user_input, url):\n    eval(user_input)\n    return requests.get(url)\n")
    (tmp_path / ".env").write_text("MODEL_API_KEY=not-for-your-eyes\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("exec('1+1')\n")
    return str(tmp_path)


def lead_for(ctx, mem=None):
    return Lead(ctx, Registry(ctx, os.path.join(ROOT, "experts"), ROOT), mem or TeamMemory(InMemoryLedger()))
