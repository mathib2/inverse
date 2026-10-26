"""Toward ten out of ten: the six flaws the probes still showed, each fixed by code and decided here without a model: Atlas's
routing rules in the planner prompt, Ada's total across datasets, Forge's template expert with the goal's own constants, Euler's
number in prose, Scout's unasked filter, Sentinel reading around a hit; the phone digest and the alert log; Tinker's merge gate."""
import json
import os
import re
import sys

from inverse_core import digest, notify
from inverse_core.team import lead as L
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.research import unfilter_quantity
from inverse_core.trace import Trace
from test_council import crew, events

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


def test_atlas_prompt_names_a_rule_per_goal_type_and_no_example_plan(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    s = lead.plan_system()
    assert "Routing rules" in s and "summary" in s and "reasoning alone" in s and "research first" in s
    assert s.count('"id":"T1"') == 1                                                                      # the schema only; no worked plans to copy


def test_ada_totals_two_dataset_counts_by_code(tmp_path):
    def script(model, messages):
        last = messages[-1]["content"]
        if '"tool_result"' in last and "calc" in messages[-2]["content"]:
            return json.dumps({"answer": "P-104 has 800 samples across both datasets [calc].", "confidence": 0.9, "assumptions": [], "not_checked": []})
        return json.dumps({"answer": "P-104 has 800 samples across both datasets.", "confidence": 0.9, "assumptions": [], "not_checked": []})

    ctx, lead = crew(tmp_path, script)

    def sql(statement, limit=2000):                                                                       # a registry with two datasets, 400 samples each
        s = statement.lower()
        if "count(*)" in s:
            if "p104_baseline_samples" in s or "p104_current_samples" in s:
                return [{"n": 400}]
            raise ValueError("no such table")
        if "equipment_table" in s:
            return [{"equipment_id": "P-104", "mass_kg": 12.5, "baseline_dataset": "p104-baseline", "current_dataset": "p104-current"}]
        return [{"equipment_id": "P-104", "mass_kg": 12.5}]
    ctx.zetaris.sql = sql
    res = ctx.registry.experts["solver"].run(Task("T1", "How many sensor samples exist for P-104 across its baseline and current datasets together?", "solver"),
                                             lead.memory, ExpertBudget(tool_calls=10))
    tot = events(ctx, "total_by_code")
    assert tot and re.fullmatch(r"\d+ \+ \d+", tot[0]["expr"]) and any(str(e.get("source", "")).startswith("calc(") for e in res.evidence)
    assert "800" in res.answer and res.confidence >= 0.9                                                  # the sum is in the evidence, so nothing is docked


def test_forge_template_expert_carries_the_goals_given_values(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    goal = "What does a 12.5 kg mass weigh on the Moon, where gravity is 1.62 m/s^2? We have no converter for that."
    assert lead._forge_by_rule(Task("T1", goal, "moon_weight_expert"), goal) is True
    prompt = ctx.registry.experts["moon_weight_expert"].prompt
    assert "GIVEN VALUES" in prompt and "gravity = 1.62 m/s^2" in prompt and "no textbook value" in prompt
    assert L.given_values("the period is 2 s and mass of 3 kg") == "period = 2 s"                        # 'is' and '=' count, 'of' does not


def test_the_calculator_hint_uses_the_goals_own_numbers_never_an_id(tmp_path):
    from inverse_core.team.verify import claim_numbers
    import re as _re
    strip = lambda g: claim_numbers(_re.sub(r"\^\s*\d+", "", g))
    assert strip("Using the registry mass of P-104, compute its weight in newtons with g = 9.81 m/s^2.") == ["9.81"]        # P-104 and ^2 are not numbers to multiply
    assert strip("What does a 12.5 kg mass weigh on the Moon, where gravity is 1.62 m/s^2?")[:2] == ["12.5", "1.62"]


def test_euler_may_not_state_a_new_number_in_prose(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    euler = ctx.registry.experts["reasoning"]
    ev, bad = euler._check([{"claim": "The cube root of 27 is 3."}], context="What is the cube root of 27?")
    assert bad and "without a calc" in bad[0] and not ev                                                 # 3 appears nowhere but the prose
    ev, bad = euler._check([{"claim": "The mass is 12.5 kg, as given."}, {"claim": "weight", "calc": "12.5 * 9.81", "expect": 122.625}], context="12.5 kg times 9.81")
    assert not bad and [e["type"] for e in ev] == ["step", "calc"]                                        # a given number may be restated


def test_scout_drops_a_quantity_filter_the_task_did_not_ask_for():
    goal = "What are the noise level and the sampling rate of the sensors on P-104?"
    sql = "SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'v'"
    assert unfilter_quantity(sql, goal) == ("SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104'", True)
    assert unfilter_quantity("SELECT sigma FROM obs.sensors_table WHERE quantity = 'x' AND equipment_id = 'P-104'", goal) == ("SELECT sigma FROM obs.sensors_table WHERE equipment_id = 'P-104'", True)
    assert unfilter_quantity("SELECT sigma FROM obs.sensors_table WHERE quantity = 'x'", goal) == ("SELECT sigma FROM obs.sensors_table", True)
    assert unfilter_quantity(sql, "the displacement sensor on P-104")[1] is False and unfilter_quantity(sql, "sensor T200-DISP-1")[1] is False
    assert unfilter_quantity("SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", goal)[1] is False


def test_sentinel_reads_around_each_hit_before_the_model_speaks(tmp_path):
    seen = {}

    def script(model, messages):
        seen["user"] = messages[-1]["content"]
        return json.dumps({"findings": [], "summary": "Nothing beyond the scan.", "confidence": 0.7, "assumptions": [], "not_checked": []})

    ctx, lead = crew(tmp_path, script)
    sentinel = ctx.registry.experts["vulnerability"]
    res = sentinel.run(Task("T1", "Review core/inverse_core/team/tools.py for security weaknesses.", "vulnerability"), lead.memory, ExpertBudget(tool_calls=6))
    read = events(ctx, "hits_read")
    if read:                                                                                              # the scan found hits in tools.py: their surroundings were read by code
        assert read[0]["hits"] >= 1 and "CODE AROUND THE HITS" in seen["user"] and re.search(r"\n\s*\d+: ", seen["user"])
    assert res.answer


def test_the_digest_says_who_spoke_what_vera_decided_and_the_last_results(tmp_path, monkeypatch):
    lines = [{"who": "lead", "kind": "note", "text": "Plan: T1 Scout", "ts": 10}, {"who": "research", "kind": "result", "text": "Finished T1: 400 rows", "ts": 11},
             {"who": "critic", "kind": "review", "text": "ACCEPT T1 (by rule): fine", "ts": 12}, {"who": "critic", "kind": "review", "text": "REVISE T2 (by rule): a number from nowhere", "ts": 13},
             {"who": "tinker", "kind": "alert", "text": "Council-approved change for X", "ts": 14}, {"who": "you", "kind": "question", "text": "hello", "ts": 15}]
    s = digest.summary(lines, 30)
    assert s.startswith("Crew, last 30 min: 5 lines from") and "Vera: 1 accepted, 1 sent back." in s and "Alert: Council-approved" in s and "Scout: Finished T1" in s
    assert digest.summary([], 30) == "" and digest.summary([{"who": "you", "kind": "question", "text": "x"}], 30) == ""
    root = str(tmp_path)
    for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "NOTIFY_SMS_TO", "TEXTBELT_TO"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("INVERSE_ROOT", root)
    monkeypatch.setenv("NOTIFY_DIGEST_MINUTES", "0")
    assert digest.send_if_due(root) is None
    monkeypatch.setenv("NOTIFY_DIGEST_MINUTES", "30")
    assert digest.send_if_due(root, now=1000) is None                                                   # nothing said yet: nothing sent, the clock is set
    Trace(os.path.join(root, "runs")).event("compose", cited=1, fallback=False, unfinished=0)
    assert digest.send_if_due(root, now=1000 + 1801).startswith("Crew, last 30 min: 1 lines from Atlas")


def test_every_alert_is_logged_with_the_channels_that_took_it(tmp_path, monkeypatch):
    for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "NOTIFY_SMS_TO", "TEXTBELT_TO"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("INVERSE_ROOT", str(tmp_path))
    assert notify.notify("hello") == []
    with open(tmp_path / "state" / "alerts.jsonl", encoding="utf-8") as f:
        row = json.loads(f.readlines()[-1])
    assert row["text"] == "hello" and row["sent"] == [] and row["title"] == "INVERSE crew"


def test_tinker_gate_reads_changed_lines_and_skips_merged_items(monkeypatch):
    import tinker
    diff = "diff --git a/x.py b/x.py\n@@ -10,2 +10,3 @@ def f():\n+a\n+b\n+c\n@@ -40 +41 @@\n+d\n"
    monkeypatch.setattr(tinker, "sh", lambda cmd, **kw: (0, diff))
    assert tinker.changed_lines(["x.py"]) == {"x.py": {10, 11, 12, 41}}
    state = {"tried": {"A": {"last": 1, "outcome": "merged and deployed"}, "B": {"last": 2, "outcome": "no change made"}}}
    assert tinker.pick(["A", "B"], state) == "B"                                                          # a merged item is not picked again
    assert tinker.pick(["A"], state) == "A"                                                               # unless nothing else is left
    assert tinker.test_file_for("Euler must compute roots and powers with the calculator").endswith(os.path.join("backlog_tests", "test_euler_must_compute_roots_and_powers_with.py"))

def test_tinker_merges_only_a_measured_improvement_against_a_real_baseline(monkeypatch):
    import tinker
    assert tinker.mergeable(True, None) and tinker.mergeable(False, True) and not tinker.mergeable(False, None) and not tinker.mergeable(False, False)
    monkeypatch.setattr(tinker, "latest_probes", lambda: {"forge": {"rating": {"score": 5.5}}})
    assert tinker.baseline("forge", {"marks": {}}) == 5.5 and tinker.baseline("forge", {"marks": {"forge": 7.0}}) == 7.0     # a no-op that drops forge to 3.5 is now caught
    assert tinker.baseline("nobody", {}) is None

