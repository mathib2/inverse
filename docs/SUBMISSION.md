# Submission details (Open Agent Hackathon 2026)

Deadline: **Tue 27 Oct 2026, 23:45 UTC** (6:45 PM Central). Track: **03, Reasoning Architecture**.

## Project

**Name:** INVERSE

**One line:** A crew of local AI agents that plan, do the work, check each other, talk to each other, and keep going on their own, with every claim tied to evidence.

**Description (short):** Eight agents run on one workstation on local models (NVIDIA Nemotron through Ollama, or through Meterless Nightshift). Atlas plans a mission in at most five tasks by expertise; Scout queries the Zetaris data platform read-only and cites every query; Euler derives with every number recomputed; Ada solves multi-step problems with tools and asks the others when a step needs them; Sentinel reviews the crew's own code with every finding checked against the file and line; Forge builds a new agent when the crew lacks one; Vera reviews every result on her own lane and sends weak work back; Warden runs queued goals, standing missions and new-data missions without anyone at the keyboard. Shared memory with a trust order lives in Meterless H-MEM; long reviews run through Meterless Markovian; the agents talk over a message bus; a council lets them propose changes to their own crew in a tiny wire protocol and decides them in short, bounded sessions with reversible effects recorded in the Meterless World Model; every mission is replayable from its files.

**Team:** _fill in names and the registered HackOS team._

## Links

- Repository: https://github.com/mathib2/inverse (make public before submitting)
- Demo video: _to record, `docs/DEMO_SCRIPT.md`_
- Slide deck: _to build from `docs/SLIDES.md`_
- Sponsor technology explanation: `docs/SPONSORS.md`
- Pre-existing work: `docs/agent/PREEXISTING.md`

## Checklist before pressing submit

1. HackOS team registration confirmed (or late entry granted). **Blocking.**
2. Cursor requirement: cite the waiver announcement in `docs/SPONSORS.md`, or leave the honest statement as is.
3. Repository public, published from a squashed branch (or after `git filter-repo`): the tailnet address lives in an early commit and `git log -p --all | grep -c <tailnet-ip>` must be 0 on the public repository; rotate the deploy key afterwards.
4. Warden running on the workstation for the demo (`~/.local/bin/inverse-watch status`), with one autonomous mission saved for the replay segment, its conversation visible.
5. The recording runs fully local (`ollama`, the default); the video says so and shows the Nightshift path as one line of `.env`.
6. Video recorded (1 to 4 minutes) and the deck exported to PDF.
7. `README.md` matches the live app (names, pages, missions). `docs/IMPROVEMENT_PLAN.md` items 1 to 10 are done or consciously dropped.
