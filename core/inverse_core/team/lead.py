"""Lead: plan -> delegate (by context) -> collect -> Critic (can send back) -> compose. It routes; experts do the work.
A stuck detector forces a strategy change when a retry repeats the previous answer, and escalates when it repeats twice.
The Lead may define a new expert when no configured one fits a task, and the experts may review the plan before it runs."""
from __future__ import annotations

import copy
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from ..budget import BudgetExceeded
from .bus import Bus
from .critic import Critic
from .vulnerability import scope_check
from .crew import roster
from .expert import ExpertBudget, ExpertResult, Task
from .llmcall import BadReply, ask
from . import limits
from .plan import PLACEHOLDER, Plan, PlanError
from .verify import claim_numbers, unverified_numbers
from .registry import ConfigError
from .tools import CODE_TOOLS, Tools
from .words import results_in_words


PLAN_SYSTEM = """You are the lead of a team of experts. Decompose the user's goal into at most 5 tasks and assign each to ONE expert.
Delegate by what each task needs. Use depends_on when a task needs another task's result. Do not use an expert you did not list or define.
Experts:
{experts}
Known equipment IDs: {equipment}
Return ONLY JSON: {{"tasks":[{{"id":"T1","goal":"<one self-contained instruction, written by you for THIS goal>","expert":"<a name from the list>","depends_on":[]}}]}}
Write every goal in your own words for the goal you were given; never copy the example text or leave a placeholder.
Use research to look facts up in the registry, sensor specs, maintenance history and samples (counts and ranges, not raw dumps), reasoning for derivations and calculations from given facts, solver for multi-step work with tools and for any summary or digest of what the crew knows (it has the shared memory tool), vulnerability for a review of our own code.
Routing rules, apply the first that fits: a calculation whose numbers are all in the goal -> one task, reasoning alone. A summary, digest, or "what do we know" -> one task, solver alone. A lookup of facts in the registry, sensors, maintenance or samples -> research, one task per distinct lookup, and nothing else. A lookup followed by a computation on it -> research first, then one reasoning task that depends on it. A review of our own code -> one task, vulnerability alone.
If no expert fits a task and an architect is on the team, give the architect a task to design, create and test an expert for that need, assign the dependent task to the expert name the architect should create (lowercase snake_case), and make it depend on the architect's task. Without an architect, define one (at most 2) by adding "new_experts":[{{"name":"snake_case","role":"one sentence","system_prompt":"its instructions","tools":["..."],"model_lane":"fast|deep"}}] to the JSON, using only these tools: {tools}. Prefer an existing expert when one fits."""

COMPOSE_SYSTEM = """Write the final answer for the user from the accepted expert results. Rules: use only facts present in the results; cite every claim as
[T1.E2] (task id, evidence number); say which expert produced each part; state uncertainty and what was NOT checked. The goal may ask several
things: answer each of them from the results and say plainly which one has no result. Tasks that did not finish are listed for you under
"unfinished": do not describe them or guess why they failed (that is reported separately, verbatim); just do not fill their gap.
Be concise (under 220 words)."""

REVIEW_TAIL = ("\nYou are reviewing the team plan before work starts. For YOUR tasks only, say whether each is doable as written with "
               "your tools, and fix the wording if not (keep the same id). Return ONLY JSON: "
               '{"ok":true|false,"changes":[{"id":"T1","goal":"rewritten self-contained instruction"}],"missing":["what you need that no task provides"]}')
NEW_EXPERT_BUDGET = {"tool_calls": 6, "tokens": 40000, "seconds": 240}
PLAN_MAX_TOKENS, REVIEW_MAX_TOKENS, COMPOSE_MAX_TOKENS = 700, 400, 650          # reply caps: at 10 tokens/s on a CPU an unbounded reply is the long tail


def _norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


CODE_WORDS = re.compile(r"\b(code|repositor(y|ies)|repo|security|weakness(es)?|vulnerab\w*|exploit\w*)\b", re.I)
PLANNED_PREFIX = re.compile(r"^Using the accepted results from the earlier tasks, answer this in plain words:\s*")   # a lesson keeps what the task was about
DAY_WORDS = re.compile(r"\b(?:how\s+many|number\s+of)\s+(?:days|weeks)\b|\bdays?\s+(?:passed|elapsed|between|apart)\b", re.I)   # a date difference: Euler's days_between
CALC_WORDS = re.compile(r"\b(compute|calculate|derive|deriv\w+|multipl\w+|times|divide\w*|convert\w*|weight|weigh\w*|force|torque|energy|frequency|damping|ratio|percent\w*|average|mean|formula|equation"
                        r"|(?:how\s+many|number\s+of)\s+(?:days|weeks)|days?\s+(?:passed|elapsed|between|apart)"
                        r"|why|whether|should|needs?|compare\w*|explain|assess\w*|diagnos\w+|recommend\w*|judge)\b", re.I)   # a computation or a judgement: Euler after Scout
DATA_WORDS = re.compile(r"\b(registry|maintenance|sensors?|samples?|datasets?|records?|tables?|rows|stored|specification\w*|history|sql|quer\w+)\b", re.I)
LACK_WORDS = re.compile(r"\b(we have no|there is no|no (?:converter|expert|agent|tool|one) (?:for|that|who)|nobody (?:can|knows)|the crew (?:lacks|cannot)|none of (?:you|the agents) can)\b", re.I)
PATH_WORD = re.compile(r"[\w./-]+/[\w./-]+")                                 # a repository path named in a goal
LOOKUP_WORDS = re.compile(r"^\W*(how many|how much|list|what is|what are|what was|which|when|show|name|give me)\b", re.I)   # a plain lookup: Scout alone
GIVEN = re.compile(r"\b([A-Za-z]+)\s+(?:is|=|equals)\s+(-?\d+(?:\.\d+)?)\s*([A-Za-z][\w/^]{0,7})?")   # "gravity is 1.62 m/s^2" -> gravity = 1.62 m/s^2


