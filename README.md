# INVERSE: a physics-checked reverse-engineering agent

**Turn sensor logs into a verified physics model, or an honest refusal.**
Open Agent Hackathon 2026 · Track 3 (Reasoning Architecture)

A maintenance engineer asks *"what governs this machine, and has it worn?"*. INVERSE recovers the hidden physical parameters from sensor data and answers one of three ways, never on LLM judgment alone:

| Verdict | Meaning |
|---|---|
| **ACCEPT** | A model with 95% parameter intervals, the tests it passed, what was *not* checked, and a maintenance flag if a parameter drifted beyond its uncertainty |
| **REJECT** | Every candidate failed a named physics test |
| **UNIDENTIFIABLE** | The data cannot answer the question. The agent refuses *before fitting* and names the measurement that would resolve it |

**The LLM proposes. Solvers, simulators and validators decide.** A model that fits *better* is vetoed if its physics is wrong.

## What it does (three demo scenarios, all seeded and reproducible)

1. **Pump P-104, has it worn?** Damping is recovered at 2.80 ± 0.03 N·s/m (95%). H-MEM recalls last month's baseline (2.00). The agent raises a **maintenance flag: damping +40%, 53σ**.
2. **Rig T-200, better fit vs physics.** A 4-parameter SINDy-style model fits better (lower chi², lower AIC) but has *negative damping*. The **stability and energy validators veto it**; the honest linear model is accepted. The veto is written to the ledger with source `validator`.
3. **Pump P-104, mass unknown.** From free-decay data only the ratios c/m and k/m are determined (Jacobian rank 2 of 3). The agent **refuses**, and recommends *a forced response with a known 1 N force at 1.5 Hz* (largest Fisher determinant among the candidate experiments).

**Memory works:** rerun a question and refuted models are skipped (fewer rounds, fits and LLM calls). Stop the H-MEM sidecar and that behavior visibly breaks; this is an automated test.

## Architecture

```
Laptop (Windows)                                OptiPlex (Ubuntu, Docker)
┌─────────────────────────┐  SSH tunnel     ┌────────────────────────────────────────────┐
│ Meterless Nightshift    │◄─ -R 8088 ──────│ Zetaris platform (UI :3000, REST :8888)    │
│  Runtime :8088          │                 │ obs-service (FastAPI) on zetaris_default   │
│  NVIDIA key → Nemotron  │── -L 3000/8888/ │ Node sidecar: H-MEM + World Model :8100       │
│ Browser: Streamlit UI   │       8501 ────►│ Python core: orchestrator, math, validators│
└─────────────────────────┘                 │ Streamlit UI :8501                         │
                                            └────────────────────────────────────────────┘
question → Planner → Zetaris join (samples + sensor σ/units + equipment + maintenance)
        → injection guard → Identifiability (Jacobian rank, Fisher; REFUSE early)
        → rounds [ SINDy + Proposer(LLM) → MAP fit + Laplace → Validators (no LLM) ]
        → Critic (LLM picks a falsification test; the test decides) → verdict → Reporter (LLM)
Every step: JSONL trace in runs/<ts>/ · every veto: H-MEM ledger, source=validator (high trust)
```

## Sponsor technology (each does real work)

| Sponsor | Role in INVERSE |
|---|---|
| **Zetaris** | Federates four fragments with one SQL join: sensor samples, sensor specs (σ and units feed the likelihood and the units validator), equipment registry (mass), maintenance history. REST tables over `obs-service`, `CACHE TABLE`d, exploded by schemastore views (`zetaris/sql/`). |
| **Meterless World Model** | Shared state between agents and runs: equipment, dataset, hypothesis and validator-result entities with content-addressed stable IDs (idempotent re-sync, tested). On a warm run the Reporter's "recalled from memory" evidence is read from it. Passes conformance 8/8 (`docs/evidence/world-model-conformance.txt`). |
| **Meterless H-MEM** | The hypothesis ledger across runs (Node sidecar over the real reference implementation). Refutations persist; trust is by source, so a validator's veto cannot be overwritten by an LLM claim. Passes its conformance suite (`docs/evidence/hmem-conformance.txt`, 13/13). |
| **Meterless Nightshift** | The only LLM provider. All calls go through its OpenAI-compatible Runtime (`core/inverse_core/clients/meterless.py`), with the required headers, retry and a fail-fast health indicator. |
| **NVIDIA Nemotron** | Proposer, Critic and Reporter run on Nemotron lanes through Nightshift. The serving model reported by each response is stored in every trace (`docs/evidence/traces/`, `models_used` in the verdict). |
| Dev tooling | Claude Code on the team's OptiPlex. The Cursor requirement was waived by the organizers. |

