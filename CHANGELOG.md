# Changelog

> Entries before 2026-10-24 describe features that were removed when the entry was refocused on the crew (the physics subsystem, the
> Physics bench page, the evaluation report); they live in the git history before commit `db408c1`.

## Agreement and routing by code, Tinker edits in place, a compact crew page (2026-10-25, night)
- Atlas: a one-task plan carries the goal verbatim (a paraphrase by a 4B planner can only drop a detail or be the schema's example text); placeholder tasks ("write the instruction for the task") are refused and the planner re-asked; plain arithmetic with nothing to look up goes to Euler; a lookup that feeds a computation is rewritten so Scout looks up only. Scout: numbers the rows do not contain are replaced by the row values (`scout_numbers_dropped`), so Scout and Vera agree by construction. Benchmark round 11 exposed both failures; rounds 11 and 12 are in `docs/BENCH.md`.
- Tinker's engineering step works on one named file and region with `edit_file` only, and "no safe change" is an accepted answer recorded as a lesson. With `TINKER_AUTOMERGE=council` (the default) a change that passed the tests and the probe is merged on Sentinel's review and Vera's vote after a veto window (`veto auto/…` or `approve auto/…` in the Live box); `human` leaves every branch for a person.
- The crew page: one header line with the status row beside it, the examples, the goal and Go, the mission or the answer, then four sections (The crew, On its own, Council, Past missions) behind a switch; shorter captions on the Warden panel and the council.
- Textbelt's free SMS is disabled for US numbers; carrier SMS by email (T-Mobile:`number@tmomail.net`) needs SMTP credentials in `.env`.

## The crew works on itself, a Live chat, and your phone (2026-10-25)
- **Tinker** (`scripts/tinker.py`, `scripts/inverse-tinker`): an improvement loop that runs round the clock in a sandbox clone: picks the next item of the crew's improvement list or a failing probe, researches it on the web (`web_search`, `fetch_url`, through the injection guard), makes the smallest change (`edit_file`, `write_file`, sandbox only), runs the tests and the agent's probe by code, and when nothing got worse pushes a branch `auto/...`, files a council task card and alerts a person. It never touches the live checkout and cannot merge.
- One chat log for everything the crew says (`core/inverse_core/chat.py`, `state/chat.jsonl`): the message bus, Warden's log, the council and Tinker write to it; the **Live** mode of the page shows it as a chat, refreshed every three seconds, with a box that queues a goal.
- `core/inverse_core/notify.py`: alerts on the phone over free channels named in `.env` (ntfy push with a call-like priority, Telegram, a carrier's email-to-SMS gateway); `scripts/notify.py` to test one. The crew page writes `state/ui_mission.json` while a mission runs so Tinker waits.

## A benchmark, faster missions, fewer failed tasks, and the agents measured (2026-10-25)
- `scripts/bench.py` + `bench/cases.yaml`: eight checkable goals, pass/clean/seconds/calls/tokens per case, results under `docs/evidence/bench/`; `scripts/probe.py`: each agent alone on its own questions, marked 0-10; `scripts/warmup.py` warms the model server's prefix cache. Write-ups: `docs/BENCH.md`, `docs/AGENT_REPORT.md`.
- Speed: reply caps per call, the composer skipped for one or two short results (cited by code), Scout answering in one conversation, smaller tool results and a lazy fold, plan review only for three or more tasks, `prompt_too_long` traced. Rounds 7 and 8: 7 of 8 goals in about 370 s against 4 of 8 in 588 s at the start.
- Effectiveness, by code where code can decide: a value-annotated SQL schema with examples; a rejected query is evidence with the platform's message; a column the task asks for is added to the query; row values the answer leaves out ride along, cited; a routing guard on every model plan (`plan_guard`); the reviewer judges quotes against evidence values, sends back "not available" with the rows, a number from nowhere, and an asked value left out, and retries a model's reject once; a calc that names a quantity is resolved from the context; a clean scan is answered by code; a summary starts from the shared memory; a repeated tool call ends the loop by code; chunked reviews in JSON.

## Sign-in page (2026-10-25)
- `ui/auth.py`: with `UI_PASSWORD_HASH` in `.env` (written by `scripts/set_password.py`, a salted PBKDF2 hash, never the password), the UI shows a sign-in page first; a signed cookie keeps a device signed in for a week; **Sign out** in the sidebar revokes it; a wrong password slows the next try. Phone access through the tailnet is documented in the README.

## README first screen (2026-10-25)
- The tests badge, a ten-line diagram of a mission and a "Read next" links block at the top of the README; a marked place for the two screenshots.

## Vera's verdict in a checkable shape (2026-10-25)
- The Critic's model reply is `{"verdict", "problems": [{"quote", "why"}], "reason"}`: every objection quotes the words of the answer it is about. Code keeps an objection only when the quote is really in the answer and the evidence does not cover it (a number missing from the evidence, or, for a quote without numbers, most of its content words absent from the evidence). A revise or reject with no objection that checks out does not send work back: the result is accepted with the objection on record under "not checked" (`by: code` in the trace).
- A verdict that cannot be read (no JSON, or a word that is not accept, revise or reject) is asked for once more; unreadable twice, the result is kept and marked unreviewed, never silently accepted and never sent back for the reviewer's failure. `norm_verdict` reads approve, ok, pass, fail and the one-letter council forms.
- Plain lines for the new outcomes; `tests/test_critic.py` covers the checks, the re-ask, and the acceptance check of the plan: a correct arithmetic answer is no longer rejected on a made-up reason.

## Live view, Warden panel, council form (2026-10-25)
- The running mission lives in the process, not in one browser session: a click, a rerun or a page reload re-attaches to it; the status line names who is on which task, how many finished and the time elapsed; a **Stop** button (`ctx.stop`) lets the step in progress finish, starts nothing new, and the answer lists what did not finish, verbatim. Model replies, memory writes, Markovian chunks, proposals and council steps read as plain lines, live and in "How it went".
- Warden's panel refreshes itself every 10 seconds and shows the mission running now (`state/current.json`), the queue, and a button to show a mission Warden ran.
- The council section speaks in the agents' names, has a one-line empty state, a form built from choices (no JSON), the wire's own reason when a proposal is refused, and an undo that reports errors.

## Review fixes (2026-10-25)
- From the pre-submission review: votes read in a small model's own words; a second backer for self-serving or rule-filed changes; prompt addenda, granted tools, new missions and unevidenced notes become task cards or are rejected; the book replays incrementally and survives bad lines; the guard scrubs every column; Spark built-ins forbidden in SQL; plan review cannot copy the example; Critic verdicts normalised; a tool loop that overruns its budget fails honestly; client defaults and MODEL_TIMEOUT; Warden re-reads missions, retries a failed new-data mission once and plans fixed-text missions by rule; the datasets generator stands alone; evidence committed under docs/evidence/.

## The council (2026-10-24)
- CW/1 (`team/wire.py`): one small JSON object per message with short keys and hard caps; verbs P, S, V, D, X; kinds cfg, mission, note, agent, code with a per-kind patch whitelist; content-addressed ids merge the same idea into one proposal with backers.
- `team/council.py`: filing is free (a `propose` list in an agent's reply, the `propose`/`support` tools, two rules in the Lead, people); sessions happen only by rule, at most once an hour, bounded to four model calls; Vera votes on the whole agenda in one call, the agent a change concerns votes on its own items; a fixed rule decides; effects are applied by code with undo (experts.local, missions.local.yaml, shared memory, kept agents, task cards for people). Book, trace events, bus messages and World Model entities for every step. Warden holds a session when one is due.
- UI: a council section on the crew page (open proposals, decisions, a session on demand, a form, undo); `scripts/council.py` from a shell.

## The experts are the product (2026-10-24)
- The physics subsystem (orchestrator, analysis, validators, inference, the physics expert, the Physics bench page, its scripts, evidence and tests) is removed: the hackathon entry is the crew of local, autonomous agents. The data generator for the obs-service stays.
- Warden reacts to new sensor data by starting a crew mission about that machine (fixed goal text), not a physics check; the `data check` standing mission replaces `machine health`.
- `team/verify.py` keeps the one deterministic check the crew still needs (numbers in an answer must appear in its evidence).
- UI: `app.py` is the Crew page by default with Advanced beside it; `plain.py` and `parts.py` keep only crew wording.

## The crew (2026-10-24)
- The agents have names by expertise (Atlas, Vera, Warden, Newton, Scout, Euler, Ada, Sentinel, Forge; `core/inverse_core/team/crew.py`, `callsign` in `experts/*.yaml`); identifiers in configs, plans, traces and messages are unchanged. `docs/CREW.md`.
- A new front page, **Crew**, is the default: one goal box, the agents at work in plain sentences, the answer, who did what, what they said to each other, Warden's panel (standing missions, a queue, what ran on its own) and past missions to replay. The old pages remain as **Physics bench** and **Advanced**.
- Standing missions (`missions.yaml`): Warden runs them on their schedule, so the crew works without anyone asking (machine health, code review, memory digest).
- `MODEL_PROVIDER` defaults to `ollama`: fully local; `nightshift` remains the sponsor path.

## Small gaps closed (2026-10-24)
- The Proposer and the Critic ask the runtime for one JSON object (`response_format: json_object`), as the team side already did; the committed traces show the parse errors this removes. `docs/SPONSORS.md` now says what those traces show about Nemotron proposals instead of a claim that could not be true by construction. `MarkovianClient` defaults to the Markovian port (8101). The H-MEM sidecar answers 400 to a malformed body instead of dying (integration test). The unknown-mass limit is in the README and the UI explains it in plain words.

## Runs on its own, and the experts talk (2026-10-24)
- Watch mode (`scripts/watch.py`, `core/inverse_core/watch.py`): a loop on the workstation checks Zetaris for new sensor data per machine, runs the physics check, decides by rule whether the team is needed (wear flag, rejection, refusal) and runs it with a goal written from the verdict; a manifest per run, a heartbeat, a log, a goal queue people and the UI can write to, recovery of interrupted runs, and a sidecar check. `~/.local/bin/inverse-watch` keeps it running in tmux on the workstation.
- A message bus (`team/bus.py`): accepted results, the Critic's notes, questions and answers go on `runs/<ts>/messages.jsonl` and the trace; each expert sees the messages addressed to it with its next task. New tools `ask_expert` (consult another expert, one level deep, small budget), `post_message` and `read_messages`; the Solver holds them. The UI shows the conversation of every run and a watch-mode panel.

## Faster runs (2026-10-24)
- The Lead runs a plan level by level and executes independent tasks concurrently (default two at a time; `--parallel`); Trace and Budget are thread-safe; a per-run SQL cache shared by the Research expert and the tool layer; plain progress lines for both.

## Review fixes (2026-10-24)
- An adversarial review of the overnight changes confirmed eight defects; all fixed with regression tests: non-string or null model fields no longer crash a run (answer, reason, evidence detail), one unreadable plan sample no longer ends a vote, memory errors are traced instead of fatal, experts proposed by losing plan samples are dropped, the physics verdict is remembered only after review, the SQL guard checks aliased comma lists and refuses subqueries, file tools never read dot-folders or skipped folders, prompt files must live inside the repository, a Markovian chain is abandoned cleanly on any failure and unreviewed files are listed, stray final markers cannot end a chain early, the architect's test-drive budget is reported instead of failing the architect, the closed-form solver takes y0 at the first sample, the UI survives an offline Zetaris or a broken experts.local file and keeps the architect's tools when saved, the evaluation uses distinct noise realisations per scenario and varies record shapes for the refusal check.

## Submission documents (2026-10-24)
- `docs/SPONSORS.md` (sponsor technology explanation), `docs/SUBMISSION.md` (project details and the checklist), `docs/ONBOARDING.md` (adding a machine; what a plant would need); the eval report gains a ten-times-noisier scenario.

## Demo material (2026-10-24)
- `docs/DEMO_SCRIPT.md` rewritten to the real UI labels and measured timings, with a replayed team segment and fallbacks; `docs/agent/NIGHTSHIFT_TUNNEL.md` (self-reconnecting tunnel for the laptop that hosts Nightshift); honest progress label on the single-machine page.

## Research-backed algorithms (2026-10-24)
- Closed-form solution of the linear unforced oscillator in `simulate` (exact, much faster); split conformal prediction band on the unseen tail of every accepted fit (`inference/conformal.py`, reported in the verdict and the UI); Reflexion lessons per expert in H-MEM (`team/memory.py`, injected by the Lead); self-consistency plan voting (`--votes N`). References and locations in `docs/agent/ALGORITHMS.md`.

## Architect expert (2026-10-24)
- `kind: architect`: designs, creates (`create_expert`), test-drives (`test_expert`) and refines new custom experts during a run; plans may assign a task to an expert the architect will create; the Lead verifies it exists when the task's turn comes. Only an architect may hold the architect tools.

## Markovian for long reviews (2026-10-24)
- Meterless Markovian (vendored reference) driven step by step over HTTP from a stand-alone service; the vulnerability expert reviews two or more files as one bounded chunk per file with a compressed carryover; measured versus estimated tokens in the trace; engine evidence and conformance.

## Customizable experts (2026-10-24)
- New expert kinds `custom` (a tool loop defined only by config) and `vulnerability` (defensive, this repository only, findings verified against the files); built-in `solver` and `vulnerability` experts; tool layer `core/inverse_core/team/tools.py`.
- `experts.local/` overrides (gitignored); UI panel to add, edit, disable or remove experts; the lead can create an expert for a run (**Keep it** saves it); experts can review the plan before it runs (`--collaborate` / UI toggle).
- Plain-language progress lines for team runs (`ui/plain.py: team_step`). Docs: `docs/agent/EXPERTS.md`.
- Edits to existing files: `team/{lead,critic,registry,llmcall,build,experts}.py`, `ui/team.py`, `ui/plain.py`, `scripts/run_team.py`, `README.md`, `.gitignore`, tests.

## Team orchestrator (2026-10-23)
- New `core/inverse_core/team/` (Lead, Plan, Critic, TeamMemory, config-driven experts), `experts/*.yaml`, `scripts/run_team.py`, UI mode `ui/team.py`.
- Edits to existing files: `ui/app.py` (mode switch; forget also clears team memory), `requirements.txt` (+pyyaml), `.env.example`, `README.md`.
- Scout Intent not yet integrated.
