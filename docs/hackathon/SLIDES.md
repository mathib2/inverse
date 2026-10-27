# Slides (outline, 10 slides)

1. **INVERSE**
   - A crew of AI agents that plan, do the work, check each other, talk, and run on their own.
   - Track 03, Reasoning Architecture.
2. **The problem**
   - One model, one prompt, one answer: no plan, no review, no memory, no evidence.
   - It stops when you stop typing.
3. **The crew**
   - Atlas plans, Vera reviews, Warden keeps watch.
   - Scout looks things up, Euler derives, Ada solves with tools, Sentinel reviews our own code, Forge builds new agents.
   - Scout, Euler, Ada, Sentinel and Forge are a YAML file each; Atlas, Vera and Warden are fixed roles in code.
4. **A mission**
   - Plan by expertise: plain goals planned by rule, a plan review for three tasks or more, a rule fallback.
   - Work with bounded tools: read-only SQL through a guard, a calculator that also counts the days between two dates.
   - Vera's review: fixed rules, then code accepts what the tool results prove, then her model.
   - The answer is written from accepted results only; its numbers are checked like every task's; what did not finish is listed verbatim by code.
5. **They talk**
   - A message bus: results to everyone, notes to one agent, questions and answers.
   - Ada can ask another agent a question and gets its answer with evidence.
   - Every agent reads its messages as data from teammates, never as instructions.
6. **On their own**
   - Warden: queued goals, standing missions, new-data missions; manifests, recovery, heartbeat.
   - Tinker improves the crew's own code around the clock in a sandbox.
   - A Tinker change merges only after the tests, the agent's probe, Sentinel's review, Vera's vote and a veto window announced on the owner's phone.
7. **The council**
   - Agents propose changes to their own crew in a tiny wire protocol.
   - Short sessions of at most four model calls: Vera and the agent concerned vote, a rule decides.
   - Effects are applied by code, reversible, and recorded in the World Model.
8. **Memory and honesty**
   - H-MEM with a trust order: a deterministic check outranks a tool result, which outranks a model's claim.
   - Numbers must appear in the evidence; Vera sends weak work back with a reason.
   - A reviewer's lesson reaches an expert only for a task like the one it came from.
   - A note planted in the data is withheld before any model sees it; every mission replays from its files.
9. **Measured**
   - Eight checkable goals: 8/8 in 222 s on the workstation's CPU (round 17), 8/8 in 40 s on Nightshift (round 19).
   - Rounds 20 to 22 fell to 6/8, 6/8 and 7/8: every task was shown its expert's newest lessons, whatever the task was about.
   - After the fix, rounds 23 and 24: 8/8 in 32 s each, on Nightshift.
   - Warden's saved P-104 maintenance review: 16 s and 13 model calls on Nightshift, every task accepted.
10. **Sponsors, honestly**
   - Zetaris is the only data path; Cursor as declared in `SPONSORS.md`.
   - Meterless: Nightshift serves the model; H-MEM holds the shared memory; Markovian runs the long code reviews; the World Model holds the council's decisions.
   - NVIDIA Nemotron-Mini-4B on a laptop GPU through Nightshift, with the same model on the workstation's Ollama as the fallback.
   - Limits: one synthetic data service, a 4B model, a laptop that must stay awake. Next: a graphics card in the workstation.
