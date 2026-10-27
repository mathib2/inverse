"""The registry: agents from experts/*.yaml and local overrides, their names, and prompt files inside the repository. No model and no network unless a test says so."""
import os

import pytest

from inverse_core.team.crew import CREW, name, rename, roster, who
from inverse_core.team.registry import ConfigError, Registry, forget_config, load_configs, save_config

from fakes import make_ctx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_built_in_expert_has_a_name_and_configs_can_override_it():
    configs = load_configs(os.path.join(ROOT, "experts"))
    for ident in configs:
        assert name(ident, configs) == configs[ident]["callsign"] == CREW[ident]["name"]
    assert name("lead") == "Atlas" and name("critic") == "Vera" and name("watch") == "Warden" and name("watch:P-104") == "Warden"
    assert name("all") == "everyone" and name("new_agent") == "New Agent" and name("") == ""
    assert name("research", {"research": {"callsign": "Finder"}}) == "Finder"
    assert who("research") == "Scout (research)" and who("all") == "everyone"
    rows = roster(configs)
    assert [r["name"] for r in rows[:3]] == ["Atlas", "Vera", "Warden"] and {r["id"] for r in rows[3:]} == set(configs)


def test_rename_touches_identifiers_only():
    assert rename("research starts T1 (attempt 2)") == "Scout starts T1 (attempt 2)"
    assert rename("solver asked reasoning: what is 2*3") == "Ada asked Euler: what is 2*3"
    assert rename("the researcher re-searched research-grade data") == "the researcher re-searched research-grade data"
    assert rename("") == "" and rename(None) is None


def test_prompt_files_must_live_inside_the_repository(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}")
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    with pytest.raises(ConfigError, match="inside the repository"):
        reg.add({"name": "leaky", "kind": "custom", "role": "r", "system_prompt_file": "../../etc/passwd"})


def test_registry_loads_yaml_and_disabled_expert_is_absent(tmp_path):
    ctx = make_ctx(tmp_path, lambda m, msgs: "{}")
    reg = Registry(ctx, os.path.join(ROOT, "experts"), ROOT)
    assert set(reg.names()) == {"research", "reasoning", "solver", "vulnerability", "architect"}
    d = tmp_path / "experts"
    d.mkdir()
    (d / "a.yaml").write_text("name: a\nkind: reasoning\nrole: r\nmodel_lane: fast\nenabled: false\n")
    (d / "b.yaml").write_text("name: b\nkind: reasoning\nrole: r\nmodel_lane: deep\nbudget: {tool_calls: 1}\n")
    r2 = Registry(ctx, str(d), ROOT)
    assert r2.names() == ["b"] and r2.experts["b"].lane == "deep" and r2.budget_for("b").max_tool_calls == 1
    (d / "c.yaml").write_text("name: c\nkind: nope\nrole: r\n")
    with pytest.raises(ValueError, match="unknown expert kind"):
        Registry(ctx, str(d), ROOT)


def test_registry_local_overrides_add_and_disable_without_touching_builtins(tmp_path, monkeypatch):
    monkeypatch.delenv("INVERSE_IGNORE_LOCAL_EXPERTS", raising=False)                        # this test is about local overrides
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
