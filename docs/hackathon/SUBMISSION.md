# Submission details (Open Agent Hackathon 2026)

Deadline: **Tue 27 Oct 2026, 23:45 UTC** (6:45 PM Central). Track: **03, Reasoning Architecture**.

## Project

**Name:** INVERSE

**One line:** A crew of local AI agents that plan, do the work, check each other, talk to each other, and keep going on their own, with every claim tied to evidence.

**Description (short):** Eight agents run on one workstation. Their model calls go to Meterless Nightshift (NVIDIA Nemotron-Mini-4B on a laptop GPU); when Nightshift cannot answer, the workstation's own Ollama answers with the same model for the next two minutes, and then Nightshift is tried again. Atlas plans a mission in at most five tasks by expertise; Scout queries the Zetaris data platform read-only and cites every query; Euler derives with every number recomputed; Ada solves multi-step problems with tools and asks the others when a step needs them; Sentinel reviews the crew's own code with every finding checked against the file and line; Forge builds a new agent when the crew lacks one; Vera checks every result with fixed rules and code first, asks her model only when they cannot decide, and sends weak work back; Warden runs queued goals, standing missions and new-data missions without anyone at the keyboard. Shared memory with a trust order lives in Meterless H-MEM; long reviews run through Meterless Markovian; the agents talk over a message bus; a council lets them propose changes to their own crew in a tiny wire protocol and decides them in short, bounded sessions with reversible effects recorded in the Meterless World Model; every mission is replayable from its files. Tinker, a ninth member, works on the crew's own code around the clock in a sandbox, and a change reaches the live crew only after the tests, the agent's probe, Sentinel's review, Vera's vote and a veto window on the owner's phone. On a benchmark of eight checkable goals the crew scores 8/8 in 30 s on Nightshift under an exact grader (rounds 26 and 27) and 8/8 in 222 s on the workstation's CPU (round 17), `docs/BENCH.md`.

**Team (five):** Mathias Benitez, Agustin Benitez, Stephen Zook, Angel Gonzalez, Santiago Carbajal. Check that all five are on the registered HackOS team before submitting.

## Links

- Repository: https://github.com/mathib2/inverse (published by `scripts/admin/publish_public.sh`; make it public before submitting)
- Demo video: _to record, `docs/hackathon/DEMO_SCRIPT.md` (3:45)_
- Slide deck: the 12-slide deck built from `docs/hackathon/SLIDES.md`, exported to PDF
- Sponsor technology explanation: `docs/hackathon/SPONSORS.md`
- Pre-existing work: `docs/hackathon/PREEXISTING.md`

## Checklist before pressing submit

1. HackOS team registration confirmed (or late entry granted). **Blocking.**
2. Cursor: optional under the official rules (05); `docs/hackathon/SPONSORS.md` says it was not used. Paste its sections into the form's sponsor question, including "What was unique".
3. Repository public. The public repository, https://github.com/mathib2/inverse, is a rewritten copy of the private one. The private repository cannot be made public, because all its branches and GitHub's copies of every merged pull request carry the original history. `scripts/admin/publish_public.sh` rewrites the history with `git filter-repo`, with rules kept outside the repository, and refuses to push if anything the rules name is left; `DRY_RUN=1` runs the rewrite and the check without pushing. Rotate the deploy key afterwards.
4. Warden running on the workstation for the demo (`~/.local/bin/inverse-watch status`). The replay segment is Warden's saved maintenance review of P-104, `docs/evidence/missions/20261026-195911` (on Nightshift, 16 s, 13 model calls). Its conversation: Scout, Euler and Ada announce their results to everyone; no agent consults another in this run. Before recording, check that it opens in the app (Recent in the sidebar, or Show it in the Warden panel) with its conversation visible.
5. The recording runs on Nightshift, the primary provider: before recording, the AI badge says "AI online", not "AI online · fallback", and Connections in the sidebar shows Nightshift "Online", not "Online on the fallback" (the laptop awake, the "Nightshift tunnel" task running).
6. Video recorded (1 to 4 minutes) and the deck exported to PDF.
7. `README.md` matches the live app (names, pages, missions). The pre-submission review's items 1 to 10 are done or consciously dropped.
