# How every agent is built

Every agent in the crew has the same shape, whether it is one of the three fixed roles (Atlas the lead, Vera the critic,
Warden the watch) or one of the experts the registry loads from `experts/*.yaml` (Scout, Euler, Ada, Sentinel, Forge). This
is the shape the current references describe for an agent (a model, tools, memory, a planner, an evaluator, and gates
written in code between the steps), and `tests/test_structure.py` checks it.

## The record

Each expert is one YAML file with the same nine fields: `name` (the identifier the code uses), `callsign` (the name people
see), `kind` (which Python class runs it: `research`, `reasoning`, `custom`, `architect`), `role` (one sentence the planner
reads), `system_prompt_file` (its instructions, under `prompts/`), `tools` (what it may call, by name, from the one toolbox),
`model_lane` (`fast`, `deep` or `critic`), `budget` (tool calls, tokens and seconds per task) and `enabled`. The council can
change a budget, a tool or a prompt addendum with an undo; nothing else is edited by an agent.

## The loop

Every expert runs one task the same way:

1. **Fetch by code first.** What the task plainly asks for is looked up before the model speaks: Scout's columns, Ada's
   facts, counts and totals, Sentinel's scan and the lines around its hits, Euler's names resolved from the context.
2. **One model call, bounded.** A reply cap per call, a tool-call budget, a wall-clock budget, JSON only.
3. **Check by code.** Every number in the answer must be in the evidence; an empty answer, a bare word, a repeated tool call,
   a number in prose, a filter nobody asked for are caught by rules, not by taste.
4. **Repair once, then stop.** A failed check gets one more turn with the reason; a second failure ends the task honestly.
5. **Evidence out.** The result carries its evidence items, a confidence, what was assumed and what was not checked. A
   conclusion without evidence is refused by `require_evidence`.
6. **Review.** Vera's rules run first; what the tool results prove is accepted by code; the model judges only what is left,
   and an objection must quote the answer and fail against the evidence to send work back.
7. **Memory.** An accepted finding is written to the shared memory with its source and confidence; a refuted one is written
   as refuted, so the next mission does not repeat it.

## The measure

Each agent has its own probe set in `scripts/probe.py` (small, checkable questions) and a mark out of ten (accuracy,
honesty, efficiency, robustness). The marks are in `docs/AGENT_REPORT.md`; what an agent still gets wrong is read from the
latest probe and from the report's list, shown on the Crew panel, and worked on by Tinker. The probes measure the model's
own path: the Atlas probe plans without the rule-first shortcut and the Vera probe reviews without the code-first
acceptance, so a mark moves only when the agent does.

## What is deliberately not shared

The lead plans and composes but never calls a tool; the critic never writes an answer; the watch never speaks to a model.
Scout may only read the data platform; Sentinel may only read code we own; Tinker may only write inside its sandbox.
