# Experts: how the team is customized

The team is a lead agent plus experts. **Experts are config, not code.** This page says how to change one, add one, or let the lead create one, and what the safety limits are.

## Where an expert is defined

| File | Who writes it | Purpose |
|---|---|---|
| `experts/<name>.yaml` | the repo | the built-in crew: `research`, `reasoning`, `solver`, `vulnerability`, `architect` |
| `experts.local/<name>.yaml` (gitignored) | you, or the UI panel **Experts · customize the team** | a new expert, or an override of a built-in with the same name. Deleting the file brings the built-in back unchanged |
| the run | the lead (`new_experts` in its plan) | a `custom` expert for one run; **Keep it** in the UI writes it to `experts.local/` |

Fields:

```yaml
name: solver                      # lowercase letters, digits, _
kind: custom                      # research | reasoning | custom | vulnerability | architect
role: "One or two sentences the lead reads when deciding whom to give a task."
system_prompt_file: prompts/solver.md   # or: system_prompt: "inline instructions" (inline wins)
tools: [run_sql, calc, memory]    # from the list below; unknown names are refused at load
model_lane: deep                  # fast | deep | critic (team/lanes.py; LANE_* in .env overrides)
budget: {tool_calls: 8, tokens: 50000, seconds: 300}
enabled: true                     # false keeps the config but takes the expert off the team
```

A config error (unknown kind, tool or lane, bad name, non-positive budget) is reported with the file and field; nothing half-loads.

## Kinds

- **research**: read-only SQL on Zetaris through a guard (single SELECT, known tables only); every claim cites a query, numbers are checked against the rows.
- **reasoning**: decompose, solve, and recompute every calculation with `safe_eval`; a mismatch triggers one repair turn and is visible to the Critic.
- **custom**: a bounded tool loop defined only by its config: prompt, tools, lane, budget. One tool call per reply; every tool result is evidence; numbers in the answer that no tool produced lower the confidence and are listed under *not checked*. `solver` is one.
- **architect**: designs, creates and tests a new expert when the team lacks one. Its tools act on the registry (`list_experts`, `design_expert`, `create_expert`, `test_expert`); what it creates is a `custom` expert with a fixed budget, held to the same scopes and review as any other, and the UI can keep it. The lead may plan a task for an expert that does not exist yet, as long as it depends on the architect's task; when that task's turn comes the Lead checks the expert was created and fails the task clearly otherwise.
- **vulnerability**: defensive code review of **this repository**. The deterministic `scan` runs first; the model triages its hits and may read code; every finding it reports is then checked against the file (inside the repo, line exists, snippet on that line) and dropped otherwise. Unknown severities are lowered, never raised.

## Tools (`core/inverse_core/team/tools.py`)

All read-only, all charged to the expert's budget, every call traced (`tool` event).

| Tool | What it does | Limits |
|---|---|---|
| `run_sql` | one SELECT on the Zetaris tables | same guard as the Research expert; maintenance notes pass the injection filter |
| `calc` | arithmetic | `safe_eval`: numbers and a few math functions, nothing else |
| `list_files`, `read_file`, `grep` | browse code we own | inside the repository root only; `.env`, keys and certificates are never readable; size-capped |
| `scan` | fixed weak-spot rules with severities | code and config files; `tests/` skipped |
| `memory` | what the team found or ruled out | H-MEM, namespace `team:shared` |

## Long reviews through Markovian

When the Markovian service is up (`npm run markovian` in `services/meterless-sidecar`, port 8101) and a review touches two or more files, the vulnerability expert runs it as a Meterless Markovian chain: one bounded chunk per file (the scan hits plus the code around them), a compressed carryover state between chunks instead of the whole history, findings verified per chunk, and the H-MEM team memory injected into the first chunk. The trace records `markovian_start`, one `markovian_chunk` per file and `markovian_done` with the engine's estimated savings and the measured Nightshift usage. Without the service the expert falls back to its single tool loop.

## Collaboration on the plan

With `--collaborate` (CLI) or the UI toggle, each expert that has a task reviews the plan from its own seat before anything runs: the physics expert by rule, the others on their own lane with their own prompt. An expert may reword **only its own tasks**; the lead applies the changes, records a `plan_review` event (what changed, what is missing) and re-validates the plan. The user still edits and approves the plan in the UI.

## Safety scope

- The vulnerability expert is **defensive, own-code only**. A task that asks for offensive work (exploit, payload, brute force, "break into", ...) or names an external system (a URL, an IP, a domain) is refused before any model call: the refusal is traced (`refused_scope`), returned as `policy` evidence, rejected by the Critic by rule (no retries), and written to team memory as refuted so it is not attempted again.
- No tool writes anything, runs code, or leaves the machine except the Zetaris query and the Nightshift model calls the whole app already makes.
- Secrets stay in `.env`; the tools cannot read it, and nothing from it is logged.