def given_values(goal):
    """The constants a goal states ('gravity is 1.62 m/s^2', 'g = 9.81'), as 'name = value unit; ...'; '' when it states none."""
    out = []
    for m in GIVEN.finditer(str(goal or "")):
        out.append(f"{m.group(1)} = {m.group(2)}" + (f" {m.group(3)}" if m.group(3) else ""))
    return "; ".join(dict.fromkeys(out))


SUMMARY_WORDS = re.compile(r"\b(summari[sz]e|digest|what (do|does) (we|the crew|the team) know|found so far|ruled out|still unchecked)\b", re.I)


def rule_plan(goal, names, equipment):
    """A plan written by rule, for when the model cannot write one (a small local model may copy the schema's example text twice).
    A machine named in the goal gets Scout's look at the registry, specs and history, then Euler answers the goal from it; code words
    send the goal to Sentinel; summary words to Ada with the shared memory; anything else to Ada. Deterministic and traced."""
    tasks = []

    def add(expert, text, deps=()):
        if expert in names:
            tasks.append(Task(f"T{len(tasks) + 1}", text, expert, list(deps)))

    machines = [e for e in equipment if re.search(rf"(?<![\w-]){re.escape(e)}(?![\w-])", goal, re.I)][:2]
    if CODE_WORDS.search(goal) and not machines:
        add("vulnerability", goal)
    elif machines:
        add("research", f"With read-only queries on the registry, the sensor specifications, the maintenance history and the sample tables for "
                        f"{' and '.join(machines)}, answer: {goal}")
        if CALC_WORDS.search(goal) or not LOOKUP_WORDS.search(goal):          # a plain lookup ends with Scout; anything else goes on to Euler
            add("reasoning", f"Using the accepted results from the earlier tasks, answer this in plain words: {goal}", deps=[t.id for t in tasks])
    elif SUMMARY_WORDS.search(goal):
        add("solver", goal + " Use the shared memory tool first.")
    elif LOOKUP_WORDS.search(goal) and DATA_WORDS.search(goal):                # a lookup that names no machine (the registry as a whole): Scout
        add("research", goal)
    if not tasks:
        add("solver" if "solver" in names else ("reasoning" if "reasoning" in names else next(iter(names))), goal)
    return Plan(goal, tasks)


ABOUT_US = re.compile(r"\bwhat (?:can|could) (?:you|the crew|this crew|inverse) do\b|\bwhat are you(?:r)? (?:capable of|able to do|good at|capabilities|skills|abilities)\b"
                      r"|\bwho are you\b|\bintroduce yourself\b|\bhow can you help\b|\bwhat can i ask\b|^\s*help\s*[?.!]*\s*$", re.I)


def about_us(goal, configs):
    """The answer to a question about the crew itself, written from its own records: who is on it, what each one does, what to ask.
    No model call: a 4B planner read "what are you capable of" as a task to build a new expert (27 calls, 431 s, no answer)."""
    rows = roster(configs)
    lines = "; ".join(f"{r['name']} {r['does'].rstrip('.')}" for r in rows)
    text = (f"I am INVERSE, a crew of {len(rows)} AI agents running on a local model. {lines}. "
            "Ask what the registry, the sensors, the maintenance history or the sample tables say about a machine (for example P-104), "
            "give a calculation with its numbers, ask to review a file of this repository for security weaknesses, or ask what the crew has found so far. "
            "Every answer cites the evidence it comes from, and Vera checks it before you see it.")
    ev = [{"type": "roster", "source": "the crew's own records (experts/*.yaml and the crew list)", "detail": f"{len(rows)} agents: " + ", ".join(r["name"] for r in rows)}]
    return ExpertResult(text, ev, 1.0, [], []).to_dict()


def simple_goal(goal, equipment=()):
    """A goal whose plan a rule writes as well as the model would, and in no time: a plain lookup, an arithmetic with its numbers in
    the goal and no machine to look up, a summary, a review of a named path. Not a goal that says the crew lacks something (the
    architect path), not a long or two-part goal."""
    g = str(goal or "").strip()
    if not g or len(g) > 300 or LACK_WORDS.search(g) or " then " in g.lower() or ";" in g:
        return None
    machines = [m for m in equipment if re.search(rf"(?<![\w-]){re.escape(m)}(?![\w-])", g, re.I)]
    if CODE_WORDS.search(g) and PATH_WORD.search(g) and not machines:
        return "a review of a named path"
    if SUMMARY_WORDS.search(g):
        return "a summary of what the crew knows"
    if LOOKUP_WORDS.search(g) and DATA_WORDS.search(g) and not CALC_WORDS.search(g):
        return "a plain lookup"
    if CALC_WORDS.search(g) and claim_numbers(g) and not DATA_WORDS.search(g) and not machines:
        return "an arithmetic with its numbers in the goal"
    return None


