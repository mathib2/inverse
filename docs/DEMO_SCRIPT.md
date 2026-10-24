# Demo script (target 3:00, record with everything healthy; never use SAMPLE_MODE)

Before recording: Nightshift open on the laptop with the NVIDIA key and a Nemotron lane; laptop tunnel open (PowerShell); UI at http://localhost:8501 shows Nightshift 🟢 and Zetaris 🟢; click **Reset memory** for P-104 and T-200.

| Time | Screen | Say |
|---|---|---|
| 0:00 | UI title | "A controls engineer needs to know what physically governs a machine, and whether it has worn, without trusting an LLM's guess. INVERSE: a verified physics model, or an honest refusal." |
| 0:15 | Zetaris SQL Editor (`scripts/zetaris_join_demo.py` output or the join) | "Four fragments, one Zetaris join: samples, sensor specs, equipment registry, maintenance history. The sensor sigma and units from Zetaris feed the likelihood and the units validator." |
| 0:35 | Scenario **Rig T-200**, Run | "Nemotron, through Meterless Nightshift, proposes model forms. SINDy proposes a more flexible one." |
| 0:55 | Validator table | "The flexible model fits better, lower chi-square and AIC. But damping came out negative. The stability and energy validators veto it. No LLM judged that. The veto is written to the ledger with source validator." |
| 1:20 | Ledger panel (H-MEM) | "Meterless H-MEM keeps the ledger. Trust is by source: an LLM can't overwrite a validator's refutation." |
| 1:35 | **Run again** (warm) | "Same question again. The refuted model is recalled from memory and skipped: one round instead of two, fewer fits, fewer LLM calls." (point at Run history table) |
| 1:55 | Scenario **Pump P-104**, Run | "Pump P-104. Damping 2.80 plus or minus 0.03. Last month's baseline recalled from H-MEM was 2.00. Maintenance flag: damping up 40 percent, 53 sigma." |
| 2:20 | Scenario **mass unknown**, Run | "Now the mass is unknown. From free decay only the ratios are determined: Jacobian rank 2 of 3. The agent refuses before fitting, and names the measurement that would resolve it: a forced response with a known force." |
| 2:40 | Injection note in the result / trace | "A maintenance note told the system to mark everything accepted. It was withheld before reaching any model." |
| 2:50 | Nightshift Archive/run details | "Every call went through Nightshift to Nemotron. Proof is in the trace." |
| 3:00 | End card | "INVERSE. The LLM proposes. Physics decides." |

Backup if a live run is slow: show `docs/evidence/traces/` and the saved verdicts.
