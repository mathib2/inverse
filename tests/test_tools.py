"""The toolbox: files inside the repository only, the scan, the calculator, web search and fetch, the sandbox-only write tools. No model and no network unless a test says so."""
import os

import pytest

from inverse_core.budget import BudgetExceeded
from inverse_core.team.expert import ExpertBudget
from inverse_core.team.reasoning import safe_eval
from inverse_core.team.tools import page_text, parse_duckduckgo, Tools

from fakes import crew, events, make_ctx, repo


DDG = ('<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fcache&amp;rut=abc">Prefix <b>cache</b> notes</a>'
       '<a class="result__snippet" href="x">How the <b>KV</b> cache works &amp; why.</a>'
       '<a rel="nofollow" class="result__a" href="https://example.org/two">Two</a><a class="result__snippet" href="y">second</a>')


def _budget():
    from inverse_core.team.expert import ExpertBudget
    return ExpertBudget()


def test_web_results_are_parsed_and_pages_become_text():
    r = parse_duckduckgo(DDG)
    assert r[0] == {"title": "Prefix cache notes", "url": "https://example.com/cache", "snippet": "How the KV cache works & why."}
    assert r[1]["url"] == "https://example.org/two" and r[1]["snippet"] == "second"
    assert page_text("<html><head><style>a{}</style><script>x()</script></head><body><h1>Hi</h1> <p>there &amp; you</p></body></html>") == "Hi there & you"


def test_sandbox_tools_refuse_outside_the_sandbox_and_fetch_refuses_this_machine(tmp_path, monkeypatch):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    t = Tools(ctx, ["write_file", "edit_file", "run_tests", "fetch_url"], owner="tinker")
    monkeypatch.delenv("INVERSE_SANDBOX", raising=False)
    assert "sandbox" in t.call("write_file", {"path": "x.md", "content": "y"}, _budget(), who="tinker")["error"]
    assert "sandbox" in t.call("run_tests", {}, _budget(), who="tinker")["error"]
    assert "public" in t.call("fetch_url", {"url": "http://127.0.0.1:8501/"}, _budget(), who="tinker")["error"]
    assert "public" in t.call("fetch_url", {"url": "ftp://example.com/x"}, _budget(), who="tinker")["error"]
    monkeypatch.setenv("INVERSE_SANDBOX", t.root)                                                     # now this checkout is the sandbox
    out = t.call("write_file", {"path": "notes_tinker_test.md", "content": "one two\n"}, _budget(), who="tinker")
    assert out == {"written": "notes_tinker_test.md", "chars": 8}
    out = t.call("edit_file", {"path": "notes_tinker_test.md", "old": "two", "new": "three"}, _budget(), who="tinker")
    assert out["edited"] == "notes_tinker_test.md" and open(os.path.join(t.root, "notes_tinker_test.md")).read() == "one three\n"
    assert "exactly once" in t.call("edit_file", {"path": "notes_tinker_test.md", "old": "zzz", "new": "y"}, _budget(), who="tinker")["error"]
    out = t.call("edit_file", {"path": "notes_tinker_test.md", "old": "1: one three", "new": "1: one four"}, _budget(), who="tinker")   # line numbers copied from the excerpt
    assert out["edited"] == "notes_tinker_test.md" and open(os.path.join(t.root, "notes_tinker_test.md")).read() == "one four\n"
    assert "text files" in t.call("write_file", {"path": "x.bin", "content": "y"}, _budget(), who="tinker")["error"]
    os.remove(os.path.join(t.root, "notes_tinker_test.md"))


def test_four_flaws_the_review_found(tmp_path, monkeypatch):
    from inverse_core.team import lead as L, tools as T
    from inverse_core.team.research import pin_sensor
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    assert T.Tools(ctx, [], owner="x").allowed == [] and "calc" in T.Tools(ctx, None, owner="x").allowed              # an empty list is no tools
    assert L.CALC_WORDS.search("What does the pump weigh?") and L.CALC_WORDS.search("how much it weighs")              # weigh, weighs, weighed
    sql = "SELECT sensor_id, sigma FROM obs.sensors_table WHERE equipment_id = 'T-200' AND quantity = 'x'"
    assert pin_sensor(sql, "the noise of sensor T200-DISP-1") == ("SELECT sensor_id, sigma FROM obs.sensors_table WHERE sensor_id = 'T200-DISP-1'", "T200-DISP-1")
    assert pin_sensor("SELECT sigma FROM obs.sensors_table WHERE sensor_id = 'T200-DISP-1'", "sensor T200-DISP-1")[1] is None

    class Hop:
        is_redirect, is_permanent_redirect, headers = True, False, {"Location": "http://127.0.0.1:8501/"}

    monkeypatch.setattr(T.requests, "get", lambda *a, **k: Hop())
    t = T.Tools(ctx, ["fetch_url"], owner="tinker")
    out = t.call("fetch_url", {"url": "http://example.com/x"}, _budget(), who="tinker")
    assert "redirect" in out["error"]


