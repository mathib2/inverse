# The crew

INVERSE is a crew of AI agents that run on one computer, on local models, with no cloud. They reverse-engineer machines from
sensor data, review code, look facts up, work through problems, check each other's work, talk to each other, and keep going
on their own. Names are what people see; the identifiers in parentheses are what configs, plans, traces and messages use.

| Agent | Identifier | What they do | Tools |
|---|---|---|---|
| **Atlas** | `lead` | Plans the mission (at most five tasks), hands them out by expertise, lets the crew review the plan, writes the final answer with citations, and reports verbatim what did not finish | the plan and the crew |
| **Vera** | `critic` | Reviews every result on its own lane: fixed rules first (evidence present, numbers grounded, scope), then a model; sends weak work back with a reason, rejects what cannot work | rules, a model |
| **Warden** | `watch` | Keeps watch: new sensor data starts a physics check; a wear flag, a rejection or a refusal starts a crew mission; standing missions run on their schedule; queued goals are taken first | the schedule, the queue |
| **Newton** | `physics` | Reverse-engineers a machine's physics from its sensor data: proposes model forms, fits them, and lets six physics checks and a falsification test decide; refuses when the data cannot answer | the physics pipeline |
| **Scout** | `research` | Finds facts in the data platform (registry, sensor specs, maintenance history) with read-only SQL and cites every query | `run_sql` |
| **Euler** | `reasoning` | Works through a question step by step; every number is recomputed by a calculator and a mismatch forces a repair | `calc` |
| **Ada** | `solver` | Multi-step problems that mix facts and numbers; asks Scout, Newton or Euler when a step needs them and leaves notes for the others | `run_sql`, `calc`, `memory`, `ask_expert`, `post_message` |
| **Sentinel** | `vulnerability` | Defensive review of this repository's own code; every finding must point at a real file and line or it is dropped; long reviews run through Meterless Markovian | `scan`, `read_file`, `grep`, `list_files`, `memory` |
| **Forge** | `architect` | Designs, builds and test-drives a new agent when the crew lacks one for a task; the new agent is held to the same budgets and review | `list_experts`, `design_expert`, `create_expert`, `test_expert` |

## How they talk

Every mission has a message bus (`runs/<ts>/messages.jsonl`, mirrored in the trace): an accepted result is announced to
everyone, Vera's notes go to the agent they concern, Ada can ask another agent a question (`ask_expert`, one level deep,
small budget) or leave a note (`post_message`), and each agent sees the messages addressed to it with its next task, marked
as data from teammates, not instructions. The crew page shows the conversation live and in replay.

## How they run on their own

Warden (`scripts/watch.py`) loops on the workstation (`~/.local/bin/inverse-watch start|stop|status|log`). Each cycle: queued
goals first (`queue/goals.jsonl`, written from the crew page or `--queue "..."`), then the standing missions whose interval
has passed (`missions.yaml`), then every machine whose sensor data changed. Every run leaves a manifest; interrupted runs are
re-queued once; the memory sidecars are restarted if they stop answering. Details: `docs/agent/AUTONOMY.md`.

## Local by default

`MODEL_PROVIDER` defaults to `ollama`: every agent runs on the local models the workstation serves (`docs/agent/LOCAL_MODELS.md`).
`nightshift` switches the same crew to Meterless Nightshift for the sponsor recording; nothing else changes.

## Adding an agent

Drop a YAML file in `experts/` (or `experts.local/`): `name` (identifier), `callsign` (the name people see), `kind`, `role`,
`system_prompt` or `system_prompt_file`, `tools`, `model_lane`, `budget`. The registry validates it; Atlas can delegate to it on
the next mission. Forge can also build one during a mission, and the Advanced page can keep it.
