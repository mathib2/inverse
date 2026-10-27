# INVERSE: a crew of local AI agents that work, check each other, talk, and run on their own

[![tests](https://github.com/mathib2/inverse/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/mathib2/inverse/actions/workflows/tests.yml) · unit tests need no model and no network · Apache-2.0

**Eight agents on local models, with no cloud model: NVIDIA Nemotron-Mini-4B, served by Meterless Nightshift on a laptop's GPU, with the workstation's own Ollama as the fallback. A ninth, Tinker, works on their code around the clock. Give them a goal, or let them find their own: they plan, do the work, check each other, talk to each other, and answer with evidence, or say plainly what they could not check.**
Open Agent Hackathon 2026 · Track 03 (Reasoning Architecture) · Zetaris + Meterless + NVIDIA Nemotron

<!-- Screenshots go here (docs/archive/IMPROVEMENT_PLAN.md item 9): the front page during a mission with the Live panel open, and the Council panel.
![The front page during a mission](docs/img/chat.png)
![The Council panel: open proposals, the form, decisions](docs/img/council.png)
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

**Why it matters.** A small engineering or operations team with one workstation, data it cannot send to a cloud and no budget for API credits still needs to know what its data says, whether its own code has holes, and what it has already ruled out. INVERSE gives that team a crew that works unattended on that workstation: it checks the data when it changes, reviews its own code four files at a time every six hours, changed files first, keeps a memory with a trust order, answers with citations or says plainly what it could not check, and improves its own configuration through a council that people can read and undo. Every decision is a file a person can replay. `docs/evidence/` holds three real missions with their plans, traces and conversations (one is Warden's maintenance review of P-104 on Nightshift), every benchmark round and each agent's probe marks. Council sessions stay on the workstation under `council/` and are not in the repository.

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
| **Tinker** | works on the crew's own code in a sandbox around the clock; it merges on its own only a change that measurably helps, after the tests, Sentinel's review, Vera's vote and a veto window announced on your phone; anything else stays a branch for a person |

## The repository

| folder | what is in it |
|---|---|
| `core/inverse_core/team/` | The crew, one module per agent: `lead.py` Atlas, `critic.py` Vera, `watch.py` Warden, `research.py` Scout, `reasoning.py` Euler, `custom.py` Ada and every config-built agent, `vulnerability.py` Sentinel, `architect.py` Forge. Beside them the run machinery: `expert.py` (task, result, budget), `plan.py`, `registry.py`, `build.py` (wires a run), `llmcall.py` (every model call, traced), `lanes.py` (lane to model), `tools.py`, `sql_guard.py`, `verify.py`, `memory.py`, `bus.py`, `council.py` and `council_wire.py` (CW/1), `gate.py`, `limits.py` (each agent's known flaws, from its probes and `docs/AGENT_REPORT.md`), `crew.py` (the names). |
| `core/inverse_core/` | Shared services with no agent logic: `chat.py` (the live feed), `notify.py` and `digest.py` (the phone), `trace.py`, `budget.py`, `ledger.py`, `injection_guard.py`, `missions.py` (standing missions), `datasets.py` (the synthetic data); `clients/` talks to the model server, Zetaris, the World Model and Markovian, and `clients/sidecars.py` names this checkout's own sidecars. |
| `ui/` | The page: `app.py` (entry), `chat_ui.py` (the front page and its panels), `advanced_ui.py`, `warden_ui.py`, `council_ui.py`, `live_ui.py`, `auth.py` (sign-in), `parts.py`, `plain.py` (every word shown). |
| `experts/`, `prompts/` | Each expert's record and its instructions; the registry reads them. |
| `missions.yaml` | Warden's standing missions: `data_check` every 12 hours, `code_review` every 6, `memory_digest` every 24. `missions.local.yaml` (not in git) holds the council's and people's changes and overrides it. |
| `scripts/` | What runs all the time (`watch.py`, `tinker.py`, `public_link.py` and their control scripts), `measure/` (benchmark, probes) and `admin/` (password, alerts, council, data setup, publishing the public copy). See `scripts/README.md`. |
| `tests/` | 203 tests in 26 files; none needs a model or the internet. The six that need live services (`test_integration.py`, the real-engine test in `test_markovian.py`) skip when Zetaris or the Meterless engines are not there, so CI runs 197. |
| `backlog_tests/` | Where a test that defines done for one of Tinker's backlog items goes (`backlog_tests/README.md`). None is written yet, so a change merges on its own only when the agent's probe rises. |
| `docs/` | How it works, how to run it, the submission and the records. See `docs/README.md`. |
| `services/`, `data/` | The Meterless sidecar and the synthetic data service; the data platform's SQL in `data/zetaris/`. |

## What you see

The front page (port 8501; Setup says how to reach it) is a chat with the crew. On a fresh page, pick one of three example questions, or ask your own at the bottom: Atlas plans, the agents work, Vera checks, and the answer arrives in the thread with who worked on it and how long it took. **Stop** lets the step in progress finish and starts nothing new. The panel on the right switches between Answer, Evidence, Who did what, Steps, Live (everything the agents say, with a box to queue a goal for Warden or answer Tinker), Crew (each agent and what it is working to fix), Warden, Council and Alerts (what was sent to your phone). The sidebar has New chat, the Chat and Advanced switch (the Advanced view: plan editor, agent editor, replay with traces), Recent (the last eight missions), Share with your team (the public link, when one runs), Connections, Memory and, with the sign-in page on, Sign out.

## How a mission runs

1. **Plan.** Atlas turns the goal into at most five tasks, each for one agent by expertise, with dependencies. Plain goals (a lookup, a summary, an arithmetic with its numbers, a review of a named path) and Warden's standing and new-data missions are planned by rule, with no model call; a question about the crew is answered from its records. On the page and in Warden, a plan with three or more tasks is reviewed by the agents from their own seats (each may reword only its own tasks; `run_team.py --collaborate` always asks for this review). A plan that copies the schema's example text is refused; if the model cannot write a usable plan, a plan written by rule runs instead, and the trace says so.
2. **Work.** Each agent works with bounded tools: read-only SQL through a guard (one SELECT, known tables only), a calculator, code scan and reading inside this repository only, the shared memory, and for tool-using agents `ask_expert` (consult another agent, one level deep, small budget) and `post_message`. Independent tasks of a level run two at a time.
3. **Review.** Vera checks every result: fixed rules first (evidence present, every number in the answer found in a tool result, scope). An answer whose every number is in its own query rows or calculator results, with nothing hedged or left unchecked, is then accepted by code. Anything else goes to her own model lane, whose objections must quote the answer and are kept only when code finds the quoted words unsupported by the evidence. Weak work goes back with the quoted words and the reason; the agent retries with the note and its earlier evidence; an agent that repeats itself must change strategy, then is stopped. A rejected claim is written to shared memory as refuted.
4. **Answer.** Atlas writes the final answer from the accepted results only, citing every claim as `[T1.E2]` (one accepted result, or two short ones, is the answer itself, cited by code). If the writer adds a number that no accepted result holds, the answer is assembled by code instead. What did not finish is listed verbatim by code, never paraphrased; with nothing accepted the answer is written by code.
5. **Trace.** `runs/<ts>/` holds `plan.json`, `trace.jsonl` (every model call with the served model and its provider, every tool call, every review), `messages.jsonl` (the conversation), `answer.json` and, for Warden's runs, `manifest.json`.

## The agents talk

A message bus per mission: an accepted result is announced to everyone, Vera's notes go to the agent they concern, Ada can ask another agent a question or leave a note, and each agent sees the messages addressed to it with its next task, marked as data from teammates, not instructions. The front page shows the conversation as it happens in the Live panel and, for every answer, in its Steps panel; the Advanced view's replay shows it for any saved run.

## The council

Any agent can propose a change to the crew at no cost, inside the JSON it already returns or through the `propose` tool: an agent's budget, tools or prompt; a standing mission; a note for shared memory; keeping an agent Forge built; or a code change, which always becomes a task card for people. Proposals are one small JSON object each (CW/1, `docs/COUNCIL.md`), with ids that merge the same idea into one proposal with several backers. The council decides them in short, rare sessions that a rule starts: three open proposals, one with two backers, or one that has waited a day, and at most one session an hour. Warden asks at the end of each cycle whether one is due, and a person can call one. A session is bounded to four model calls: Vera votes on the whole agenda in one call, the agent a change concerns votes on its own items, and a fixed rule adopts, rejects or defers. A prompt addition, a new tool, or a new mission or mission goal that an agent files becomes a task card for people, like a code change. Adopted changes are applied by code, reversibly, and recorded in the book, the trace, the bus and the Meterless World Model.

## On its own

`scripts/watch.py` is Warden. Each cycle (every `WATCH_INTERVAL` seconds, 30 minutes by default; a queued goal cuts the wait short) it runs queued goals first (`queue/goals.jsonl`, the box in the Live or Warden panel, or `--queue "..."`), then the standing missions in `missions.yaml` whose interval has passed (a data check every 12 hours, a code review of four files every 6 hours, changed files first, and a memory digest every 24 hours), then one mission per machine whose sensor data changed, then a council session when the council's rules say one is due. Every run has a manifest; a run interrupted by a crash is marked and its goal re-queued once; the memory sidecars are restarted if they stop answering. A digest of what the crew said goes to your phone every 30 minutes by default (`NOTIFY_DIGEST_MINUTES`). Nothing acts on equipment or writes to the data platform. On the workstation, from `~/inverse-live`: `~/.local/bin/inverse-watch start|stop|restart|status|log` (installed from `scripts/inverse-watch`).

**Tinker** (`scripts/tinker.py`, `docs/TINKER.md`), the crew's ninth member, works on the crew's own code and knowledge around the clock, in a sandbox copy of the repository: it picks the next item of the crew's improvement list (`docs/AGENT_REPORT.md` and failing probes), researches it (from the crew's own probe evidence, and on the web every third cycle or whenever there is no such evidence), makes the smallest change (its engineer runs a coder model on its own lane, chosen by measurement: `qwen2.5-coder:7b` in the deployed sandbox), runs the tests and the probe of the agent concerned, and, only when nothing got worse, pushes a branch and puts it to the council. The sandbox runs on the workstation's Ollama, not on Nightshift. It merges on its own only a change that measurably helps (the agent's probe rose, or the item's own test now passes): Sentinel reviews it, Vera votes, and after a 30-minute veto window announced on your phone (free channels: ntfy push, Telegram, carrier SMS, Textbelt) the crew merges and deploys it itself; anything else stays a branch for a person. The **Live** panel of the front page is one chat of everything the agents say, refreshed every three seconds.

## Memory with a trust order

Shared findings, refuted claims and reviewer lessons live in Meterless H-MEM across missions. A claim written by a deterministic check outranks a tool result, which outranks a model's claim: a refutation cannot be overwritten by a later model claim. An agent sees a reviewer's lesson only on a task like the one the lesson came from. Stop the sidecar and memory visibly breaks; that is an automated test.

## Nightshift first, the workstation as fallback

`MODEL_PROVIDER=nightshift` (the code's default when `.env` names none): every model call of the eight agents goes first to Meterless Nightshift, which serves NVIDIA Nemotron-Mini-4B from its lane `local-runtime/nemotron-mini-4b-instruct-q4-k-m` on a Windows laptop's RTX 3060 (about 59 tokens a second) and reaches the workstation through an SSH reverse tunnel (`docs/operations/NIGHTSHIFT_TUNNEL.md`). Set `LANE_FAST`, `LANE_DEEP` and `LANE_CRITIC` to that route, as the workstation's `.env` does; otherwise the lanes ask Nightshift for larger hosted Nemotron routes (`team/lanes.py`). When Nightshift cannot answer (the laptop is asleep, the tunnel is down), the call goes to the workstation's own Ollama with the same model, and Nightshift is tried first again two minutes later. Each call's provider is in the trace, and the page shows **AI online · fallback** while the workstation answers. `MODEL_PROVIDER=ollama` runs everything on the workstation (`docs/operations/LOCAL_MODELS.md`). Lanes (`fast`, `deep`, `critic`) can point at different models (`LANE_*`), so Vera can review on a model other than the one that did the work. On the benchmark's eight checkable goals (`docs/BENCH.md`) the crew scores 8/8 on Nightshift (40 s in round 19, 32 s in each of rounds 23 and 24) and 8/8 on the workstation's CPU (222 s, round 17). Rounds 20 to 22 fell to 6/8, 6/8 and 7/8, because every task was shown its agent's newest reviewer lessons whatever the task was about; lessons now reach only tasks like their own.

## Sponsor technology

| Sponsor | Where it does real work |
|---|---|
| **Zetaris** | The only data path: Scout and Ada query the equipment registry, sensor specifications, maintenance history and samples through `run_sql` and the SQL guard (`team/sql_guard.py: check_sql`); maintenance notes pass the injection guard before any model sees them; Warden's "new data" is a Zetaris query. Setup: `scripts/admin/setup_zetaris.py`, `data/zetaris/`. |
| **Meterless** | Nightshift: the primary provider (`MODEL_PROVIDER=nightshift`, the code's default); the eight agents' model calls go to it first, and the workstation's Ollama answers only when it cannot (`clients/meterless.py`). H-MEM: shared memory with a trust order and reviewer lessons (`services/meterless-sidecar/server.ts`, `ledger.py`, `team/memory.py`). World Model: shared entities through the sidecar (`clients/world.py`); see `docs/hackathon/SPONSORS.md` for its current use. Markovian: when its service is up and Sentinel's scan hits two or more files, the review runs as one bounded chunk per file (at most six) with a compressed carryover (`services/meterless-sidecar/markovian/`, `clients/markovian.py`, `team/vulnerability.py`). |
| **NVIDIA Nemotron** | The eight agents' model calls run on Nemotron-Mini-4B-Instruct: on the laptop's GPU through Nightshift's lane `local-runtime/nemotron-mini-4b-instruct-q4-k-m`, or, when Nightshift cannot answer, as `nemotron-mini` in the workstation's Ollama. On Nightshift the lanes ask for larger hosted Nemotron routes unless `LANE_FAST`, `LANE_DEEP` and `LANE_CRITIC` name the laptop's route, as the workstation's `.env` does (`team/lanes.py`, `docs/operations/NIGHTSHIFT_TUNNEL.md`); a lane can be pointed at another local model (`LANE_CRITIC`). Tinker's engineer step runs `qwen2.5-coder:7b` instead (`TINKER_ENGINEER_MODEL`). The served model and the provider of every call are in the trace. |
| **Cursor** | Written with Claude Code; Cursor is installed on the team's laptop. Declared honestly in `docs/hackathon/SPONSORS.md`. |

## Setup

You need Linux (with tmux for the scripts that run all the time), Python 3.14 (requirements.txt pins versions tested on 3.14.4), Node.js with `npm`/`npx`, a checkout of the Meterless repository for `npm run setup`, Docker running Zetaris and the obs-service, and a model server: Ollama with `nemotron-mini` (`docs/operations/LOCAL_MODELS.md`) or, for the primary provider, Meterless Nightshift on a Windows laptop (`docs/operations/NIGHTSHIFT_TUNNEL.md`).

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # Zetaris URL and key, the provider and lanes: Nightshift (NIGHTSHIFT_TUNNEL.md); its commented block runs on Ollama alone (LOCAL_MODELS.md)
(cd services/meterless-sidecar && npm install && METERLESS_REPO=<your Meterless checkout> npm run setup)   # vendors the Meterless reference engines
docker compose -f services/obs-service/docker-compose.yml up -d --build   # the synthetic data service, on Zetaris's docker network (zetaris_default)
PYTHONPATH=core .venv/bin/python scripts/admin/setup_zetaris.py   # REST tables, cache, views (idempotent)
scripts/run_sidecars.sh                    # H-MEM/World Model and Markovian, on the ports SIDECAR_URL and MARKOVIAN_URL name (8100, 8101)
PYTHONPATH=core .venv/bin/streamlit run ui/app.py --server.port 8501 --server.address 127.0.0.1
```

The UI listens on loopback only. To reach it from another machine, use an SSH tunnel (`ssh -L 8501:127.0.0.1:8501 <user>@<server>`, then `http://localhost:8501`), a forward from the workstation's Tailscale address to that port on a tailnet (`docs/operations/ACCESS.md`), or the public link below.

**From a phone.** Open the public link below, or install the Tailscale app on the phone, sign in to the same tailnet, and open port 8501 of the workstation's Tailscale address. On the tailnet, traffic between the phone and the workstation is encrypted and nothing is opened to the internet. The public link is open to the internet, behind the sign-in page.

**Sign-in page.** `.venv/bin/python scripts/admin/set_password.py <user>` asks for a password twice and writes `UI_USER` and a salted hash (`UI_PASSWORD_HASH`) into `.env`; nothing secret is in the repository. Restart the UI and every visitor gets a sign-in page first; a device stays signed in for a week, **Sign out** in the sidebar ends that early, and a wrong password slows the next try. Without `UI_PASSWORD_HASH` there is no sign-in page.

**Public link.** `scripts/public_link.py`, run with `~/.local/bin/inverse-public start|stop|status|url|log` (it needs `cloudflared` in `~/.local/bin`), opens the page to people outside the tailnet: a Cloudflare quick tunnel (`https://<random>.trycloudflare.com`, no account, no uptime promise, a new address after every restart) until the tailnet's owner allows Tailscale Funnel, then the permanent `https://<machine>.<tailnet>.ts.net`. Signed-in people see the current link under **Share with your team** in the sidebar, and your phone gets it when it changes. The sign-in page is its only gate, so set a password before you start it (`docs/operations/ACCESS.md`).

## Usage

- The front page: ask in the chat; in the Live panel, queue a goal for Warden or answer Tinker with `veto auto/...` or `approve auto/...`.
- CLI: `PYTHONPATH=core .venv/bin/python scripts/admin/run_team.py "goal" --collaborate` runs one mission and prints the answer.
- Warden: `PYTHONPATH=core .venv/bin/python scripts/watch.py [--once] [--force] [--queue "goal"] [--status]`.
- Tests: `PYTHONPATH=core .venv/bin/python -m pytest -q tests` (no model and no network needed for the unit tests; the integration tests skip when the services are absent).

## Honest limitations

- The data platform federates one synthetic service (`data/README.md`); no real plant data was used.
- The crew runs a 4B model, Nemotron-Mini: answers are short and sometimes thin even when the evidence is right; the deterministic layer keeps them honest, not eloquent.
- Nightshift has no Linux build, so it runs on a Windows laptop that must be on and awake; while it is not, the crew runs on the workstation's CPU, several times slower.
- One Warden per checkout; "new data" is a row count and a last timestamp.
- Only tool-using agents (Ada, and agents Forge builds) can start a conversation; the others answer when asked and read their inbox.
- Vera reviews on the same Nemotron-Mini model as the agents she checks (all three lanes name the laptop's route), so her independence comes from her fixed rules and checked quotes, not from a second model; `LANE_CRITIC` can name one.
- Each agent's mark out of ten and its open flaws are in `docs/AGENT_REPORT.md`; three are open (Atlas's raw plan routing, Forge's template expert, Ada's weight from a fetched mass).
- Of the agents, only Tinker changes the crew's code, in a sandbox clone. With the default `TINKER_AUTOMERGE=council` it merges and deploys, with no person approving, a change that measurably helps (the agent's probe rose or the item's own test now passes), after the tests, Sentinel's review, Vera's vote and a 30-minute veto window announced on your phone. Any other value (e.g. `human`) leaves every merge to a person. The council never edits code: a code proposal becomes a task card.

## License

Apache-2.0, see `LICENSE`. The Meterless reference engines vendored by `npm run setup` into `services/meterless-sidecar/vendor/` are Apache-2.0 too.
