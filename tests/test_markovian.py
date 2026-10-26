"""Meterless Markovian for long reviews: the client's marker helpers, the chunked review with a scripted engine and model,
and the real vendored reference engine over HTTP (skipped when npx or vendor/markovian is missing)."""
import json
import os
import shutil
import signal
import subprocess
import time

import pytest
import requests

from inverse_core.budget import BudgetExceeded
from inverse_core.clients.markovian import checkpoint, content_of, ensure_marker, MarkovianClient
from inverse_core.ledger import InMemoryLedger
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.memory import TeamMemory
from inverse_core.team.vulnerability import VulnerabilityExpert

import tempfile
from fakes import events, make_ctx, repo


class FakeMarkovian:
    """Scripted engine: one prompt per step, keeps the carryover the model wrote, finishes on [TASK_COMPLETE]."""

    def __init__(self):
        self.texts, self.usages, self.started = [], [], None

    def start(self, goal, mode="RESEARCH", chunk_config=None, memory_context="", attachments=()):
        self.started = {"goal": goal, "mode": mode, "chunk_config": chunk_config, "memory_context": memory_context}
        return {"run_id": "fake", "done": False, "step": 1, "prompt": f"User Request: {goal}", "carryover": ""}

    def step(self, run_id, text, usage=None):
        self.texts.append(text)
        self.usages.append(usage or {})
        if "[TASK_COMPLETE]" in text:
            return {"run_id": run_id, "done": True, "status": "completed", "chunks": [{"id": i + 1} for i in range(len(self.texts))],
                    "estimated": {"tokens_used": 1, "tokens_saved": 0, "efficiency_percent": 0, "label": "estimated"},
                    "measured": {"prompt_tokens": sum(u.get("prompt_tokens", 0) for u in self.usages), "completion_tokens": 0, "calls": len(self.texts)}}
        co = text.split("[STATE_CHECKPOINT]")[-1].strip()
        return {"run_id": run_id, "done": False, "step": len(self.texts) + 1, "prompt": f"Continuing. [CARRYOVER STATE]\n{co}\n\nContinue.", "carryover": co}


def repo2(tmp_path):
    root = repo(tmp_path)
    (tmp_path / "pkg" / "b.py").write_text("import os\n\ndef run(cmd):\n    os.system(cmd)\n")
    return root