class Lead:
    def __init__(self, ctx, registry, memory, critic=None, max_attempts=3, plan_lane="plan", compose_lane="plan", rule_fallback=True, rule_first=True):
        self.rule_first = rule_first                                          # plain goals are planned by rule, without a model call
        self.ctx, self.registry, self.memory = ctx, registry, memory
        self.rule_fallback = rule_fallback                                    # a plan by rule when the model cannot write one (small local models)
        self.critic = critic or Critic(ctx)
        self.max_attempts, self.plan_lane, self.compose_lane = max_attempts, plan_lane, compose_lane
        self.bus = getattr(ctx, "bus", None) or Bus()                         # the experts' conversation: results, reviews, questions, answers
        ctx.bus = self.bus

    def plan_system(self):
        """The planner's system prompt as sent: byte-stable per process, so the model server's prefix cache holds it."""
        return PLAN_SYSTEM.format(experts="\n".join(f"- {n}: {r}" for n, r in self.registry.roles().items()),
                                  equipment=", ".join(self.ctx.equipment) or "none", tools=", ".join(Tools.SPECS)) + limits.note(getattr(self.ctx, "root", "."), "lead")

    def plan(self, goal, collaborate=False, votes=1):
        """votes > 1 samples that many plans at temperature 0.7 and keeps the most common task/expert structure
        (self-consistency, Wang et al. 2022): a majority over samples is more reliable than one greedy decode."""
        if ABOUT_US.search(goal or "") and len(str(goal)) < 160:             # a question about the crew: answered from its records, no model call
            t = Task("T1", goal, "lead", [])
            t.status, t.result = "done", about_us(goal, self.registry.configs)
            plan = Plan(goal, [t])
            self.ctx.trace.event("plan", goal=goal, tasks=[t.__dict__ | {"result": None}], model=None, by="code", reason="a question about the crew, answered from its records")
            return plan
        kind = simple_goal(goal, self.ctx.equipment) if self.rule_first else None
        if kind:                                                              # no model call: the rule plan, then the same guard every plan gets
            plan = self._guard(rule_plan(goal, self.registry.names(), self.ctx.equipment).validate(self.registry.names(), self.creators()))
            self.ctx.trace.event("plan", goal=goal, tasks=[t.__dict__ | {"result": None} for t in plan.tasks], model=None, by="rule", reason=f"{kind}: planned by rule, no model call")
            return self.review_plan(plan) if collaborate else plan
        msgs = [{"role": "system", "content": self.plan_system()}, {"role": "user", "content": goal}]
        before = set(self.registry.configs)                                  # experts proposed by losing or invalid samples are dropped again
        if votes > 1:
            plan = self._vote(goal, msgs, votes)
            if plan is not None:
                self._prune(before, plan)
                return self.review_plan(plan) if collaborate else plan
        err = ""
        for _ in range(2):
            out = ask(self.ctx, self.plan_lane, msgs, "lead_plan", json_reply=True, max_tokens=PLAN_MAX_TOKENS)
            try:
                plan = self._parse_plan(goal, out["json"])
                self._prune(before, plan)
                self.ctx.trace.event("plan", goal=goal, tasks=[t.__dict__ | {"result": None} for t in plan.tasks], model=out["model"])
                return self.review_plan(plan) if collaborate else plan
            except (PlanError, ConfigError, KeyError, TypeError, AttributeError) as e:
                err = str(e)
                msgs += [{"role": "assistant", "content": out["text"]}, {"role": "user", "content": "Invalid plan: " + err + ". Return corrected JSON."}]
        self._prune(before, None)
        if self.rule_fallback:                                                # the crew must keep working unattended: a plan written by rule
            plan = rule_plan(goal, self.registry.names(), self.ctx.equipment).validate(self.registry.names(), self.creators())
            self.ctx.trace.event("plan", goal=goal, tasks=[t.__dict__ | {"result": None} for t in plan.tasks], model=None, by="rule",
                                 reason="the model's plans were not usable: " + err[:200])
            return self.review_plan(plan) if collaborate else plan
        raise PlanError("the planner could not produce a valid plan: " + err)

    def _prune(self, before, plan):
        """Drop experts registered for this run during planning that the chosen plan does not use."""
        used = {t.expert for t in plan.tasks} if plan else set()
        for name in set(self.registry.configs) - before:
            if name not in used and self.registry.drop(name):
                self.ctx.trace.event("expert_dropped", name=name, reason="proposed during planning but not used by the chosen plan")

    def _mem(self, op, *args, **kw):
        """Memory is advisory: an H-MEM hiccup is traced, never fatal to the run."""
        try:
            return getattr(self.memory, op)(*args, **kw)
        except Exception as e:
            self.ctx.trace.event("memory_error", op=op, error=f"{type(e).__name__}: {str(e)[:200]}")
            return [] if op in ("lessons", "findings") else None

    def _parse_plan(self, goal, j):
        for spec in (j.get("new_experts") or [])[:2]:
            self._create_expert(spec)
        return self._guard(Plan.from_dict({"goal": goal, "tasks": j["tasks"][:5]}).validate(self.registry.names(), self.creators()))

    def _guard(self, plan):
        """Three routing rules a 4B planner gets wrong often enough to cost a mission, applied by code and traced: a data lookup
        given to the reasoning agent goes to research; a summary of what the crew knows goes to the solver (it has the memory
        tool); a goal that asks for a computation gets a reasoning task after the lookups when the plan has none."""
        names, changes = self.registry.names(), []
        path = next((m.group(0).rstrip("/.") for m in PATH_WORD.finditer(plan.goal)), None)
        goal = plan.goal.strip()
        if len(plan.tasks) == 1 and plan.tasks[0].expert not in ("research", *self.creators()) and goal not in plan.tasks[0].goal:
            plan.tasks[0].goal = goal                                         # a one-task plan loses nothing by carrying the goal itself: the planner's paraphrase can only drop a detail or be the example text
            changes.append(f"{plan.tasks[0].id}: the goal verbatim (a one-task plan)")
        if len(plan.tasks) == 1 and plan.tasks[0].expert == "solver" and "reasoning" in names and CALC_WORDS.search(goal) and claim_numbers(goal) and not DATA_WORDS.search(goal):   # a number to compute with, never an id such as P-104
            plan.tasks[0].expert = "reasoning"                                # plain arithmetic with the numbers in the goal: Euler computes and self-checks; Ada would look for facts that are not there
            changes.append(f"{plan.tasks[0].id}: solver -> reasoning (arithmetic with nothing to look up)")
        for t in plan.tasks:
            if t.expert == "reasoning" and "research" in names and DATA_WORDS.search(t.goal) and not CALC_WORDS.search(t.goal):
                t.expert, _ = "research", changes.append(f"{t.id}: reasoning -> research (a data lookup)")
            elif t.expert == "reasoning" and not CALC_WORDS.search(t.goal) and not re.search(r"\d", t.goal):   # nothing to compute: Euler would invent arithmetic
                to = "vulnerability" if CODE_WORDS.search(t.goal) and "vulnerability" in names else ("solver" if "solver" in names else None)
                if to:
                    t.expert, _ = to, changes.append(f"{t.id}: reasoning -> {to} (no numbers and nothing to compute)")
            if t.expert == "vulnerability" and path and not PATH_WORD.search(t.goal):
                t.goal, _ = f"{t.goal} Path: {path}", changes.append(f"{t.id}: the path from the goal added ({path})")
        if SUMMARY_WORDS.search(plan.goal) and "solver" in names and len(plan.tasks) == 1 and plan.tasks[0].expert in ("reasoning", "research", "solver"):
            if plan.tasks[0].expert != "solver":
                plan.tasks[0].expert, _ = "solver", changes.append(f"{plan.tasks[0].id}: -> solver (a summary needs the shared memory)")
            if "memory" not in plan.tasks[0].goal.lower():
                plan.tasks[0].goal, _ = plan.tasks[0].goal + " Use the shared memory tool first.", changes.append(f"{plan.tasks[0].id}: the memory tool named")
        if len(plan.tasks) == 1 and plan.tasks[0].expert == "research" and plan.goal.strip() not in plan.tasks[0].goal:   # Scout sees the whole question, not a paraphrase of half of it
            plan.tasks[0].goal, _ = f"{plan.tasks[0].goal} (The whole goal: {plan.goal.strip()})", changes.append(f"{plan.tasks[0].id}: the whole goal appended")
        if CALC_WORDS.search(plan.goal) and "reasoning" in names and plan.tasks and all(t.expert == "research" for t in plan.tasks) and len(plan.tasks) < 5:   # lookups only
            deps = [t.id for t in plan.tasks]
            plan.tasks.append(Task(f"T{len(plan.tasks) + 1}", f"Using the accepted results from the earlier tasks, answer this in plain words: {plan.goal}", "reasoning", deps))
            changes.append(f"{plan.tasks[-1].id}: reasoning added (the goal asks for a computation)")
        for t in plan.tasks:                                                      # days between two dates: Euler counts them with days_between; Scout's SQL date functions were refused three times
            if t.expert == "research" and DAY_WORDS.search(t.goal) and "reasoning" in names:
                looks = [o.id for o in plan.tasks if o is not t and o.expert == "research" and t.id not in o.depends_on]
                if t.depends_on or looks:
                    t.expert, t.depends_on = "reasoning", list(t.depends_on) or looks
                    t.goal = f"Using the dates in the accepted results from the earlier tasks, count the days: {t.goal}"
                    changes.append(f"{t.id}: research -> reasoning (days between dates are computed, not queried)")
        for t in plan.tasks:                                                      # a computation in Scout's own task tempts the model to compute, and the numbers it makes up are refused three times
            if t.expert == "research" and CALC_WORDS.search(t.goal) and any(o.expert in ("reasoning", "solver") for o in plan.tasks if o is not t):
                t.goal = f"Look up the values this needs and report them exactly as the queries return them; the computation is another task's: {goal}"
                changes.append(f"{t.id}: Scout looks up only (the computation is another task's)")
        if LACK_WORDS.search(plan.goal) and self.creators() and not any(t.expert in self.creators() for t in plan.tasks) and len(plan.tasks) < 5:
            arch = self.creators()[0]                                          # the goal says the crew lacks something: Forge builds it first, the work waits for it
            need = re.sub(r"\W+", "_", re.sub(r"\?.*$", "", plan.goal.lower()))[:24].strip("_") or "new"
            name = f"{need}_expert"
            main = next((t for t in plan.tasks if t.expert not in ("research",)), plan.tasks[-1] if plan.tasks else None)
            try:
                before = copy.deepcopy(plan.tasks)
                t1 = Task("T0", f"Design, create and test an expert named {name} that can do this for the crew: {plan.goal}", arch, [])
                plan.tasks.insert(0, t1)
                if main is not None:
                    main.expert, main.depends_on = name, sorted(set(main.depends_on) | {"T0"})
                plan.validate(names, self.creators())
                changes.append(f"T0: {arch} builds {name} first (the goal says the crew lacks it)")
            except Exception as ex:                                            # a plan the validator refuses is left as it was
                plan.tasks[:] = before
                self.ctx.trace.event("plan_guard_skipped", reason=f"{type(ex).__name__}: {str(ex)[:120]}")
        if changes:
            self.ctx.trace.event("plan_guard", changes=changes)
            plan.validate(names, self.creators())
        return plan

    @staticmethod
    def signature(plan):
        """What a plan is, structurally: which expert does how many tasks, and how many dependencies each has."""
        return tuple(sorted((t.expert, len(t.depends_on)) for t in plan.tasks))

    def _vote(self, goal, msgs, votes):
        samples, invalid = [], 0
        for i in range(votes):
            try:                                                             # an unreadable sample counts as invalid; it does not end the vote
                out = ask(self.ctx, self.plan_lane, msgs, f"lead_plan_sample{i + 1}", json_reply=True, temperature=0.7, max_tokens=PLAN_MAX_TOKENS)
                samples.append((self._parse_plan(goal, out["json"]), out["model"]))
            except (PlanError, ConfigError, KeyError, TypeError, AttributeError, ValueError):
                invalid += 1
        if not samples:
            self.ctx.trace.event("plan_votes", samples=0, invalid=invalid, chosen=None)
            return None
        counts = {}
        for p, _ in samples:
            counts[self.signature(p)] = counts.get(self.signature(p), 0) + 1
        best = max(counts.items(), key=lambda kv: kv[1])[0]
        plan, model = next((p, m) for p, m in samples if self.signature(p) == best)
        self.ctx.trace.event("plan_votes", samples=len(samples), invalid=invalid, agreement=counts[best],
                             signatures=[" ".join(f"{e}:{d}" for e, d in s) for s in counts], chosen=" ".join(f"{e}:{d}" for e, d in best))
        self.ctx.trace.event("plan", goal=goal, tasks=[t.__dict__ | {"result": None} for t in plan.tasks], model=model, votes=votes)
        return plan

    def creators(self):
        """Experts that can create experts (the architect kind): a plan may assign a task to a not-yet-existing expert if it depends on them."""
        return [n for n, c in self.registry.configs.items() if c.get("kind") == "architect" and n in self.registry.experts]

    def _forge_by_rule(self, task, goal):
        """The expert a plan names but nobody built: a template expert with the calculator and read-only SQL, registered for this run
        and traced as forge_by_rule. The constants the goal states ride along as given values, so a Moon question is not answered
        with Earth's gravity. The architect's judgement is better when it works; this is what happens when it does not."""
        name = str(task.expert)
        if name in self.registry.experts or not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", name):
            return name in self.registry.experts
        given = given_values(goal)
        try:
            self._create_expert({"name": name, "role": f"Answers, with tools, questions like: {str(goal)[:120]}",
                                 "system_prompt": f"You are {name}, an expert the crew built for this: {str(goal)[:200]} "
                                                  + (f"GIVEN VALUES, use exactly these in calc and no textbook value in their place: {given}. " if given else "")
                                                  + "Settle every number with the calc tool and every fact with one read-only SELECT; cite the tool results; say plainly what you could not check.",
                                 "tools": ["calc", "run_sql"], "model_lane": "fast"})
            self.ctx.trace.event("forge_by_rule", task=task.id, name=name)
        except Exception as ex:
            self.ctx.trace.event("forge_by_rule_failed", task=task.id, name=name, error=f"{type(ex).__name__}: {str(ex)[:120]}")
        return name in self.registry.experts

    def _create_expert(self, spec):
        """An expert the planner proposed: always a tool-using `custom` expert with a fixed budget; the registry validates the
        rest (name, tools, lane) and refuses what it does not know. Registered for this run; the UI can keep it."""
        if not isinstance(spec, dict):
            raise ConfigError("new_experts entries must be objects")
        if str(spec.get("name", "")) in self.registry.configs:
            return                                                                   # already on the team: just use it
        c = self.registry.add({"name": spec.get("name"), "kind": "custom", "role": spec.get("role", ""), "tools": list(spec.get("tools") or []),
                               "system_prompt": str(spec.get("system_prompt") or spec.get("role") or ""), "model_lane": spec.get("model_lane") or "fast",
                               "budget": dict(NEW_EXPERT_BUDGET)})
        self.ctx.trace.event("expert_created", name=c["name"], role=c["role"], tools=c["tools"], lane=c["model_lane"], config=c)

    def review_plan(self, plan):
        """Each expert with a task looks at the plan from its own seat: a deterministic expert checks by rule, the others on their
        own lane with their own prompt. Only an expert's own tasks may be reworded; the Lead applies the changes and re-validates."""
        tasks = {t.id: t for t in plan.tasks}
        for name in dict.fromkeys(t.expert for t in plan.tasks):
            if name not in self.registry.experts:                              # an expert the architect will create: nobody to review its task yet
                continue
            expert, mine = self.registry.experts[name], [t for t in plan.tasks if t.expert == name]
            reviewer = getattr(expert, "review_plan", None)
            if reviewer:
                review = reviewer(plan, mine)
            else:
                payload = {"goal": plan.goal, "all_tasks": [{"id": t.id, "expert": t.expert, "goal": t.goal, "depends_on": t.depends_on} for t in plan.tasks],
                           "your_tasks": [t.id for t in mine]}
                try:
                    out = ask(self.ctx, expert.lane, [{"role": "system", "content": (expert.prompt or expert.role) + REVIEW_TAIL},
                                                      {"role": "user", "content": json.dumps(payload)}], f"{name}_plan_review", json_reply=True, max_tokens=REVIEW_MAX_TOKENS)
                    review = dict(out["json"]) | {"model": out["model"]}
                except (ValueError, KeyError, TypeError):
                    review = {"ok": True, "changes": [], "missing": [], "note": "review reply was not valid JSON; plan kept as drafted"}
            changed = []
            for c in review.get("changes") or []:
                t = tasks.get(str(c.get("id"))) if isinstance(c, dict) else None
                goal = str(c.get("goal") or "").strip() if isinstance(c, dict) else ""
                if t and t.expert == name and goal and goal != t.goal:
                    kept = [e for e in self.ctx.equipment if e in t.goal and e not in goal]
                    if PLACEHOLDER.search(goal) or kept:                      # a copied example or a dropped machine never replaces a goal
                        self.ctx.trace.event("plan_review_ignored", expert=name, task=t.id, reason="placeholder text" if not kept else f"dropped {kept}")
                        continue
                    t.goal = goal
                    changed.append(t.id)
            self.ctx.trace.event("plan_review", expert=name, ok=bool(review.get("ok", True)), changed=changed,
                                 missing=[str(m) for m in (review.get("missing") or [])][:5], model=review.get("model"))
        return plan.validate(self.registry.names(), self.creators())

    @staticmethod
    def levels(plan):
        """Tasks grouped by dependency depth: everything in one level depends only on earlier levels, so it can run at the same time."""
        depth = {}
        for t in plan.order():
            depth[t.id] = 1 + max((depth[d] for d in t.depends_on), default=-1)
        groups = {}
        for t in plan.tasks:
            groups.setdefault(depth[t.id], []).append(t)
        return [groups[k] for k in sorted(groups)]

    def run(self, plan, run_dir=None, parallel=2):
        """Executes the plan level by level; independent tasks in a level run concurrently (at most `parallel` at once), which
        is where most of the wall-clock time of a multi-expert run goes."""
        names = self.registry.names() + (["lead"] if any(t.expert == "lead" and t.status == "done" for t in plan.tasks) else [])
        plan.validate(names, self.creators())
        self.ctx.budget.t0 = time.time()                                      # the wall-clock budget starts when the plan is approved, not drafted
        self.ctx.trace.event("plan_approved", tasks=[t.id for t in plan.tasks], pending_experts=plan.pending_experts(names), parallel=parallel)
        if run_dir:
            plan.save(run_dir)
        done = {}
        for level in self.levels(plan):
            ready = []
            for task in level:
                if task.status == "done" and task.result:                     # answered by code when it was planned: nothing to run
                    continue
                blocked = [d for d in task.depends_on if done[d].status != "done"]
                if blocked and task.expert not in self.registry.experts and all(done[d].expert in self.creators() for d in blocked) \
                        and self._forge_by_rule(task, plan.goal):              # the architect failed to build it: a rule did, so the work goes on
                    blocked = []
                if self.stopped():                                            # a person pressed Stop: what did not start is listed in the answer, verbatim
                    task.status, task.feedback = "skipped", "stopped by a person before it started"
                    self.ctx.trace.event("task_skipped", task=task.id, reason="stopped")
                elif blocked:
                    task.status, task.feedback = "failed", f"skipped: dependency {blocked} did not produce an accepted result"
                    self.ctx.trace.event("task_skipped", task=task.id, blocked_by=blocked)
                elif task.expert not in self.registry.experts and not self._forge_by_rule(task, plan.goal):   # planned for an expert nobody created
                    task.status, task.feedback = "failed", f"no expert named {task.expert!r} exists: the architect task did not create it"
                    self.ctx.trace.event("task_failed", task=task.id, reason=task.feedback)
                else:
                    task.context = "\n".join(f"[{d}] {done[d].result['answer']}" for d in task.depends_on)
                    ready.append(task)
            if len(ready) > 1 and parallel > 1:
                workers = min(parallel, len(ready))
                self.ctx.trace.event("level", tasks=[t.id for t in ready], parallel=workers)
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="expert") as pool:
                    list(pool.map(self._execute, ready))
            else:
                for task in ready:
                    self._execute(task)
            for task in level:
                done[task.id] = task
            if run_dir:
                plan.save(run_dir)
        council = getattr(self.ctx, "council", None)
        if council:                                                           # proposals written by rule from what this run showed
            try:
                council.observe(plan, self.ctx.trace.events, run_dir or getattr(self.ctx.trace, "dir", ""))
            except Exception as e:
                self.ctx.trace.event("council_error", op="observe", error=f"{type(e).__name__}: {str(e)[:200]}")
        return plan

    def stopped(self):
        """True once a person asked the mission to stop (ctx.stop); experts finish the step they are on, nothing new starts."""
        s = getattr(self.ctx, "stop", None)
        return bool(s is not None and s.is_set())

    def _execute(self, task):
        if self.stopped():                                                    # queued behind a running task when Stop was pressed
            task.status, task.feedback = "skipped", "stopped by a person before it started"
            self.ctx.trace.event("task_skipped", task=task.id, reason="stopped")
            return
        expert = self.registry.experts[task.expert]
        if set(getattr(expert, "tools", None) or []) & CODE_TOOLS:            # scope is a property of the tool layer, not of one expert class
            ok, why = scope_check(task.goal)
            if not ok:
                self.ctx.trace.event("refused_scope", agent=task.expert, task=task.id, reason=why)
                task.status, task.feedback = "rejected", "refused: " + why
                self._mem("refute", f"{task.expert}: {task.goal[:160]}", "refused: " + why, source="validator", confidence=1.0, expert=task.expert)
                self.ctx.trace.event("task_rejected", task=task.id, reason=task.feedback)
                return
        task.lessons = self._mem("lessons", task.expert, goal=task.goal) or []   # what reviewers told this expert before, on a task like this one (Reflexion)
        if task.lessons:
            self.ctx.trace.event("lessons", task=task.id, expert=task.expert, count=len(task.lessons))
        last, repeats, rejected_once, last_rule = None, 0, "", ""
        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1 and self.stopped():
                task.status, task.feedback = "failed", "stopped by a person before another attempt; the last note was: " + task.feedback
                self.ctx.trace.event("task_failed", task=task.id, reason=task.feedback)
                return
            task.attempts, task.status = attempt, "running"
            budget = self.registry.budget_for(task.expert)
            task.messages = [m for m in self.bus.inbox(task.expert)
                             if not (m.get("type") == "result" and m.get("task") in task.depends_on)        # already in task.context
                             and not (m.get("type") == "review" and m.get("task") == task.id)]              # already in task.feedback
            self.ctx.trace.event("delegate", task=task.id, expert=task.expert, attempt=attempt, lane=expert.lane, feedback=task.feedback or None,
                                 messages=len(task.messages) or None)
            try:
                res = expert.run(task, self.memory, budget)
            except BudgetExceeded as e:
                task.status, task.feedback = "failed", f"budget: {e}"
                self.ctx.trace.event("task_failed", task=task.id, reason=task.feedback)
                return
            except Exception as e:                                            # an expert crash is a failed task, not a crashed run
                task.feedback = (f"Your previous reply could not be read as JSON ({e}). Reply with exactly one JSON object and no prose."
                                 if isinstance(e, BadReply) else f"{type(e).__name__}: {e}")
                self.ctx.trace.event("expert_error", task=task.id, error=f"{type(e).__name__}: {e}"[:300])
                if attempt == self.max_attempts:
                    task.status = "failed"
                    return
                continue
            if not isinstance(res.answer, str) or not res.answer.strip():     # a JSON number or null where text was due: ask again, never crash
                task.feedback = 'Your reply\'s "answer" field must be a non-empty string.'
                self.ctx.trace.event("expert_error", task=task.id, error="answer was empty, not text" if isinstance(res.answer, str) else f"answer was {type(res.answer).__name__}, not text")
                if attempt == self.max_attempts:
                    task.status = "failed"
                    return
                continue
            task.result = res.to_dict()
            self.ctx.trace.event("expert_result", task=task.id, expert=task.expert, confidence=res.confidence, evidence=len(res.evidence),
                                 models=res.models_used, tool_calls=budget.tool_calls, tokens=budget.tokens)
            if last is not None and _norm(res.answer) == last and rejected_once:   # the same answer after a reviewer's reject: the reject stands
                task.status, task.feedback = "rejected", rejected_once
                self._mem("refute", f"{task.expert}: {res.answer[:200]}", rejected_once, source="llm_critic", expert=task.expert)
                self.ctx.trace.event("task_rejected", task=task.id, reason=rejected_once)
                return
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
            try:
                review = self.critic.review(task, task.result)
            except BudgetExceeded as e:
                task.status, task.feedback = "failed", f"budget during review: {e}"
                self.ctx.trace.event("task_failed", task=task.id, reason=task.feedback)
                return
            except Exception as e:                                            # the reviewer is down: keep the result, say it was not checked
                note = f"the Critic could not review this result ({type(e).__name__}: {str(e)[:120]})"
                task.result["not_checked"] = list(task.result.get("not_checked") or []) + [note]
                self.ctx.trace.event("critic", task=task.id, verdict="unreviewed", reason=note, by="error")
                task.status, task.feedback = "done", ""
                return
            reason = str(review.get("reason") or "")
            if review["verdict"] == "accept":
                task.status, task.feedback = "done", ""
                self.bus.post(task.expert, "all", res.answer, type="result", task=task.id, confidence=res.confidence)
                self._file(res, task)
                for f in res.findings:                                        # shared memory only holds what survived review, with what its author left unchecked
                    self._mem("add_finding", f"{task.expert}: {str(f.get('claim', ''))[:200]}", f.get("evidence") or [], source=f.get("source", "fitter"),
                              confidence=f.get("confidence", 0.7), expert=task.expert, not_checked=task.result.get("not_checked") or [])
                if res.findings:
                    self.ctx.trace.event("memory_write", task=task.id, findings=len(res.findings))
                return
            if reason:                                                        # the reviewer's note goes on the bus, addressed to the expert
                self.bus.post("critic", task.expert, reason, type="review", task=task.id, verdict=review["verdict"])
            kept = review.get("problems") or []
            if review.get("by") == "llm" and kept:                             # only an objection that checked out becomes a lesson, in its checkable words
                self._mem("add_lesson", task.expert, (f"{PLANNED_PREFIX.sub('', task.goal)[:80]}: " + "; ".join(f"\u00ab{str(k.get('quote'))[:80]}\u00bb {k.get('why') or k.get('check')}" for k in kept[:2]))[:240])
            if review["verdict"] == "reject" and review.get("by") == "llm" and attempt == 1 and self.max_attempts > 1:   # once: a second reject is final
                self.ctx.trace.event("reject_retried", task=task.id, reason=reason[:200])   # a 4B reviewer's reject is a strong revise: one more try with the quote
                rejected_once = reason
            elif review["verdict"] == "reject":
                task.status, task.feedback = "rejected", reason
                self._mem("refute", f"{task.expert}: {res.answer[:200]}", reason, source="llm_critic" if review.get("by") == "llm" else "validator",
                          expert=task.expert)
                self.ctx.trace.event("task_rejected", task=task.id, reason=reason)
                return
            task.feedback = reason
            if review.get("by") == "rule" and reason and reason == last_rule:    # the same rule objection twice: a third try repeats it (a code review lost 15 min this way)
                task.status, task.feedback = "failed", "the same objection twice: " + reason
                self.ctx.trace.event("task_failed", task=task.id, reason=task.feedback)
                return
            last_rule = reason if review.get("by") == "rule" else ""
            if not getattr(expert, "retryable", True):                       # a deterministic expert would return the same answer
                task.status = "failed"
                self.ctx.trace.event("task_failed", task=task.id, reason="critic sent it back but the expert is deterministic: " + task.feedback)
                return
            self.ctx.trace.event("retry", task=task.id, next_attempt=attempt + 1, reason=reason)
        task.status = "failed"
        self.ctx.trace.event("task_failed", task=task.id, reason="critic still not satisfied after retries: " + task.feedback)

    def _file(self, res, task):
        """Proposals that rode on an accepted result go to the council; a council hiccup is traced, never fatal to the run."""
        council = getattr(self.ctx, "council", None)
        for p in (getattr(res, "proposals", None) or [])[:2] if council else []:
            try:
                council.file(p, by=task.expert, run=getattr(self.ctx.trace, "dir", ""))
            except Exception as e:
                self.ctx.trace.event("council_error", op="file", error=f"{type(e).__name__}: {str(e)[:200]}")

    def compose(self, plan, run_dir=None):
        ok = [t for t in plan.tasks if t.status == "done"]
        index = {f"{t.id}.E{i}": e for t in ok for i, e in enumerate(t.result["evidence"], 1)}
        payload = [{"task": t.id, "expert": t.expert, "goal": t.goal, "answer": t.result["answer"], "confidence": t.result["confidence"],
                    "assumptions": t.result["assumptions"], "not_checked": t.result["not_checked"],
                    "evidence": {f"{t.id}.E{i}": str(e.get("detail") or "")[:160] for i, e in enumerate(t.result["evidence"], 1)}} for t in ok]
        problems = [{"task": t.id, "expert": t.expert, "status": t.status, "why": t.feedback} for t in plan.tasks if t.status != "done"]
        self.ctx.trace.event("composing", accepted=len(ok), unfinished=len(problems))
        by_code = True                                                        # the accepted results in plain paragraphs, each with its citations: no model involved (words.py)
        if not ok:                                                            # nothing survived review: the answer is written by code, never by a model
            text, model, fallback = results_in_words(ok), None, True
        elif len(ok) == 1 or (len(ok) == 2 and sum(len(str(t.result["answer"])) for t in ok) < 900):   # short results ARE the answer: cited by code, no writer call
            text, model, fallback = results_in_words(ok), None, False
        else:
          try:
            out = ask(self.ctx, self.compose_lane, [{"role": "system", "content": COMPOSE_SYSTEM},
                      {"role": "user", "content": json.dumps({"goal": plan.goal, "results": payload, "unfinished": problems}, default=str)}], "lead_compose", max_tokens=COMPOSE_MAX_TOKENS)
            text, model, fallback, by_code = out["text"].strip(), out["model"], False, False
            facts = [e for t in ok for e in t.result["evidence"]] + [{"detail": str(t.result["answer"])} for t in ok] + [{"detail": plan.goal}]
            invented = unverified_numbers(text, facts)
            if invented:                                                      # the writer added a number no accepted result holds (it once wrote "32 days" for a task that had failed)
                self.ctx.trace.event("compose_numbers_refused", numbers=invented[:8], model=model)
                text = results_in_words(ok) + (f"\n\n*(The writer added {'a number' if len(invented) == 1 else 'numbers'} no accepted result holds "
                                               f"({', '.join(invented[:4])}); this answer was assembled by code from the accepted results.)*")
                fallback, by_code = True, True
          except Exception as e:                                              # the writer is down: assemble the answer by code, nothing is lost
            text = results_in_words(ok) + f"\n\n*(The writer model was unavailable, {type(e).__name__}; this summary was assembled by code from the accepted results.)*"
            model, fallback, by_code = None, True, True
        cited = set(re.findall(r"\[(T\d+\.E\d+)\]", text))
        if ok and not (cited & set(index)):                                   # the writer cited nothing: the sources are listed by code, so every answer can be checked
            text += "\n\nSources: " + "; ".join(f"{t.id} ({t.expert}) " + " ".join(f"[{t.id}.E{i}]" for i in range(1, len(t.result["evidence"]) + 1)) for t in ok)
            cited = set(re.findall(r"\[(T\d+\.E\d+)\]", text))
        bad = sorted(cited - set(index))
        self.ctx.trace.event("compose", cited=len(cited), unknown_citations=bad, unfinished=len(problems), model=model, fallback=fallback, by_code=by_code)
        answer = text
        if problems:                                                          # written by code, verbatim: the model never paraphrases a failure
            answer += "\n\n**Not completed**\n" + "\n".join(f"- {p['task']} ({p['expert']}) {p['status']}: {p['why']}" for p in problems)
        result = {"answer": answer, "citations": {c: index[c] for c in sorted(cited & set(index))}, "unknown_citations": bad,
                  "unfinished": problems, "not_checked": sorted({n for t in ok for n in t.result["not_checked"]}),
                  "models_used": sorted({e["model"] for e in self.ctx.trace.events if e["kind"] == "llm" and e.get("model")}), "goal": plan.goal}
        if run_dir:                                                           # with plan.json and trace.jsonl this makes the run replayable without a model
            with open(os.path.join(run_dir, "answer.json"), "w") as f:
                json.dump(result, f, indent=1, default=str)
        return result