def test_file_tools_never_read_dot_folders_or_skipped_folders(tmp_path):
    root = repo(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[remote]\n  url = git@example\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "x.py").write_text("print(1)\n")
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}", root=root)
    tools, budget = Tools(ctx, ["read_file"]), ExpertBudget(tool_calls=5)
    assert "do not read" in tools.call("read_file", {"path": ".git/config"}, budget)["error"]
    assert "do not read" in tools.call("read_file", {"path": "vendor/x.py"}, budget)["error"]
    assert "eval(" in tools.call("read_file", {"path": "pkg/a.py"}, budget)["text"]


def test_safe_eval_computes_math_and_rejects_code():
    assert safe_eval("sqrt(16) + 2**3 * 0.5") == 8.0
    for bad in ["__import__('os').system('id')", "open('x')", "(1).__class__", "9**9**9", "x + 1"]:
        with pytest.raises((ValueError, SyntaxError)):
            safe_eval(bad)


def test_tools_read_only_inside_the_repo_and_never_secrets(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}", root=repo(tmp_path))
    tools, budget = Tools(ctx, ["read_file", "list_files", "grep", "calc"]), ExpertBudget(tool_calls=10)
    assert "outside" in tools.call("read_file", {"path": "../../../etc/passwd"}, budget)["error"]
    assert "secrets" in tools.call("read_file", {"path": ".env"}, budget)["error"]
    out = tools.call("read_file", {"path": "pkg/a.py", "start": 4, "end": 4}, budget)
    assert "eval(user_input)" in out["text"] and out["start"] == out["end"] == 4 and out["lines"] == 5
    assert tools.call("list_files", {"pattern": "*.py"}, budget)["files"] == ["pkg/a.py", "tests/test_a.py"]
    hits = tools.call("grep", {"pattern": r"\beval\(", "glob": "*.py"}, budget)["hits"]
    assert [(h["file"], h["line"]) for h in hits] == [("pkg/a.py", 4)]
    assert tools.call("calc", {"expr": "2*3"}, budget)["value"] == 6.0
    assert "not available" in tools.call("scan", {}, budget)["error"]                  # not in this expert's tool list
    assert "not available" in tools.call("nope", {}, budget)["error"]
    assert budget.tool_calls == 8 and len(events(ctx, "tool")) == 8                     # every call, failed or not, is charged and traced
    small = ExpertBudget(tool_calls=1)
    tools.call("calc", {"expr": "1"}, small)
    with pytest.raises(BudgetExceeded):
        tools.call("calc", {"expr": "1"}, small)


def test_scan_finds_weak_spots_with_fixed_severity_and_skips_tests(tmp_path):
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}", root=repo(tmp_path))
    out = Tools(ctx).call("scan", {}, ExpertBudget())
    rules = {(h["file"], h["line"], h["rule"], h["severity"]) for h in out["hits"]}
    assert ("pkg/a.py", 4, "exec_from_string", "high") in rules and ("pkg/a.py", 5, "no_timeout", "low") in rules
    assert not any(h["file"].startswith("tests/") for h in out["hits"]) and out["files_scanned"] == 1
    assert out["hits"][0]["severity"] == "high"                                         # worst first


def test_a_tool_ignores_a_why_the_model_put_inside_its_arguments(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "{}")
    t = Tools(ctx, ["run_sql", "calc"], owner="solver")
    out = t.call("run_sql", {"sql": "SELECT mass_kg FROM obs.equipment_table WHERE equipment_id = 'P-104'", "why": "the registry mass"}, ExpertBudget(), who="solver")
    assert "error" not in out and events(ctx, "args_dropped")[0]["dropped"] == ["why"]
    assert t.call("calc", {"expr": "2 * 3", "why": "x"}, ExpertBudget(), who="solver")["value"] == 6


def test_a_call_with_a_timeout_after_a_nested_call_is_not_reported(tmp_path):
    """The rule once stopped at the ')' of str(query) and reported "no timeout" for a call that ends in timeout=20."""
    root = repo(tmp_path)
    (tmp_path / "pkg" / "b.py").write_text("import requests, yaml\n"
                                           "r = requests.post(URL, data={'q': str(query)[:200]}, headers={'User-Agent': UA}, timeout=20)\n"
                                           "r = requests.get(url,\n    headers=h(x),  # (note)\n    timeout=5)\n"
                                           "r = requests.get(str(url), headers=h(x))\n"
                                           "cfg = yaml.load(open(p), Loader=yaml.SafeLoader)\n"
                                           "cfg = yaml.load(open(p))\n")
    ctx = make_ctx(tmp_path / "runs", lambda m, msgs: "{}", root=root)
    hits = [(h["line"], h["rule"]) for h in Tools(ctx).call("scan", {"path": "pkg/b.py"}, ExpertBudget())["hits"]]
    assert sorted(hits) == [(6, "no_timeout"), (8, "unsafe_deserialize")]
