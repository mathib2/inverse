"""Each agent knows what it gets wrong: the failed probes and the improvement items that name it reach its prompt as a standing
note with the aim to remove them; and the chat narrates a mission's trace as it happens. No model and no network."""
import json
import os

from inverse_core import chat
from inverse_core.team import limits
from inverse_core.trace import Trace
from test_council import crew


def _root(tmp_path):
    (tmp_path / "docs" / "evidence" / "probe").mkdir(parents=True)
    with open(tmp_path / "docs" / "evidence" / "probe" / "p1.json", "w") as f:
        json.dump({"agents": {"ada": {"probes": [{"goal": "total across datasets", "pass": False}, {"goal": "ok", "pass": True}]},
                              "scout": {"probes": [{"goal": "fine", "pass": True}]}}}, f)
    (tmp_path / "docs" / "AGENT_REPORT.md").write_text("## List\n\n1. **Ada must add the two counts she holds**: x\n2. **Scout must not add a filter**: y\n"
                                                       "3. **Vera must doubt numbers**: z\n", encoding="utf-8")
    return str(tmp_path)


def test_known_limitations_come_from_the_probe_and_the_report(tmp_path):
    root = _root(tmp_path)
    k = limits.all_known(root)
    assert k["solver"] == ["fails this probe: total across datasets", "Ada must add the two counts she holds"]
    assert k["research"] == ["Scout must not add a filter"] and k["critic"] == ["Vera must doubt numbers"] and "reasoning" not in k
    n = limits.note(root, "solver", k)
    assert "standing aim is to remove them" in n and "total across datasets" in n and "propose it" in n and len(n) < 700
    assert limits.note(root, "reasoning", k) == "" and limits.all_known(str(tmp_path / "nowhere")) == {}


def test_the_note_reaches_the_experts_vera_and_atlas(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    ada = ctx.registry.experts["solver"]                                                            # the crew's own report names Ada
    assert "KNOWN LIMITATIONS" in ada.prompt and ada.system().startswith(ada.prompt.split("\n")[0][:40])
    assert "KNOWN LIMITATIONS" in lead.plan_system() and lead.critic.note == ""                            # nothing is known against Vera today
    from inverse_core.team.critic import Critic
    ctx.root = _root(tmp_path)
    assert "Vera must doubt numbers" in Critic(ctx).note


def test_the_chat_narrates_a_mission_as_it_happens(tmp_path):
    root = str(tmp_path)
    tr = Trace(os.path.join(root, "runs"))
    tr.event("plan", goal="g", tasks=[{"id": "T1", "expert": "research", "goal": "look up the mass"}])
    tr.event("delegate", task="T1", expert="research", goal="look up the mass")
    tr.event("tool", agent="research", tool="run_sql", args={"sql": "SELECT 1"}, error=None)
    tr.event("llm", agent="research", lane="fast")
    tr.event("expert_result", task="T1", expert="research", confidence=0.6, evidence=1, tool_calls=1)
    tr.event("critic", task="T1", verdict="accept", reason="fine", by="rule")
    tr.event("compose", cited=1, fallback=True, unfinished=0)
    lines = chat.tail(20, root)
    assert [(m["who"], m["kind"]) for m in lines] == [("lead", "note"), ("lead", "question"), ("research", "log"), ("research", "result"), ("critic", "review"), ("lead", "result")]
    assert lines[0]["text"].startswith("Plan: T1 Scout: look up the mass") and lines[1]["to"] == "research" and "ACCEPT T1 (by rule)" in lines[4]["text"]
    assert lines[5]["text"] == "Answer ready: 1 citation(s); composed by code" and lines[0]["run"] == os.path.basename(tr.dir)