@pytest.fixture()
def markovian_server():
    side = os.path.join(ROOT, "services", "meterless-sidecar")
    if not shutil.which("npx") or not os.path.isdir(os.path.join(side, "vendor", "markovian")):
        pytest.skip("npx or vendor/markovian missing")
    state, port = tempfile.mkdtemp(), "8197"
    p = subprocess.Popen(["npx", "tsx", "markovian/serve.ts"], cwd=side, env={**os.environ, "MARKOVIAN_PORT": port, "SIDECAR_STATE": state},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            requests.get(url + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        os.killpg(p.pid, signal.SIGKILL)
        pytest.skip("markovian service did not start")
    yield url
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_marker_helpers_follow_the_spec():
    assert checkpoint("a", "b", "c", "d").startswith("[STATE_CHECKPOINT]\nCOMPLETED: a\nREMAINING: b")
    assert checkpoint("a", "b", "c", "d", final=True) == "[TASK_COMPLETE]"
    assert content_of('{"x": 1}\n[STATE_CHECKPOINT]\nCOMPLETED: a') == '{"x": 1}'
    assert content_of('{"x": 1}\n[TASK_COMPLETE]') == '{"x": 1}'
    assert ensure_marker('{"x": 1}', final=False, completed="f1", remaining="f2").endswith("COMPLETED: f1\nREMAINING: f2\nDECISIONS: \nCONTEXT: ")
    assert ensure_marker('{"x": 1}\n[TASK_COMPLETE]', final=True) == '{"x": 1}\n[TASK_COMPLETE]'   # exactly one marker per chunk


def test_long_review_runs_one_bounded_chunk_per_file_through_markovian(tmp_path):
    prompts = []

    def script(model, messages):
        user = messages[-1]["content"]
        prompts.append(user)
        if "pkg/a.py" in user.split("[WORKING SET")[-1][:60]:
            return (json.dumps({"findings": [{"file": "pkg/a.py", "line": 4, "snippet": "eval(user_input)", "severity": "high", "weakness": "input executed", "fix": "parse it"}],
                                "summary": "a reviewed"}) + "\n[STATE_CHECKPOINT]\nCOMPLETED: pkg/a.py\nREMAINING: pkg/b.py\nDECISIONS: 1 finding\nCONTEXT: scan")
        return json.dumps({"findings": [{"file": "pkg/b.py", "line": 4, "snippet": "os.system(cmd)", "severity": "high", "weakness": "shell from input", "fix": "subprocess list"}],
                           "summary": "b reviewed"})                        # forgets the marker: the host appends [TASK_COMPLETE]
    ctx = make_ctx(tmp_path / "runs", script, root=repo2(tmp_path))
    fake = FakeMarkovian()
    ctx.markovian = fake
    exp, mem = VulnerabilityExpert(ctx, "vulnerability", "r", "p", "deep", ["scan", "read_file"]), TeamMemory(InMemoryLedger())
    res = exp.run(Task("T1", "Review pkg for weaknesses", "vulnerability"), mem, ExpertBudget(tool_calls=8, tokens=200000))
    assert [e["source"] for e in res.evidence if e["type"] == "code"] == ["pkg/a.py:4", "pkg/b.py:4"]
    engine = next(e for e in res.evidence if e["type"] == "engine")
    assert engine["source"] == "markovian" and "2 bounded chunks" in engine["detail"] and "over 2 calls" in engine["detail"]
    assert fake.started["chunk_config"]["maxChunks"] == 2 and fake.started["memory_context"].startswith("TEAM MEMORY")
    assert "[CARRYOVER STATE]\nCOMPLETED: pkg/a.py" in prompts[1] and "[WORKING SET 2 of 2: pkg/b.py]" in prompts[1]
    assert fake.texts[1].rstrip().endswith("[TASK_COMPLETE]")           # the host-side marker fallback kept the chain moving
    kinds = [e["kind"] for e in ctx.trace.events]
    assert kinds.count("markovian_chunk") == 2 and "markovian_start" in kinds and "markovian_done" in kinds
    assert [f["claim"][:8] for f in res.findings] == ["pkg/a.py", "pkg/b.py"] and "a reviewed b reviewed" in res.answer


def test_single_file_review_does_not_use_markovian(tmp_path):
    def script(model, messages):
        return json.dumps({"findings": [], "summary": "nothing", "confidence": 0.6, "assumptions": [], "not_checked": []})
    ctx = make_ctx(tmp_path / "runs", script, root=repo(tmp_path))
    ctx.markovian = FakeMarkovian()
    res = VulnerabilityExpert(ctx, "vulnerability", "r", "p", "deep", ["scan"]).run(Task("T1", "Review pkg", "vulnerability"), TeamMemory(InMemoryLedger()), ExpertBudget())
    assert not any(e["type"] == "engine" for e in res.evidence) and ctx.markovian.started is None     # one file: the plain loop is enough


def test_reference_engine_drives_a_three_chunk_chain(markovian_server):
    mk = MarkovianClient(markovian_server)
    assert mk.health()["engine"] == "markovian"
    r = mk.start("Review three files", chunk_config={"chunkSize": 4000, "carryoverTokens": 600, "maxChunks": 5}, memory_context="MEMORY: none")
    assert r["step"] == 1 and "MEMORY: none" in r["prompt"] and not r["done"]
    for i in range(1, 4):
        r = mk.step(r["run_id"], json.dumps({"findings": []}) + "\n" + checkpoint(f"f{i}", "rest", "none", "ctx", final=i == 3),
                    usage={"prompt_tokens": 100, "completion_tokens": 10})
        if i < 3:
            assert r["step"] == i + 1 and r["carryover"].startswith(f"COMPLETED: f{i}")
    assert r["done"] and r["status"] == "completed" and len(r["chunks"]) == 3 and r["measured"] == {"prompt_tokens": 300, "completion_tokens": 30, "calls": 3}
    assert r["chunks"][1]["carryover_in"].startswith("COMPLETED: f1") and r["chunk_config"]["carryoverTokens"] == 600


def test_client_default_url_is_the_markovian_service_not_the_hmem_sidecar():
    assert MarkovianClient().url == "http://127.0.0.1:8101"


def test_a_stray_final_marker_cannot_end_the_chain_early():
    out = ensure_marker('{"findings": []}\n[TASK_COMPLETE]', final=False, completed="a.py", remaining="b.py")
    assert "[TASK_COMPLETE]" not in out and out.startswith('{"findings": []}') and "[STATE_CHECKPOINT]\nCOMPLETED: a.py\nREMAINING: b.py" in out
    assert ensure_marker('{"x": 1}\n<DONE/>', final=True) == '{"x": 1}\n<DONE/>'                  # the engine's alias counts as final


def test_a_failing_chunk_abandons_the_chain_and_lists_what_was_not_reviewed(tmp_path):
    calls = []

    def script(model, messages):
        calls.append(1)
        if len(calls) == 2:
            raise BudgetExceeded("token budget 100 exceeded")
        return json.dumps({"findings": [], "summary": "a done"}) + "\n[STATE_CHECKPOINT]\nCOMPLETED: pkg/a.py\nREMAINING: pkg/b.py\nDECISIONS: none\nCONTEXT: scan"
    ctx = make_ctx(tmp_path / "runs", script, root=repo2(tmp_path))
    fake = FakeMarkovian()
    abandoned = []
    fake.abandon = lambda run_id: abandoned.append(run_id)
    ctx.markovian = fake
    res = VulnerabilityExpert(ctx, "vulnerability", "r", "p", "deep", ["scan", "read_file"]).run(Task("T1", "Review pkg", "vulnerability"), TeamMemory(InMemoryLedger()), ExpertBudget(tool_calls=8, tokens=200000))
    assert abandoned == ["fake"] and events(ctx, "markovian_abandoned") and events(ctx, "markovian_done")[0]["status"] == "abandoned"
    assert any(n.startswith("not reviewed: pkg/b.py") for n in res.not_checked) and any("stopped by the budget" in n for n in res.not_checked)
    assert any(e["type"] == "engine" for e in res.evidence) and res.confidence == pytest.approx(0.3)
