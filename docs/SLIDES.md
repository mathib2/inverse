# Slide deck content (8 slides)

1. **Title** – INVERSE: a physics-checked reverse-engineering agent. Track 3. Team + names (TODO).
2. **Problem & user** – A maintenance/controls engineer must decide whether a machine has worn. LLMs guess; plants can't act on a guess. Need: ACCEPT with uncertainty, REJECT with the failed test, or an honest "can't tell yet".
3. **Solution** – Every task is an inverse problem y = G(θ) + η. The LLM proposes; solvers, simulators and validators decide. Three verdicts: ACCEPT / REJECT / UNIDENTIFIABLE.
4. **Agent architecture** – the flow diagram from README (Planner → Zetaris join → identifiability → rounds → validators → Critic → Reporter), plus traces.
5. **Stack & sponsor usage** – Zetaris (federation: samples + σ/units + registry + maintenance), Meterless H-MEM (hypothesis ledger, trust by source), Meterless World Model (shared entities, recalled evidence), Nightshift (only provider), Nemotron (Proposer/Critic/Reporter). Evidence: conformance 13/13, traces with serving model.
6. **What's unique** – A better-fitting model is vetoed on physics grounds; refusal before fitting with the measurement that fixes it; memory makes reruns faster (tested); injection note withheld.
7. **Results (visuals)** – P-104 damping 2.00 → 2.80 (+40%, 53σ); T-200 trap table (rmse 0.0381 vs 0.0389, AIC 193.4 vs 196.7, c = −0.28 → vetoed); robustness: the trap occurs in 5 of 80 seeds and the wrong model was accepted 0 of 30 times; 95% intervals cover the truth 95% of the time, also with 2× sensor noise; unidentifiable direction (m,c,k) with singular-value ratio 1e-8; warm vs cold table.
8. **Limitations & future work** – Synthetic data; one physical family; Scout Intent / Markovian not integrated; next: real sensor logs, software adapter, experiment design.
