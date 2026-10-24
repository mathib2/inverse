# INVERSE: a crew of local AI agents that work, check each other, talk, and run on their own

**Eight agents on one computer, on local models, with no cloud. Give them a goal, or let them find their own: they plan, do the work, check each other, talk to each other, and answer with evidence, or say plainly what they could not check.**
Open Agent Hackathon 2026 · Track 03 (Reasoning Architecture) · Zetaris + Meterless + NVIDIA Nemotron

| Agent | What they do |
|---|---|
| **Atlas** | plans the mission, hands out the tasks, writes the answer with citations |
| **Vera** | reviews every result on its own lane and sends weak work back with a reason |
| **Warden** | keeps watch: new data, standing missions and queued goals start missions on their own |
| **Scout** | finds facts in the data platform and cites every query |
| **Euler** | works through derivations; every number is recomputed by a calculator |
| **Ada** | multi-step problems with tools; asks the others when a step needs them |
| **Sentinel** | reviews our own code for weaknesses; every finding is checked against the file and line |
| **Forge** | designs, builds and test-drives a new agent when the crew lacks one |

Names, tools and how they talk: `docs/CREW.md`. How they run unattended: `docs/agent/AUTONOMY.md`. Where each sponsor technology does real work: `docs/SPONSORS.md`.

## What you see

The Crew page (`http://<server>:8501`) is one box. Write a goal and press **Go**: Atlas plans, the agents work, Vera checks, and you watch it in plain sentences with their names. Then you get the answer, who did what, and what they said to each other. Below that, **On its own** shows Warden: whether it is awake, the standing missions and when they last ran, a box to queue a goal, and every mission it started by itself. **Past missions** replays any run, with its conversation, and no model is needed to replay. **Advanced** (sidebar) keeps the plan editor, the experts editor and the full trace.

## How a mission runs

1. **Plan.** Atlas turns the goal into at most five tasks, each for one agent by expertise, with dependencies. The agents review the plan from their own seats (each may reword only its own tasks). A plan that copies the schema's example text is refused; if the model cannot write a usable plan, a plan written by rule runs instead, and the trace says so.
2. **Work.** Each agent works with bounded tools: read-only SQL through a guard (one SELECT, known tables only), a calculator, code scan and reading inside this repository only, the shared memory, and for tool-using agents `ask_expert` (consult another agent, one level deep, small budget) and `post_message`. Independent tasks of a level run at the same time.
3. **Review.** Vera checks every result: fixed rules first (evidence present, every number in the answer found in a tool result, scope), then her own model lane. Weak work goes back with a reason; the agent retries with the note and its earlier evidence; an agent that repeats itself must change strategy, then is stopped. A rejected claim is written to shared memory as refuted.
4. **Answer.** Atlas writes the final answer from the accepted results only, citing every claim as `[T1.E2]`; what did not finish is listed verbatim by code, never paraphrased; with nothing accepted the answer is written by code.
5. **Trace.** `runs/<ts>/` holds `plan.json`, `trace.jsonl` (every model call with the served model, every tool call, every review), `messages.jsonl` (the conversation), `answer.json` and, for Warden's runs, `manifest.json`.

## The agents talk

A message bus per mission: an accepted result is announced to everyone, Vera's notes go to the agent they concern, Ada can ask another agent a question or leave a note, and each agent sees the messages addressed to it with its next task, marked as data from teammates, not instructions. The crew page shows the conversation live and in replay.

## The council

Any agent can propose a change to the crew at no cost, inside the JSON it already returns or through the `propose` tool: an agent's budget, tools or prompt; a standing mission; a note for shared memory; keeping an agent Forge built; or a code change, which always becomes a task card for people. Proposals are one small JSON object each (CW/1, `docs/COUNCIL.md`), with ids that merge the same idea into one proposal with several backers. The council decides them in short, rare sessions that a rule starts (three open, a backed one, a stale one, Warden's cycle, or a person), bounded to four model calls: Vera votes on the whole agenda in one call, the agent a change concerns votes on its own items, and a fixed rule adopts, rejects or defers. Adopted changes are applied by code, reversibly, and recorded in the book, the trace, the bus and the Meterless World Model.

## On its own

