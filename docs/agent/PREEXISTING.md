# Pre-existing vs hackathon work (from `git log`, 2026-10-23)

The hackathon window opened 22 Oct. The first commit in this repo is **2026-10-23 14:14** (`5d957dd`, M0 spike), so no file in the git history predates 22 Oct. Everything below was built during the hackathon, by the team. The older general declaration is `docs/PREEXISTING.md`.

## Authored in the hackathon (git history, 18 commits at time of writing)
- 5d957dd to a5882ab (agustin): obs-service, Zetaris tables, H-MEM sidecar, core math, validators, agents, orchestrator, UI v1, docs, traces, tests.
- PRs #1 to #4 (Mathias Benitez / mathib2, 21:xx to 22:50): correctness fixes, plain-language UI (`ui/parts.py`, `ui/plain.py`, `.streamlit/config.toml`), reply-length fix, mobile sidebar.
- 88cf15b (Claude Code): thermal RC SINDYc test.
- Docs: `docs/agent/RECON.md` (M0 spike), `docs/agent/RECON_ORCHESTRATOR.md` and this file (orchestrator Phase 0).

## Third-party, not authored here
- Zetaris platform: Docker images run unmodified from `~/zetaris-platform` (the starter repo `~/getting-started` and `zetaris-platform.zip` are organizer-provided, dated 22 Oct, outside this repo).
- Meterless open core (Apache-2.0): H-MEM and World Model reference implementations, copied into `services/meterless-sidecar/vendor/` at setup (gitignored); the Nightshift Runtime runs on the laptop.
- `smoke_test.py` is the organizers' starter script, kept as provided.
- Libraries: SciPy, NumPy, PySINDy, Pint, FastAPI, Streamlit, pandas, openai, requests.
- NVIDIA Nemotron models, served through Nightshift.

## To confirm
`smoke_test.py`, `input_examples/`, `output_examples/`, `agent/`, `prompts/` came with the starter layout (empty dirs); confirm with the team before submission.
