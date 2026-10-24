# Changelog

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
