"""AI replies get enough room: Nightshift may route to a reasoning model that spends tokens thinking first.
At the old 900-token default the Proposer's JSON was cut off mid-reply on live runs."""
import inspect
import json
import os
import sys

from inverse_core import analysis as A, datasets as D, ledger as L
from inverse_core.adapters import physical
from inverse_core.agents import critic, proposer
from inverse_core.clients.meterless import REPLY_MAX_TOKENS, MeterlessClient
from inverse_core.trace import Trace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"))
import plain  # noqa: E402


class RecordingLLM:
    model = "stub"

    def __init__(self, text, finish="stop"):
        self.text, self.finish, self.kwargs = text, finish, []

    def chat(self, messages, **kw):
        self.kwargs.append(kw)
        return {"text": self.text, "model": "stub", "usage": None, "latency_s": 0.0, "finish_reason": self.finish}


class NoBudget:
    def charge_llm(self):
        pass


def roomy(llm):
    return all(kw.get("max_tokens", REPLY_MAX_TOKENS) >= 2000 for kw in llm.kwargs)


def test_default_reply_room_fits_thinking_models():
    assert REPLY_MAX_TOKENS >= 2000
    assert inspect.signature(MeterlessClient.chat).parameters["max_tokens"].default == REPLY_MAX_TOKENS


def test_proposer_and_critic_get_the_full_reply_room(tmp_path):
    llm = RecordingLLM(json.dumps({"candidates": [{"terms": ["c", "k"]}]}))
    models, _ = proposer.propose(llm, Trace(str(tmp_path)), NoBudget(), {}, 0.01, [], set(), "", 1.0)
    assert len(models) == 1 and roomy(llm)

    data = D.p104_current()
    fitted, _ = A.evaluate(data, "E", L.InMemoryLedger(), physical.candidate_library(data, 1.0)[:1], A.new_stats())
    llm = RecordingLLM(json.dumps({"test": "long_horizon_energy", "reason": "stub"}))
    out = critic.critique(llm, Trace(str(tmp_path)), NoBudget(), fitted[0], fitted[0]["data"], set())
    assert out is not None and roomy(llm)


def test_cut_off_suggestions_are_recorded_and_said_plainly(tmp_path):
    cut = RecordingLLM('{"candidates": [{"terms": ["c", "k"], "rationale": "Linear viscous damping and', finish="length")
    trace = Trace(str(tmp_path))
    models, _ = proposer.propose(cut, trace, NoBudget(), {}, 0.01, [], set(), "", 1.0)
    assert models == []
    event = next(e for e in trace.events if e["kind"] == "proposer_parse_error")
    assert event["truncated"] is True
    assert plain.step(event) == "The AI's suggestions were cut off, so INVERSE used its built-in ones"