Not integrated: Markovian and Scout Intent. The injection guard (`agents/guard.py`) is a **heuristic stand-in**; the Scout Intent engine is not integrated.

## Math (nothing more than needed)

MAP fit with `scipy.optimize.least_squares` on sensor-σ-whitened residuals, with the initial state (x0, v0) fitted jointly · Laplace uncertainty `Cov ≈ (JᵀΣ⁻¹J)⁻¹`, scaled by `max(1, χ²_red)` so intervals widen when the sensor spec understates the noise · identifiability by Jacobian SVD in log-parameter space (rank threshold 1e-6) and Fisher spectrum · a PySINDy regression initialises the full-library candidate (threshold 0, no sparsification, so the most flexible model always faces the validators) · AIC/BIC + held-out rollouts (refit on the first 70%, predict the unseen last 30%) · drift rule `|Δθ| > 3·√(σ_now²+σ_base²)` · next measurement maximizes `det F` over simulated experiments.
Validators (`core/inverse_core/validators/`): Pint units · energy and dissipation sign · numerical integrity under tolerance refinement · regime of validity · stability of the linearization · goodness of fit (reduced χ² with residual whiteness: structured misfit is vetoed, white excess noise only widens the intervals).
Calibration: across 40 seeds the 95% intervals contain the true damping 95% of the time, also when the real sensor noise is 2× the spec.

## Setup

Requires Docker (with the Zetaris platform running and healthy), Node 22, Python 3.12+.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill ZETARIS_API_KEY (from the Zetaris UI) and MODEL_* (from Nightshift's Console)
git clone --depth 1 https://github.com/Meterless/Meterless ~/vendor/Meterless      # H-MEM reference source
(cd services/meterless-sidecar && npm install && npm run setup)                  # copies the H-MEM reference into vendor/ (gitignored)
(cd services/obs-service && docker compose up -d --build)          # joins the zetaris_default network
PYTHONPATH=core .venv/bin/python scripts/setup_zetaris.py    # creates the Zetaris database, REST tables, caches and views (idempotent)
```

From the laptop, open **one** tunnel (PowerShell on the laptop, never on the server):
`ssh -L 3000:localhost:3000 -L 8888:localhost:8888 -L 8501:localhost:8501 -R 8088:127.0.0.1:8088 <user>@<server>`

## Usage

```bash
scripts/run_demo.sh                       # starts the sidecar and the UI (http://localhost:8501 through the tunnel)
PYTHONPATH=core .venv/bin/python scripts/run_agent.py "Rig T-200 was reassembled. What governs its vibration?" --reset T-200
PYTHONPATH=core .venv/bin/python -m pytest -q tests     # 40 tests incl. live Zetaris + sidecar integration
```

## Team of experts (orchestrator)

A lead agent turns a goal into a plan (tasks + assigned experts), delegates by dependency, a Critic on a separate Nemotron lane can send work back, and the final answer cites expert evidence.
The single-machine page and CLI above are unchanged and remain the fallback.

```bash
PYTHONPATH=core .venv/bin/python scripts/run_team.py "Pump P-104 vibration changed. Has it worn, and what does its registry mass imply for the spring force at 5 mm given the fitted stiffness?" [--edit] [--reset]
```
In the UI choose **Mode → Team of experts**: make a plan, edit it in the table, **Approve and run**.

- Experts are config: `experts/*.yaml` (name, kind, role, `system_prompt_file`, tools, `model_lane`, budget, enabled) and `prompts/*.md`. Add, re-scope or disable one without touching code. Kinds: `physics` (wraps the existing pipeline unchanged), `research` (Zetaris read-only SQL, cites queries), `reasoning` (decompose, solve, recompute every calculation).
- Lanes (`fast`, `deep`, `critic`) map to Nemotron routes in `team/lanes.py`; override with `LANE_*` in `.env`. The serving model of every call is in `runs/<ts>/trace.jsonl`.
- Team memory lives in H-MEM (`team:shared`); **Forget past results** clears it too. Evidence: `docs/agent/ENGINE_EVIDENCE.md`.

## Honest limitations

- Data is **synthetic** (fixed seeds, documented in `data/README.md`); the trap case is constructed (one fixed seed where an over-flexible model overfits to the wrong sign). No real plant data was used.
- One physical family (1-DOF vibration). The `software` adapter is only an interface stub.
- The initial state (x0, v0) is estimated jointly with the parameters; the first sample is only the starting guess.
- The planner is deterministic: a question naming no known equipment is refused rather than mapped to a default.
- Nightshift runs on the laptop: the tunnel and laptop must be on when the agent calls a model; the UI shows health and fails fast.
