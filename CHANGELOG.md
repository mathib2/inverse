# Changelog

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
