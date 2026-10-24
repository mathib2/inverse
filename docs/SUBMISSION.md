# Submission details (Open Agent Hackathon 2026)

Deadline: **Tue 27 Oct 2026, 23:45 UTC** (6:45 PM Central). Track: **03, Reasoning Architecture**.

## Project

**Name:** INVERSE

**One line:** Turn sensor logs into a verified physics model, or an honest refusal; then let a team of configurable experts plan, check each other, and answer with evidence.

**Description (short):** After a repair, a reliability engineer runs a release test and asks what governs the machine and whether it has worn. INVERSE recovers the physical parameters from Zetaris-federated sensor data and answers ACCEPT (with 95% intervals, the physics tests passed, a conformal check on unseen data and a wear flag against the remembered baseline), REJECT (every candidate failed a named test), or UNIDENTIFIABLE (it refuses before fitting and names the measurement that would resolve it). NVIDIA Nemotron, through Meterless Nightshift, proposes explanations; solvers and validators decide; Meterless H-MEM remembers what physics ruled out. On top of that, a team of experts defined by config (physics, research, reasoning, a solver, a defensive code reviewer, and an architect that creates new experts when a task needs one) is planned by a lead, reviews its own plan, is checked by a Critic on a separate Nemotron lane that sends weak work back, shares H-MEM memory, runs long reviews through Meterless Markovian in bounded chunks, and cites every claim.

**Measured, not claimed** (`docs/evidence/EVAL.md`): wear flagged 20/20 when planted, false alarms 0/20, wrong trap model accepted 0/80 (vetoed every time it fit better), refusal 20/20, interval coverage 93% (c) and 100% (k).

**Team:** _fill in names and the registered HackOS team._

## Links

- Repository: https://github.com/mathib2/inverse (make public before submitting; scrub done, LICENSE added)
- Demo video: _to record, `docs/DEMO_SCRIPT.md`_
- Slide deck: _to build from `docs/SLIDES.md`_
- Sponsor technology explanation: `docs/SPONSORS.md`
- Pre-existing work: `docs/agent/PREEXISTING.md`

## Checklist before pressing submit

1. HackOS team registration confirmed (or late entry granted). **Blocking.**
2. Cursor requirement: cite the waiver announcement in `docs/SPONSORS.md`, or leave the honest statement as is.
3. Meterless asked whether a laptop-hosted Nightshift behind a tunnel counts as "running on the participant's machine".
4. Repository public; `git log -p | grep -c <tailnet-ip>` is zero in the tree (history still contains the address: squash or accept).
5. Fresh traces in `docs/evidence/traces/` and `docs/evidence/EVAL_LIVE.md` regenerated with Nightshift online, H-MEM reset before. Set `MODEL_PROVIDER=nightshift` in `.env` for the recording and the evaluation (the lab runs `ollama`), and switch back afterwards.
6. One saved team run on the workstation for the replay segment.
7. Video recorded (1 to 4 minutes) and the deck exported to PDF.
8. `README.md` test count and the three scenario numbers match the live app.
9. Watch mode running on the workstation for the demo (`~/.local/bin/inverse-watch status`), with one autonomous team run saved for the replay segment, its conversation visible.
