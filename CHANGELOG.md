# Changelog

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