`scripts/watch.py` is Warden. Each cycle (every `WATCH_INTERVAL` seconds, 30 minutes by default) it runs queued goals first (`queue/goals.jsonl`, the crew page's box, or `--queue "..."`), then the standing missions in `missions.yaml` whose interval has passed (a data check every 12 hours, a code review and a memory digest every 24 hours), then one mission per machine whose sensor data changed. Every run has a manifest; a run interrupted by a crash is marked and its goal re-queued once; the memory sidecars are restarted if they stop answering. Nothing acts on equipment or writes to the data platform. On the workstation: `~/.local/bin/inverse-watch start|stop|status|log`.

## Memory with a trust order

Shared findings, refuted claims and reviewer lessons live in Meterless H-MEM across missions. A claim written by a deterministic check outranks a tool result, which outranks a model's claim: a refutation cannot be overwritten by a later model claim. Stop the sidecar and memory visibly breaks; that is an automated test.

## Local by default

`MODEL_PROVIDER=ollama` (default): every agent runs on the local models served on the workstation (`docs/agent/LOCAL_MODELS.md`). `MODEL_PROVIDER=nightshift` switches the same crew to Meterless Nightshift with NVIDIA Nemotron routes; nothing else changes. Lanes (`fast`, `deep`, `critic`) can point at different models (`LANE_*`), so Vera can review on a model other than the one that did the work.

## Sponsor technology

| Sponsor | Where it does real work |
|---|---|
| **Zetaris** | The only data path: Scout and Ada query the equipment registry, sensor specifications, maintenance history and samples through `run_sql` and the SQL guard (`team/experts.py: check_sql`); maintenance notes pass the injection guard before any model sees them; Warden's "new data" is a Zetaris query. Setup: `scripts/setup_zetaris.py`, `zetaris/sql/`. |
| **Meterless** | Nightshift: the provider on the sponsor path (same client, `clients/meterless.py`). H-MEM: shared memory with a trust order and reviewer lessons (`services/meterless-sidecar/server.ts`, `ledger.py`, `team/memory.py`). World Model: shared entities through the sidecar (`clients/world.py`); see `docs/SPONSORS.md` for its current use. Markovian: Sentinel's long code reviews run as bounded chunks with a compressed carryover (`services/meterless-sidecar/markovian/`, `team/custom.py`). |
| **NVIDIA Nemotron** | `nemotron-mini` (Nemotron-Mini-4B-Instruct) runs every agent locally through Ollama; on the Nightshift path the lanes map to Nemotron routes. The served model of every call is in the trace. |
| **Cursor** | Written with Claude Code; Cursor is installed on the team's laptop. Declared honestly in `docs/SPONSORS.md`. |

## Setup

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # Zetaris URL and key, MODEL_PROVIDER, model ids
(cd services/meterless-sidecar && npm install && npm run setup)   # vendors the Meterless reference engines
python scripts/setup_zetaris.py            # REST tables, cache, views (idempotent)
scripts/run_sidecars.sh                    # H-MEM/World Model (8100) and Markovian (8101)
PYTHONPATH=core .venv/bin/streamlit run ui/app.py --server.port 8501
```

## Usage

- The crew page: a goal and **Go**; **On its own**: queue a goal for Warden.
- CLI: `PYTHONPATH=core .venv/bin/python scripts/run_team.py "goal" --collaborate` runs one mission and prints the answer.
- Warden: `PYTHONPATH=core .venv/bin/python scripts/watch.py [--once] [--force] [--queue "goal"] [--status]`.
- Tests: `PYTHONPATH=core .venv/bin/python -m pytest -q tests` (no model and no network needed for the unit tests; the integration tests skip when the services are absent).

## Honest limitations

- The data platform federates one synthetic service (`data/README.md`); no real plant data was used.
- With the 4B local model, answers are short and sometimes thin even when the evidence is right; the deterministic layer keeps them honest, not eloquent. A larger model through Nightshift writes better plans and answers.
- One Warden per checkout; "new data" is a row count and a last timestamp.
- Only tool-using agents (Ada, and agents Forge builds) can start a conversation; the others answer when asked and read their inbox.
- Agents never change their own code unattended.

## License

MIT, see `LICENSE`.
