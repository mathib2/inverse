# Demo script (target 3:30; three recorded segments, cut together)

The labels below are the ones on screen today. Timings are measured: a single-machine run takes 1.5 to 2.5 minutes with the deep Nemotron lane, a team run 5 to 8 minutes, so the video shows one live single-machine run and **replays** a saved team run (replay is instant and needs no model). Record each segment separately; speed up waits in the edit.

**Before recording (once):** Nightshift open on its laptop with the NVIDIA key, the reverse tunnel open; in the sidebar every connection shows **Online**; **Forget past results…** for P-104 and T-200; the Markovian service up (`npm run markovian`); one saved team run already on disk (run the team example once beforehand, so **Replay a saved run** has it). Keep the browser at 125% zoom; the sidebar open.

## Segment A: the single machine, live (about 1:45)

| Time | Screen | Say |
|---|---|---|
| 0:00 | Landing page, **Mode: Single machine** | "After a repair, a reliability engineer runs a release test and asks: what governs this machine now, and has it worn? INVERSE answers with a verified physics model, or an honest refusal. It never acts on an LLM's guess." |
| 0:12 | Sidebar **Connections** | "Three sponsors do the work: sensor data comes through Zetaris, the AI is NVIDIA Nemotron through Meterless Nightshift, memory is Meterless H-MEM." |
| 0:20 | **1 · Choose a question**, card **Rig T-200: the trap**, **Use this example**, **Run analysis** | "Rig T-200 was reassembled. Watch the progress lines: Nemotron proposes explanations, SINDy proposes a more flexible one, physics checks decide." |
| 0:35 | Progress lines while it runs (cut the wait) | Read two lines aloud as they appear: *Ruled out: … Failed: Settles down, Loses energy* and *Passed every physics check: Simple spring-and-damper*. |
| 1:00 | **2 · Result**, the banner and the highlighted card *Physics caught a better-looking wrong answer* | "The flexible model fit the data better. It also had negative damping, which is a machine that shakes harder on its own. Two validators vetoed it. No AI judged that." |
| 1:15 | Tab **Physics checks** | "Six checks, plain calculations. The new one, *Predicts unseen data within its band*: fitted on the first half, band set on data the fit never saw, and it reports how much of the unseen tail fell inside. Measured, not promised." |
| 1:30 | Tab **Memory** | "The veto is in Meterless H-MEM with source *validator*. An LLM claim cannot overwrite it." |
| 1:38 | **Run analysis** again, then **This session's runs** | "Same question again: the ruled-out model is remembered and skipped, fewer fits, fewer AI calls." |

## Segment B: the refusal, live (about 0:35)

| Time | Screen | Say |
|---|---|---|
| 0:00 | Card **Pump P-104, weight unknown**, **Run analysis** | "Now the mass is unknown. From free decay only ratios are determined." |
| 0:10 | Result banner *Not enough information*, card **What to measure next** | "It refuses before fitting, and names the measurement that would resolve it: a forced response with a known force. Twenty out of twenty planted cases refuse; the forced version of the same data is identifiable twenty of twenty. That is in the evidence folder." |
| 0:25 | Tab **Behind the scenes**, the blocked maintenance note | "A maintenance note told the system to mark everything accepted. It was withheld before it reached any model." |

## Segment C: the team of experts, replayed (about 1:10)

| Time | Screen | Say |
|---|---|---|
| 0:00 | Sidebar **Mode: Team of experts**; panel **Experts · customize the team** open for two seconds | "The same rule at team level. Experts are config, not code: physics, research, reasoning, a solver, a defensive code reviewer, and an architect that creates new experts when a task needs one." |
| 0:12 | **1 · Goal and plan**, the example buttons, then **Replay a saved run (no model needed)** → **Replay** | "A lead plans, the experts review the plan, a Critic on a separate Nemotron lane checks every result. This run is replayed from its saved trace, so you see exactly what happened." |
| 0:25 | The plan table (status column) | "Research looked up the registry, physics fitted the vibration, reasoning did the derivation, each with evidence." |
| 0:35 | **3 · What each expert did**, expand the task with 2 attempts | "Here the Critic sent work back: the first answer claimed more than its evidence showed. The retry built on the verified part and passed." |
| 0:50 | **4 · Trace** | "Every call shows the lane and the Nemotron model that served it; the engine events show H-MEM memory writes after review and, for long code reviews, Meterless Markovian running the review in bounded chunks." |
| 1:00 | **2 · Answer** | "The answer cites every claim as task-and-evidence. What was not checked is listed. An unfinished task is reported word for word by code, never paraphrased." |
| 1:08 | End card | "INVERSE. The LLM proposes. Physics decides. The team checks itself." |

## Fallbacks

- If Nightshift is offline on the day: Segments A and B from the saved traces in `docs/evidence/traces/` (narrate over the JSON), Segment C exactly as above (replay needs no model).
- If a live run takes longer than two minutes, keep recording and cut the wait; the progress lines are the content.
- Numbers to quote come from `docs/evidence/EVAL.md` and `docs/evidence/EVAL_LIVE.md`, never from memory.
