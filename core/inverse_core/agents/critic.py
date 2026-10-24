"""Critic (Nemotron via Nightshift): picks a test that could break the surviving model. The test itself is deterministic."""
from ..clients.meterless import extract_json
from ..inference.falsify import MENU, run

SYSTEM = ("You are a skeptical physicist. Given an accepted model, choose ONE test from the menu most likely to break it. "
          'Return ONLY JSON {"test":"<menu key>","reason":"..."}.')


def critique(llm, trace, budget, entry, data, tried_tests=()):
    """tried_tests: tests this candidate already faced. Returns None (no LLM call) once it has faced every test."""
    menu = {k: v for k, v in MENU.items() if k not in tried_tests}
    if not menu:
        return None
    budget.charge_llm()
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Model: {entry['model'].form()} theta={[round(float(v),4) for v in entry['fit']['theta']]}. "
                                        f"Validators passed: {[v['validator'] for v in entry['validators']]}. Menu: {menu}"}]
    r = llm.chat(msgs, json_object=True)                                      # one JSON object: Nightshift and Ollama honour response_format
    trace.event("llm", agent="critic", model=r["model"], latency_s=r["latency_s"], prompt=msgs[1]["content"], reply=r["text"][:800])
    try:
        pick = extract_json(r["text"])
        name = pick["test"] if pick.get("test") in menu else next(iter(menu))
        reason = pick.get("reason", "")
    except Exception:
        name, reason = next(iter(menu)), "fallback (unparseable critic reply)"
    result = run(name, entry["model"], entry["fit"]["theta"], data)
    trace.event("critic_test", test=name, reason=reason, passed=result["passed"], evidence=result["evidence"])
    return result, reason, r["model"]
