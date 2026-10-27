# Demo script (4 minutes, with an optional 45 seconds)

Everything below is live unless marked **replay** or a deck slide; the front page is the chat page. Press **New chat** in the sidebar
before recording so the examples show. The replay is Warden's saved mission `docs/evidence/missions/20261026-195911` (P-104's
maintenance review); get it ready as described under the table. The submission notes say the video runs 1 to 4 minutes: the main cut
ends at 4:00, and the optional rows go in only if the submission form allows 5 minutes. A mission on Nightshift usually finishes in
under a minute: start it, talk over it, and cut the waiting.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Deck slide 1, the title | "INVERSE is a crew of AI agents that plan, do the work, check each other, talk to each other, and keep going on their own, with every claim tied to evidence." |
| 0:15 | Deck slide 2, the problem | "One model, one prompt, one answer: no plan, no review, no memory, no evidence. And it stops when you stop typing." |
| 0:30 | The chat page: the badges **AI online**, **Data platform online**, **Memory online**; on the right, the **Crew** pill with the eight cards | "Eight agents. Their model is NVIDIA Nemotron-Mini-4B on a laptop GPU through Meterless Nightshift, with the workstation's own model as the fallback. Atlas plans, Vera reviews, Warden keeps watch; Scout, Euler, Ada, Sentinel and Forge do the work." |
| 0:55 | Click the example **What do we know about P-104?**; the panel on the right switches to **Live** | "One box. Atlas plans the mission. Watch the plain sentences: who starts what, which tool they used, what Vera sends back and why." |
| 1:20 | **Recent** in the sidebar: click **P-104 is up for a maintenance review. From the…** (**replay**); its answer opens in the thread; then **Steps** and **Evidence** under it | "A mission Warden ran from its queue on Nightshift: 16 seconds, 13 model calls. Each agent announces its result to everyone: Scout the mass and the two maintenance records, Euler the days between them, Ada the weight. One record's note was planted as an instruction to the AI; the injection guard withheld it before any model saw it. The 33 days were counted by code. Vera accepted all four tasks, three of them by code, because the tool results hold every number. Evidence shows the query or the calculation behind each one." |
| 2:05 | **Council** (the pills on the right): the open proposals, **Hold a session now**, the session's decisions, then **Decided lately** with each change's effect | "The agents propose changes to their own crew while they work, in a tiny wire protocol. The council decides in a short session of at most four model calls: Vera votes, the agent concerned votes, a fixed rule decides. An adopted change is applied by code and can be undone." |
| 2:40 | **Warden** (the pills on the right): **Warden is awake**, the standing missions, the table of missions it started | "Nobody asked for these. Warden runs queued goals, standing missions on a schedule, and a mission for every machine whose sensor data changed. A ninth member, Tinker, improves the crew's own code around the clock, and merges a change only after the tests, a review, a vote and a veto window announced on our phones." |
| 3:05 | **Advanced** (the view switch in the sidebar): **Replay a saved run (no model needed)**, the same mission (**replay**), **Replay**, down to **5 · Trace** | "Every model call, tool call and review is in the trace with the model that served it, and the trace names the provider: Nightshift or the fallback. Every mission replays from its files." |
| 3:25 | Deck slide 9, measured | "Eight checkable goals: all eight in 222 seconds on the workstation's CPU, in 40 on Nightshift, and in 32 after we fixed a flaw our own benchmark caught." |
| 3:45 | **Chat** in the sidebar: the live mission from 0:55 has finished in the thread; then deck slide 11 | "Autonomous, checked, replayable. Zetaris is the only data path, Meterless serves the model and holds the memory, and NVIDIA Nemotron-Mini-4B answers every model call the eight agents make." |
| 4:00 | | End of the main cut. |
| +0:00 | Optional: **New chat**, the example **Check our own code**, then **Evidence** | "Sentinel reviews our own code. A fixed-rule scan finds the hot spots, every finding must quote a real file and line, and a finding the code contradicts is dropped. This file is clean, so no weakness is claimed." |
| +0:25 | Optional: deck slide 10, sponsors | "Where each sponsor does real work: Zetaris for data; Meterless for the model, the shared memory, the long reviews and the council's record; and Nemotron for every agent." |

Before recording:

- The recording runs on Nightshift, the primary provider; say so. The badge above the chat reads **AI online**, not **AI online · fallback**, and under **Connections** in the sidebar, **AI** · Nightshift shows **Online**. If it shows the fallback, the workstation's CPU is answering and a mission usually takes two to four minutes: wake the laptop, start its scheduled task **Nightshift tunnel**, then press **Check again** under **Connections**.
- The replay: **Recent** lists only the eight newest saved runs and **Warden** the twelve newest it started, so newer missions can push it off both lists. If the live checkout's `runs/` folder has no `20261026-195911`, copy it there from `docs/evidence/missions/`. Click it once before recording to see it open in the thread. **Warden** → **2026-10-26 19:59 · queued by a person** → **Show it** opens it the same way.
- If the council has nothing open, file a note under **Council** → **Propose a change yourself** (What kind of change: a note for the crew's shared memory; **The note**; **Why (one sentence)**; **File it**) so the session has something to decide.

Fallbacks: the live mission is never waited for; the replay at 1:20 carries the demo. If Warden is not running, its panel says so and the table still shows what it did.
