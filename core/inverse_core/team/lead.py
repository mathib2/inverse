"""Lead: plan -> delegate (by context) -> collect -> Critic (can send back) -> compose. It routes; experts do the work.
A stuck detector forces a strategy change when a retry repeats the previous answer, and escalates when it repeats twice."""
from __future__ import annotations

import re

from ..budget import BudgetExceeded
from .critic import Critic
from .expert import ExpertBudget, Task
from .llmcall import ask
from .plan import Plan, PlanError

PLAN_SYSTEM = """You are the lead of a team of experts. Decompose the user's goal into at most 5 tasks and assign each to ONE expert.
Delegate by what each task needs. Use depends_on when a task needs another task's result. Do not invent experts.
Experts:
{experts}
Known equipment IDs: {equipment}
Return ONLY JSON: {{"tasks":[{{"id":"T1","goal":"a self-contained instruction","expert":"name","depends_on":[]}}]}}
A physics task must name the machine by its ID in its goal. Use research to look facts up in the data, reasoning for derivations and calculations."""

COMPOSE_SYSTEM = """Write the final answer for the user from the accepted expert results. Rules: use only facts present in the results; cite every claim as
[T1.E2] (task id, evidence number); say which expert produced each part; state uncertainty and what was NOT checked; if a task failed or was rejected, say so and do not fill the gap.
Be concise (under 220 words)."""


def _norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


class Lead:
    def __init__(self, ctx, registry, memory, critic=None, max_attempts=3, plan_lane="deep", compose_lane="deep"):
        self.ctx, self.registry, self.memory = ctx, registry, memory
        self.critic = critic or Critic(ctx)
        self.max_attempts, self.plan_lane, self.compose_lane = max_attempts, plan_lane, compose_lane

    def plan(self, goal):
        prompt = PLAN_SYSTEM.format(experts="\n".join(f"- {n}: {r}" for n, r in self.registry.roles().items()),
                                    equipment=", ".join(self.ctx.equipment) or "none")
        msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": goal}]
        err = ""
        for _ in range(2):
            out = ask(self.ctx, self.plan_lane, msgs, "lead_plan", json_reply=True)
            try:
                plan = Plan.from_dict({"goal": goal, "tasks": out["json"]["tasks"][:5]}).validate(self.registry.names())
                self.ctx.trace.event("plan", goal=goal, tasks=[t.__dict__ | {"result": None} for t in plan.tasks], model=out["model"])
                return plan
            except (PlanError, KeyError, TypeError) as e:
                err = str(e)
                msgs += [{"role": "assistant", "content": out["text"]}, {"role": "user", "content": "Invalid plan: " + err + ". Return corrected JSON."}]
        raise PlanError("the planner could not produce a valid plan: " + err)

    def run(self, plan, run_dir=None):
        plan.validate(self.registry.names())
        self.ctx.trace.event("plan_approved", tasks=[t.id for t in plan.tasks])
        if run_dir:
            plan.save(run_dir)
        done = {}
        for task in plan.order():
            blocked = [d for d in task.depends_on if done[d].status != "done"]
            if blocked:
                task.status, task.feedback = "failed", f"skipped: dependency {blocked} did not produce an accepted result"
                self.ctx.trace.event("task_skipped", task=task.id, blocked_by=blocked)
            else:
                task.context = "\n".join(f"[{d}] {done[d].result['answer']}" for d in task.depends_on)
                self._execute(task)
            done[task.id] = task
            if run_dir:
                plan.save(run_dir)
        return plan

    def _execute(self, task):
        expert = self.registry.experts[task.expert]
        last, repeats = None, 0
        for attempt in range(1, self.max_attempts + 1):
            task.attempts, task.status = attempt, "running"
            budget = self.registry.budget_for(task.expert)
            self.ctx.trace.event("delegate", task=task.id, expert=task.expert, attempt=attempt, lane=expert.lane, feedback=task.feedback or None)
            try:
                res = expert.run(task, self.memory, budget)
            except BudgetExceeded as e:
                task.status, task.feedback = "failed", f"budget: {e}"
                self.ctx.trace.event("task_failed", task=task.id, reason=task.feedback)
                return
            except Exception as e:                                            # an expert crash is a failed task, not a crashed run
                task.feedback = f"{type(e).__name__}: {e}"
                self.ctx.trace.event("expert_error", task=task.id, error=task.feedback[:300])
                if attempt == self.max_attempts:
                    task.status = "failed"
                    return
                continue
            task.result = res.to_dict()
            self.ctx.trace.event("expert_result", task=task.id, expert=task.expert, confidence=res.confidence, evidence=len(res.evidence),
                                 models=res.models_used, tool_calls=budget.tool_calls, tokens=budget.tokens)
            if last is not None and _norm(res.answer) == last:
                repeats += 1
                self.ctx.trace.event("stuck", task=task.id, repeats=repeats)
                if repeats >= 2:
                    task.status, task.feedback = "failed", "escalated: the expert kept repeating the same answer"
                    self.ctx.trace.event("escalate", task=task.id)
                    return
                task.feedback = "You repeated your previous answer. CHANGE STRATEGY: use a different approach or different queries. " + task.feedback
                last = _norm(res.answer)
                continue
            last = _norm(res.answer)
            review = self.critic.review(task, task.result)
            if review["verdict"] == "accept":
                task.status, task.feedback = "done", ""
                return
            if review["verdict"] == "reject":
                task.status, task.feedback = "rejected", review["reason"]
                self.memory.refute(f"{task.expert}: {res.answer[:200]}", review["reason"], source="llm_critic" if review["by"] == "llm" else "validator",
                                   expert=task.expert)
                self.ctx.trace.event("task_rejected", task=task.id, reason=review["reason"])
                return
            task.feedback = review["reason"]
            self.ctx.trace.event("retry", task=task.id, next_attempt=attempt + 1, reason=review["reason"])
        task.status = "failed"
        self.ctx.trace.event("task_failed", task=task.id, reason="critic still not satisfied after retries: " + task.feedback)

    def compose(self, plan):
        ok = [t for t in plan.tasks if t.status == "done"]
        index = {f"{t.id}.E{i}": e for t in ok for i, e in enumerate(t.result["evidence"], 1)}
        payload = [{"task": t.id, "expert": t.expert, "goal": t.goal, "answer": t.result["answer"], "confidence": t.result["confidence"],
                    "assumptions": t.result["assumptions"], "not_checked": t.result["not_checked"],
                    "evidence": {f"{t.id}.E{i}": e["detail"][:160] for i, e in enumerate(t.result["evidence"], 1)}} for t in ok]
        problems = [{"task": t.id, "expert": t.expert, "status": t.status, "why": t.feedback} for t in plan.tasks if t.status != "done"]
        import json
        out = ask(self.ctx, self.compose_lane, [{"role": "system", "content": COMPOSE_SYSTEM},
                  {"role": "user", "content": json.dumps({"goal": plan.goal, "results": payload, "unfinished": problems}, default=str)}], "lead_compose")
        cited = set(re.findall(r"\[(T\d+\.E\d+)\]", out["text"]))
        bad = sorted(cited - set(index))
        self.ctx.trace.event("compose", cited=len(cited), unknown_citations=bad, unfinished=len(problems), model=out["model"])
        return {"answer": out["text"], "citations": {c: index[c] for c in sorted(cited & set(index))}, "unknown_citations": bad,
                "unfinished": problems, "not_checked": sorted({n for t in ok for n in t.result["not_checked"]}),
                "models_used": sorted({m for t in plan.tasks if t.result for m in t.result["models_used"] if m} | {out["model"]})}
