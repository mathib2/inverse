"""The crew has names by expertise, missions run on a schedule, and the identifiers underneath never change."""
import json
import os
import time

from inverse_core.team.crew import CREW, name, rename, roster, who
from inverse_core.team.registry import load_configs
from inverse_core.team.watch import Watcher
from test_watch import FakeTeam, FakeZ

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


def test_standing_missions_run_when_due_and_not_again_until_their_interval_passes(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    missions = [{"name": "data_check", "every": 12, "goal": "Check {machines}."}, {"name": "digest", "every": 24, "goal": "Summarize what we know."}]
    w = Watcher(z, team, root=str(tmp_path), interval=60, missions=missions)
    assert [m["name"] for m in w.due_missions()] == ["data_check", "digest"]                 # never ran: both due
    done = w.cycle()
    assert team.goals[:2] == ["Check P-104, T-200.", "Summarize what we know."]               # {machines} filled from the registry
    assert [d["trigger"] for d in done][:2] == ["mission:data_check", "mission:digest"]
    m = json.load(open(os.path.join(tmp_path, "runs", "team1", "manifest.json")))
    assert m["trigger"] == "mission:data_check" and m["by"] == "warden" and m["status"] == "done"
    assert w.due_missions() == [] and w.cycle() == []                                           # not due again, and no new data either
    state = json.load(open(os.path.join(tmp_path, "state", "watch.json")))
    assert set(state["missions"]) == {"data_check", "digest"}
    w.state["missions"]["data_check"] = time.time() - 13 * 3600                               # 13 hours later: only the 12-hour one is due
    assert [m["name"] for m in w.due_missions()] == ["data_check"]
    assert w.status()["missions"]["digest"] > 0


def test_a_failed_mission_is_retried_in_an_hour_not_after_its_whole_interval(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path), fail=True)
    w = Watcher(z, team, root=str(tmp_path), interval=60, missions=[{"name": "digest", "every": 24, "goal": "Summarize."}])
    assert [d["ok"] for d in w.cycle() if d["trigger"] == "mission:digest"] == [False]
    assert w.due_missions() == [] and w.due_missions(now=time.time() + 3601) and not w.due_missions(now=time.time() + 1800)


def test_a_requeued_mission_counts_as_that_mission_when_it_completes(tmp_path):
    z, team = FakeZ(), FakeTeam(str(tmp_path))
    w = Watcher(z, team, root=str(tmp_path), interval=60, missions=[{"name": "digest", "every": 24, "goal": "Summarize."}])
    w._dump(w.current_path, {"kind": "team", "goal": "Summarize.", "started": "x", "trigger": "mission:digest"})      # the process died mid-mission
    w.recover()
    assert w.pending()[0]["mission"] == "digest" and [m["name"] for m in w.due_missions()] == ["digest"]
    done = w.cycle()
    assert team.goals[0] == "Summarize." and team.goals.count("Summarize.") == 1 and done[0]["trigger"] == "queue"   # ran once, from the queue
    assert w.due_missions() == [] and w.status()["missions"]["digest"] > 0                                           # and counted as the mission
