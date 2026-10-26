# How good is this for the hackathon? A candid rating

Open Agent Hackathon 2026, Track 03 (Reasoning Architecture), deadline Tuesday 27 October 2026, 23:45 UTC. Registered, not yet
submitted. Rated on 25 October against what a judge sees in the first ten minutes, with the evidence for each mark.

| criterion | mark | why |
|---|---|---|
| Innovation | 8 | Agents that propose changes to their own crew in a tiny wire protocol, decided by rule in bounded sessions with undo, is a real idea and it runs. The checkable reviewer (quotes judged by code) and the plan guard are the kind of reasoning-architecture choices the track asks for. |
| Technical | 8 | Fully local, no cloud, every number in an answer checked against a tool result, replayable missions, 135 tests, a benchmark and per-agent probes with written-up rounds. The 4B model's own judgement is the weak link, and the write-ups say so instead of hiding it. |
| Product and UX | 7 | One page, one box, plain sentences with the agents' names, a live view that survives a reload, a Stop button, a sign-in page, phone access. No screenshots in the README yet; the council section still needs a judge to read a caption. |
| Demo | 5 | No video and no deck exist yet. The demo script is replay-first and the saved missions are good, so the material is ready; the recording is not. This mark decides the result more than any other. |
| Impact | 7 | The pitch is sharp: a small team with data it cannot send to a cloud and no API budget gets a crew that checks its data, reviews its code and keeps a memory. The impact statement sits in the README; the submission form still needs it in its own words. |
| Sponsor use | 7 | Zetaris is the only data path and every query goes through it; Meterless H-MEM, World Model and Markovian do visible work; Nemotron is the default model everywhere. Cursor is declared honestly as "installed, not used". |

**Overall: 7 of 10 today; 8.5 is reachable by the deadline** with no new code: a three-minute video, the deck exported from
`docs/SLIDES.md`, two screenshots in the README, the git history scrubbed before the repository goes public, and the submission
form filled from `docs/SUBMISSION.md`. Those five items are worth more than any further change to the agents.

## What a judge will hold against it, and the honest answer

- "It is a 4B model, how smart can it be?" The answer is the agent report: the marks are measured, the flaws are named, and the
  architecture is what turns a 4B model into something that answers 7 of 8 checkable goals in 46 seconds each. That is the track.
- "The reviewer is the same model as the worker." True on the local path; lanes exist (`LANE_CRITIC`) and the second model is
  loaded. Say it in the video.
- "Synthetic data." Two machines, three sensors, three maintenance notes, generated with fixed seeds, documented as such. The
  injection-guard test on a planted note is a plus, not a minus.
- "Where is the video?" Record it first, before anything else on the list.

## The marks that can still move before Tuesday

| move | from | to | cost |
|---|---|---|---|
| record the video, replay-first, with the council beat | Demo 5 | 8 | an afternoon |
| export the deck and add the two screenshots | Demo, Product | +1 each | an hour |
| scrub the history and make the repository public | Technical | +0.5 | an hour |
| run the warm-up and a saved mission before the demo | Demo | no slide shows a 60-second wait | five minutes |
