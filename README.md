# INVERSE: a crew of local AI agents that work, check each other, talk, and run on their own

[![tests](https://github.com/mathib2/inverse/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/mathib2/inverse/actions/workflows/tests.yml) · unit tests need no model and no network · Apache-2.0

**Eight agents on one computer, on local models, with no cloud. Give them a goal, or let them find their own: they plan, do the work, check each other, talk to each other, and answer with evidence, or say plainly what they could not check.**
Open Agent Hackathon 2026 · Track 03 (Reasoning Architecture) · Zetaris + Meterless + NVIDIA Nemotron

<!-- Screenshots go here (see docs/hackathon/SUBMISSION.md): the crew page during a mission and the council section.
![The crew page during a mission](docs/img/crew.png)
![The council: open proposals, the form, decisions](docs/img/council.png)
-->

```text
 a person, or Warden on its own ─goal─▶ Atlas plans at most five tasks, one agent each, with dependencies
                  ┌──────────────┬──────────────┼──────────────┬──────────────┐
                Scout          Euler           Ada         Sentinel         Forge
           read-only SQL  calculator on  tools; asks    scans our own  builds a new
           on Zetaris,    every step,    the others,    code, file     agent when
           cites queries  recomputes     one level deep and line       none fits
                  └──────────────┴──────────────┼──────────────┴──────────────┘
 Vera, on her own lane: fixed rules first, then only objections that quote the answer ─▶ sent back with the quote, or accepted
 Atlas writes the answer from accepted results only, citing [T1.E2]; what did not finish is listed verbatim, by code
 findings → shared memory (Meterless H-MEM, trust order) · proposals → the council · every step → runs/<ts>/, replayable
```

**Read next:** [What's where in docs/](docs/README.md) · [The crew](docs/CREW.md) · [Warden, on its own](docs/WARDEN.md) · [Tinker, on its own code](docs/TINKER.md) · [The council](docs/COUNCIL.md) · [Benchmark](docs/BENCH.md) · [Getting in](docs/operations/ACCESS.md) · [Sponsor technology](docs/hackathon/SPONSORS.md) · [Changelog](CHANGELOG.md)

**Why it matters.** A small engineering or operations team with one workstation, data it cannot send to a cloud and no budget for API credits still needs to know what its data says, whether its own code has holes, and what it has already ruled out. INVERSE gives that team a crew that works unattended on that workstation: it checks the data when it changes, reviews the repository every day, keeps a memory with a trust order, answers with citations or says plainly what it could not check, and improves its own configuration through a council that people can read and undo. Every decision is a file a person can replay. `docs/evidence/` holds real missions and a real council session.

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

## The repository

| folder | what is in it |
|---|---|
| `core/inverse_core/team/` | The crew, one module per agent: `lead.py` Atlas, `critic.py` Vera, `watch.py` Warden, `research.py` Scout, `reasoning.py` Euler, `custom.py` Ada and every config-built agent, `vulnerability.py` Sentinel, `architect.py` Forge. Beside them the run machinery: `expert.py` (task, result, budget), `plan.py`, `registry.py`, `tools.py`, `sql_guard.py`, `verify.py`, `memory.py`, `bus.py`, `council.py`, `gate.py`. |
| `core/inverse_core/` | Shared services with no agent logic: `chat.py` (the live feed), `notify.py` and `digest.py` (the phone), `trace.py`, `budget.py`, `ledger.py`, `injection_guard.py`; `clients/` talks to the model server, Zetaris, the World Model and Markovian. |
| `ui/` | The page: `app.py` (entry), `chat_ui.py` (the front page and its panels), `advanced_ui.py`, `warden_ui.py`, `council_ui.py`, `live_ui.py`, `auth.py` (sign-in), `parts.py`, `plain.py` (every word shown). |
| `experts/`, `prompts/` | Each expert's record and its instructions; the registry reads them. |
| `missions.yaml` | Warden's standing missions. |
| `scripts/` | What runs all the time (`watch.py`, `tinker.py`, `public_link.py` and their control scripts), `measure/` (benchmark, probes) and `admin/` (password, alerts, council, data setup). See `scripts/README.md`. |
| `tests/` | The unit tests: no model and no network. |
| `backlog_tests/` | Tests that define done for Tinker's backlog items. |
| `docs/` | How it works, how to run it, the submission and the records. See `docs/README.md`. |
| `services/`, `data/` | The Meterless sidecar and the synthetic data service; the data platform's SQL in `data/zetaris/`. |

## What you see

The front page (`http://<server>:8501`) is a chat with the crew. Ask a question at the bottom: Atlas plans, the agents work, Vera checks, and the answer arrives in the thread with who worked on it and how long it took. The panel on the right holds the answer's evidence, who did what and every step, the live feed of everything the agents say, the crew with what each one is working to fix, Warden, the council, and the alerts sent to your phone. The sidebar has New chat, Recent missions, Connections, Memory and the Advanced view (plan editor, agent editor, replay with traces).

## How a mission runs

1. **Plan.** Atlas turns the goal into at most five tasks, each for one agent by expertise, with dependencies. The agents review the plan from their own seats (each may reword only its own tasks). A plan that copies the schema's example text is refused; if the model cannot write a usable plan, a plan written by rule runs instead, and the trace says so.
2. **Work.** Each agent works with bounded tools: read-only SQL through a guard (one SELECT, known tables only), a calculator, code scan and reading inside this repository only, the shared memory, and for tool-using agents `ask_expert` (consult another agent, one level deep, small budget) and `post_message`. Independent tasks of a level run at the same time.
3. **Review.** Vera checks every result: fixed rules first (evidence present, every number in the answer found in a tool result, scope), then her own model lane, whose objections must quote the answer and are kept only when code finds the quoted words unsupported by the evidence. Weak work goes back with the quoted words and the reason; the agent retries with the note and its earlier evidence; an agent that repeats itself must change strategy, then is stopped. A rejected claim is written to shared memory as refuted.
4. **Answer.** Atlas writes the final answer from the accepted results only, citing every claim as `[T1.E2]`; what did not finish is listed verbatim by code, never paraphrased; with nothing accepted the answer is written by code.
5. **Trace.** `runs/<ts>/` holds `plan.json`, `trace.jsonl` (every model call with the served model, every tool call, every review), `messages.jsonl` (the conversation), `answer.json` and, for Warden's runs, `manifest.json`.

## The agents talk

A message bus per mission: an accepted result is announced to everyone, Vera's notes go to the agent they concern, Ada can ask another agent a question or leave a note, and each agent sees the messages addressed to it with its next task, marked as data from teammates, not instructions. The crew page shows the conversation live and in replay.

## The council

Any agent can propose a change to the crew at no cost, inside the JSON it already returns or through the `propose` tool: an agent's budget, tools or prompt; a standing mission; a note for shared memory; keeping an agent Forge built; or a code change, which always becomes a task card for people. Proposals are one small JSON object each (CW/1, `docs/COUNCIL.md`), with ids that merge the same idea into one proposal with several backers. The council decides them in short, rare sessions that a rule starts (three open, a backed one, a stale one, Warden's cycle, or a person), bounded to four model calls: Vera votes on the whole agenda in one call, the agent a change concerns votes on its own items, and a fixed rule adopts, rejects or defers. Adopted changes are applied by code, reversibly, and recorded in the book, the trace, the bus and the Meterless World Model.

## On its own

`scripts/watch.py` is Warden. Each cycle (every `WATCH_INTERVAL` seconds, 30 minutes by default) it runs queued goals first (`queue/goals.jsonl`, the crew page's box, or `--queue "..."`), then the standing missions in `missions.yaml` whose interval has passed (a data check every 12 hours, a code review and a memory digest every 24 hours), then one mission per machine whose sensor data changed. Every run has a manifest; a run interrupted by a crash is marked and its goal re-queued once; the memory sidecars are restarted if they stop answering. Nothing acts on equipment or writes to the data platform. On the workstation: `~/.local/bin/inverse-watch start|stop|status|log`.

**Tinker** (`scripts/tinker.py`, `docs/TINKER.md`) works on the crew's own code and knowledge around the clock, in a sandbox copy of the repository: it picks the next item of the crew's improvement list, researches it on the web, makes the smallest change (its engineer runs a coder model on its own lane, chosen by measurement), runs the tests and the probe of the agent concerned, and, only when nothing got worse, pushes a branch and puts it to the council: Sentinel reviews it, Vera votes, and after a veto window announced on your phone (free channels: ntfy push, Telegram, carrier SMS) the crew merges and deploys it itself. The **Live** mode of the page is one chat of everything the agents say, refreshed every three seconds.

## Memory with a trust order

Shared findings, refuted claims and reviewer lessons live in Meterless H-MEM across missions. A claim written by a deterministic check outranks a tool result, which outranks a model's claim: a refutation cannot be overwritten by a later model claim. Stop the sidecar and memory visibly breaks; that is an automated test.

## Local by default

`MODEL_PROVIDER=ollama` (default): every agent runs on the local models served on the workstation (`docs/operations/LOCAL_MODELS.md`). `MODEL_PROVIDER=nightshift` switches the same crew to Meterless Nightshift with NVIDIA Nemotron routes; nothing else changes. Lanes (`fast`, `deep`, `critic`) can point at different models (`LANE_*`), so Vera can review on a model other than the one that did the work.

## Sponsor technology

| Sponsor | Where it does real work |
|---|---|
| **Zetaris** | The only data path: Scout and Ada query the equipment registry, sensor specifications, maintenance history and samples through `run_sql` and the SQL guard (`team/sql_guard.py: check_sql`); maintenance notes pass the injection guard before any model sees them; Warden's "new data" is a Zetaris query. Setup: `scripts/admin/setup_zetaris.py`, `data/zetaris/`. |
| **Meterless** | Nightshift: the provider on the sponsor path (same client, `clients/meterless.py`). H-MEM: shared memory with a trust order and reviewer lessons (`services/meterless-sidecar/server.ts`, `ledger.py`, `team/memory.py`). World Model: shared entities through the sidecar (`clients/world.py`); see `docs/hackathon/SPONSORS.md` for its current use. Markovian: Sentinel's long code reviews run as bounded chunks with a compressed carryover (`services/meterless-sidecar/markovian/`, `team/custom.py`). |
| **NVIDIA Nemotron** | With the default configuration every agent's model calls run on `nemotron-mini` (Nemotron-Mini-4B-Instruct) through Ollama; a lane can be pointed at another local model (`LANE_CRITIC`), and on the Nightshift path the lanes map to Nemotron routes. The served model of every call is in the trace. |
| **Cursor** | Written with Claude Code; Cursor is installed on the team's laptop. Declared honestly in `docs/hackathon/SPONSORS.md`. |

## Setup

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # Zetaris URL and key, MODEL_PROVIDER, model ids
(cd services/meterless-sidecar && npm install && npm run setup)   # vendors the Meterless reference engines
python scripts/admin/setup_zetaris.py            # REST tables, cache, views (idempotent)
scripts/run_sidecars.sh                    # H-MEM/World Model (8100) and Markovian (8101)
PYTHONPATH=core .venv/bin/streamlit run ui/app.py --server.port 8501 --server.address 127.0.0.1
```

The UI listens on loopback only. To reach it from another machine, use an SSH tunnel (`ssh -L 8501:127.0.0.1:8501 <user>@<server>`) or `tailscale serve --bg 8501` on a tailnet.

**From a phone.** Install the Tailscale app on the phone, sign in to the same tailnet, and open `http://<machine-name>:8501` (the workstation's MagicDNS name or tailnet address). Traffic between the phone and the workstation is encrypted by the tailnet; nothing is opened to the internet.

**Sign-in page.** `python scripts/admin/set_password.py root` asks for a password twice and writes `UI_USER` and a salted hash (`UI_PASSWORD_HASH`) into `.env`; nothing secret is in the repository. Restart the UI and every visitor gets a sign-in page first; a device stays signed in for a week, **Sign out** in the sidebar ends that early, and a wrong password slows the next try. Without `UI_PASSWORD_HASH` there is no sign-in page.

## Usage

- The front page: ask in the chat; in the Live panel, queue a goal for Warden or answer Tinker with `veto auto/...` or `approve auto/...`.
- CLI: `PYTHONPATH=core .venv/bin/python scripts/admin/run_team.py "goal" --collaborate` runs one mission and prints the answer.
- Warden: `PYTHONPATH=core .venv/bin/python scripts/watch.py [--once] [--force] [--queue "goal"] [--status]`.
- Tests: `PYTHONPATH=core .venv/bin/python -m pytest -q tests` (no model and no network needed for the unit tests; the integration tests skip when the services are absent).

## Honest limitations

- The data platform federates one synthetic service (`data/README.md`); no real plant data was used.
- With the 4B local model, answers are short and sometimes thin even when the evidence is right; the deterministic layer keeps them honest, not eloquent. A larger model through Nightshift writes better plans and answers.
- One Warden per checkout; "new data" is a row count and a last timestamp.
- Only tool-using agents (Ada, and agents Forge builds) can start a conversation; the others answer when asked and read their inbox.
- Agents never change their own code unattended.

## License

Apache-2.0, see `LICENSE`. The Meterless reference engines vendored by `npm run setup` into `services/meterless-sidecar/vendor/` are Apache-2.0 too.
