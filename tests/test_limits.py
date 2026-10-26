"""Each agent knows what it gets wrong: the failed probes and the improvement items that name it reach its prompt as a standing
note with the aim to remove them; and the chat narrates a mission's trace as it happens. No model and no network."""
import json

from inverse_core.team import limits

from fakes import crew


def _root(tmp_path):
    (tmp_path / "docs" / "evidence" / "probe").mkdir(parents=True)
    with open(tmp_path / "docs" / "evidence" / "probe" / "p1.json", "w") as f:
        json.dump({"agents": {"ada": {"probes": [{"goal": "total across datasets", "pass": False}, {"goal": "ok", "pass": True}]},
                              "scout": {"probes": [{"goal": "fine", "pass": True}]}}}, f)
    (tmp_path / "docs" / "AGENT_REPORT.md").write_text("## List\n\n1. **Ada must add the two counts she holds**: x\n2. **Scout must not add a filter**: y\n"
                                                       "3. **Vera must doubt numbers**: z\n", encoding="utf-8")
    return str(tmp_path)


def test_known_limitations_come_from_the_probe_and_the_report(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITS_NOTE", "on")                                                        # the prompt note is opt-in: measured, it hurt Euler (probe ten1)
    root = _root(tmp_path)
    k = limits.all_known(root)
    assert k["solver"] == ["fails this probe: total across datasets", "Ada must add the two counts she holds"]
    assert k["research"] == ["Scout must not add a filter"] and k["critic"] == ["Vera must doubt numbers"] and "reasoning" not in k
    n = limits.note(root, "solver", k)
    assert "standing aim is to remove them" in n and "total across datasets" in n and "propose it" in n and len(n) < 700
    assert limits.note(root, "reasoning", k) == "" and limits.all_known(str(tmp_path / "nowhere")) == {}


def test_the_note_reaches_the_experts_vera_and_atlas(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMITS_NOTE", "on")
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    ada = ctx.registry.experts["solver"]                                                            # the crew's own report names Ada
    assert "KNOWN LIMITATIONS" in ada.prompt and ada.system().startswith(ada.prompt.split("\n")[0][:40])
    assert "KNOWN LIMITATIONS" in lead.plan_system() and lead.critic.note == ""                            # nothing is known against Vera today
    from inverse_core.team.critic import Critic
    ctx.root = _root(tmp_path)
    assert "Vera must doubt numbers" in Critic(ctx).note
