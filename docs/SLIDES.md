# Slides (outline, 8 slides)

1. **INVERSE** · a crew of local AI agents that work, check each other, talk, and run on their own. Track 03, Reasoning Architecture.
2. **The problem** · one model, one prompt, one answer: no plan, no review, no memory, no evidence, and it stops when you stop typing.
3. **The crew** · Atlas, Vera, Warden, Scout, Euler, Ada, Sentinel, Forge: what each does, and that each is a YAML file.
4. **A mission** · plan by expertise (plan review, rule fallback) → work with bounded tools → Vera's review (rules, then model) → an answer that cites every claim and lists verbatim what did not finish.
5. **They talk** · the message bus: results to everyone, notes to one agent, questions and answers; data, never instructions.
6. **On their own** · Warden: queued goals, standing missions, new-data missions; manifests, recovery, heartbeat. **The council** · agents propose changes in a tiny wire protocol; short sessions decide by rule; effects are reversible and recorded in the World Model.
7. **Memory and honesty** · H-MEM with a trust order; numbers must appear in evidence; a Critic that sends work back; replay from files.
8. **Sponsors, honestly** · Zetaris the only data path; Meterless H-MEM, Markovian, World Model, Nightshift; NVIDIA Nemotron locally and through Nightshift; Cursor as declared. Limits and what is next.
