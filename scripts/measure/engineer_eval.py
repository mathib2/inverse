"""Measure a model as Tinker's engineer: the same expert, prompt, tools, budget and task shape as scripts/tinker.py, on four small
edits with a known right answer, each decided by a test the model is shown failing, plus (--tasks all) the real backlog items,
decided by the test suite. Run from the sandbox clone, with Tinker stopped (it resets the clone at every cycle):

    PYTHONPATH=core:scripts .venv/bin/python scripts/measure/engineer_eval.py --label coder7b --model qwen2.5-coder:7b

Writes docs/evidence/engineer/<label>.json and prints one line per task and the totals. The live checkout is never touched:
edit_file and run_tests work only where INVERSE_SANDBOX is the checkout, which importing tinker sets to this one."""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # scripts/<group>/<this file> -> the checkout
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "core"))

import tinker
from inverse_core import injection_guard as guard
from inverse_core.budget import Budget
from inverse_core.ledger import SidecarLedger
from inverse_core.team.custom import CustomExpert
from inverse_core.team.expert import ExpertBudget, Task
from inverse_core.team.lanes import Lanes
from inverse_core.team.llmcall import Ctx
from inverse_core.team.memory import TeamMemory
from inverse_core.trace import Trace

TARGET = "core/inverse_core/eval_target.py"
TEST = "tests/test_eval_target.py"
SYNTHETIC = [
    {"name": "missing_case", "item": "Ada must convert milligrams too",
     "hint": "unit_factor() in core/inverse_core/eval_target.py knows kg and g; add mg = 1e-6 so tests/test_eval_target.py passes.",
     "target": 'FACTORS = {"kg": 1.0, "g": 0.001}\n\n\ndef unit_factor(unit):\n    """Kilograms per one of the unit."""\n    return FACTORS[unit]\n',
     "test": 'from inverse_core.eval_target import unit_factor\n\n\ndef test_eval_target():\n    assert unit_factor("mg") == 1e-6 and unit_factor("g") == 0.001\n'},
    {"name": "off_by_one", "item": "Scout must return the last n rows, not n minus one",
     "hint": "last_rows() in core/inverse_core/eval_target.py drops one row; it must return exactly the last n rows so tests/test_eval_target.py passes.",
     "target": 'def last_rows(rows, n):\n    """The last n rows."""\n    return rows[-n + 1:]\n',
     "test": 'from inverse_core.eval_target import last_rows\n\n\ndef test_eval_target():\n    assert last_rows([1, 2, 3, 4], 2) == [3, 4] and last_rows([1, 2, 3], 3) == [1, 2, 3]\n'},
    {"name": "regex", "item": "Sentinel must accept a sensor id with a trailing number",
     "hint": "SENSOR in core/inverse_core/eval_target.py matches T200-DISP but not T200-DISP-1: the id may end in -<number>. Change the pattern so tests/test_eval_target.py passes.",
     "target": 'import re\n\nSENSOR = re.compile(r"^[A-Z]\\d+-[A-Z]+$")\n\n\ndef is_sensor_id(s):\n    return bool(SENSOR.match(s))\n',
     "test": 'from inverse_core.eval_target import is_sensor_id\n\n\ndef test_eval_target():\n    assert is_sensor_id("T200-DISP-1") and is_sensor_id("T200-DISP") and not is_sensor_id("abc")\n'},
    {"name": "prompt_sentence", "item": "Euler must be told never to invent a number",
     "hint": "PROMPT in core/inverse_core/eval_target.py lacks the rule: add one sentence that contains the words 'never invent' and keep the rest, so tests/test_eval_target.py passes.",
     "target": 'PROMPT = "You are the reasoning expert. Show every step. Use the calculator for arithmetic."\n',
     "test": 'from inverse_core.eval_target import PROMPT\n\n\ndef test_eval_target():\n    assert "never invent" in PROMPT.lower() and "calculator" in PROMPT\n'},
]


def numbered(text):
    return "\n".join(f"{i + 1}: {ln}" for i, ln in enumerate(text.splitlines()))


def task_text(item, hint, path, excerpt):
    """The same shape Tinker gives its engineer (scripts/tinker.py)."""
    return (f"Make the smallest code change that helps with: {item}\nWhat to change: {hint[:700]}\nResearch note: none"
            f"\nThe file: {path}\nThe lines that matter:\n{excerpt[:5000]}")


def events_of(ctx):
    try:
        with open(os.path.join(ctx.trace.dir, "trace.jsonl"), encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]
    except (OSError, ValueError):
        return []


def pytest_passes(target):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", target, "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True, timeout=900,
                       env={**os.environ, "PYTHONPATH": "core"})
    return r.returncode == 0, (r.stdout or "").strip().splitlines()[-1:]


