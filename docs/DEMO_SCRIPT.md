# Demo script (3 minutes)

Everything below is the live crew page unless marked **replay**. Keep a saved mission with a good conversation ready under
**Past missions** in case the live model is slow.

| Time | On screen | Say |
|---|---|---|
| 0:00 | The crew page, the eight cards | "INVERSE is a crew of eight AI agents on one computer, on local models, no cloud. Atlas plans, Vera reviews, Warden keeps watch; Scout, Euler, Ada, Sentinel and Forge do the work." |
| 0:20 | Type a goal, press **Go** ("What do we know about P-104?") | "One box. Atlas plans the mission. Watch the plain sentences: who starts what, which tool they used, what Vera sends back and why." (On the 4B model a mission takes three to four minutes: talk over the first lines, then cut away.) |
| 0:40 | **Past missions**, **Show** the saved mission with a conversation (**replay**) | "Here is one that finished earlier. Every claim cites its evidence. What did not finish is listed by code, never paraphrased. And this is the conversation: results announced to everyone, Vera's notes, Ada asking Euler a question." |
| 1:20 | **The council**: the open proposals, **Hold a session now**, the decision and the applied change | "The agents propose changes to their own crew while they work, in a tiny wire protocol. The council decides in a short session: Vera votes, the agent concerned votes, a fixed rule decides, and the change is applied by code and can be undone. This note went into shared memory; this budget change is in Scout's config." |
| 1:50 | **On its own**: Warden awake, standing missions, the table of missions it started | "Nobody asked for these. Warden runs queued goals, standing missions on a schedule, and a mission for every machine whose sensor data changed. Each run has a manifest." |
| 2:15 | **Advanced**: the experts editor, Forge's created agent, the trace | "Agents are configuration. Forge can build one during a mission. Every model call, tool call and review is in the trace with the served model." |
| 2:35 | Back to the crew page: the live mission from 0:20 has finished | "Local, autonomous, checked. The sponsor paths: Zetaris is the only data path, H-MEM is the shared memory with a trust order, the World Model holds the council's decisions, Markovian runs the long reviews, Nemotron runs every agent." |

Fallbacks: the live mission is never waited for; the replay at 0:40 carries the demo. If Warden is asleep, the table still shows what it did.
If the council has nothing open, file a note from the crew page's form before recording so the session has something to decide.
The recording runs fully local (Ollama, `nemotron-mini`); say so. The Nightshift path is the same crew with one line of `.env`.