def run_one(model, name, item, hint, path, excerpt, decide):
    lanes = Lanes()
    lanes.mapping["engineer"] = model
    ctx = Ctx(lanes, Trace(os.path.join(ROOT, "runs")), Budget(max_llm_calls=14, max_seconds=900), guard=guard.sanitize, equipment=[], root=ROOT)
    engineer = CustomExpert(ctx, "tinker", tinker.ENGINEER_ROLE, tinker.ENGINEER_PROMPT, "engineer", ["read_file", "grep", "edit_file", "run_tests"])
    t0 = time.time()
    try:
        res = engineer.run(Task("E1", task_text(item, hint, path, excerpt), "tinker"), TeamMemory(SidecarLedger()), ExpertBudget(tool_calls=8, tokens=150000, seconds=600))
        answer, err = str(res.answer or ""), ""
    except Exception as ex:                                                   # a crashed run is a failed task, not a crashed measurement
        answer, err = "", f"{type(ex).__name__}: {str(ex)[:160]}"
    secs = round(time.time() - t0, 1)
    ev = events_of(ctx)
    edits = [e for e in ev if e.get("kind") == "tool" and e.get("tool") == "edit_file"]
    applied = [e for e in edits if not e.get("error") or str(e.get("error")) in ("None", "")]
    passed, summary = decide()
    row = {"name": name, "model": model, "seconds": secs, "llm_calls": sum(1 for e in ev if e.get("kind") == "llm"),
           "tool_calls": sum(1 for e in ev if e.get("kind") == "tool"), "edit_attempts": len(edits), "edit_applied": len(applied),
           "passed": bool(passed), "answer": answer[:160], "error": err, "test_summary": " ".join(summary)[:160], "run": os.path.basename(ctx.trace.dir)}
    print(f"  {name:<34} {'PASS' if passed else 'fail':<5} {secs:>6.0f} s  llm {row['llm_calls']:>2}  tools {row['tool_calls']:>2}  edits {len(applied)}/{len(edits)}  {answer[:70]!r}{(' ' + err) if err else ''}")
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default=os.environ.get("TINKER_ENGINEER_MODEL") or Lanes().model("deep"))
    ap.add_argument("--tasks", default="synthetic", choices=["synthetic", "backlog", "all"])
    ap.add_argument("--only", default="", help="comma-separated task names")
    a = ap.parse_args()
    only = [x.strip() for x in a.only.split(",") if x.strip()]
    tinker.revert()                                                            # start from the base commit, nothing left over
    rows = []
    print(f"engineer model: {a.model}  tasks: {a.tasks}  sandbox: {ROOT}")
    if a.tasks in ("synthetic", "all"):
        for t in SYNTHETIC:
            if only and t["name"] not in only:
                continue
            for p, text in ((TARGET, t["target"]), (TEST, t["test"])):
                with open(os.path.join(ROOT, p), "w", encoding="utf-8") as f:
                    f.write(text)
            rows.append(run_one(a.model, t["name"], t["item"], t["hint"], TARGET, numbered(t["target"]), lambda: pytest_passes(TEST)))
            for p in (TARGET, TEST):
                try:
                    os.remove(os.path.join(ROOT, p))
                except OSError:
                    pass
            tinker.revert()
    if a.tasks in ("backlog", "all"):
        try:
            with open(os.path.join(ROOT, "docs", "AGENT_REPORT.md"), encoding="utf-8") as f:
                report = f.read()
        except OSError:
            report = ""
        hints = tinker.details(report)
        for item in tinker.backlog(report, {}):
            slug = item.lower().split()[0]
            if only and slug not in only:
                continue
            path, excerpt = tinker.place_of(item)

            def decide():
                files = tinker.changed_files()
                ok, summary = pytest_passes("tests") if files else (False, ["no change made"])
                return ok and bool(files), summary + [f"changed: {', '.join(files)[:80]}"]
            rows.append(run_one(a.model, "backlog:" + slug, item, hints.get(item, ""), path, excerpt, decide))
            tinker.revert()
    tot = {"tasks": len(rows), "passed": sum(r["passed"] for r in rows), "edits_applied": sum(r["edit_applied"] for r in rows),
           "mean_seconds": round(sum(r["seconds"] for r in rows) / max(1, len(rows)), 1), "mean_llm_calls": round(sum(r["llm_calls"] for r in rows) / max(1, len(rows)), 2)}
    print(f"TOTAL {tot['passed']}/{tot['tasks']} pass · {tot['edits_applied']} edits applied · {tot['mean_seconds']} s per task · {tot['mean_llm_calls']} calls per task")
    out = {"label": a.label, "model": a.model, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "tasks": rows, "totals": tot}
    folder = os.path.join(ROOT, "docs", "evidence", "engineer")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, a.label + ".json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("written", os.path.relpath(os.path.join(folder, a.label + ".json"), ROOT))


if __name__ == "__main__":
    main()
