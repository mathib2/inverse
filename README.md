# INVERSE: a physics-checked reverse-engineering agent, and the team of experts around it

**Turn sensor logs into a verified physics model, or an honest refusal. Then let a team of configurable experts plan, check each other, and answer with evidence.**
Open Agent Hackathon 2026 · Track 03 (Reasoning Architecture) · Zetaris + Meterless + NVIDIA Nemotron

After a repair or reassembly, a reliability engineer runs a release test on a machine and asks *"what governs this machine now, and has it worn since the last test?"*. INVERSE recovers the hidden physical parameters from the sensor data and answers one of three ways, never on LLM judgment alone:

| Verdict | Meaning |
|---|---|
| **ACCEPT** | A model with 95% parameter intervals, the physics tests it passed, what was *not* checked, and a maintenance flag if a parameter drifted beyond its uncertainty |
| **REJECT** | Every candidate failed a named physics test |
| **UNIDENTIFIABLE** | The data cannot answer the question. The agent refuses *before fitting* and names the measurement that would resolve it |

**The LLM proposes. Solvers, simulators and validators decide.** A model that fits *better* is vetoed if its physics is wrong. The same rule runs at team level: a lead plans, experts defined by config do the work, a Critic on a separate model lane sends weak work back, and every number in the answer must come from evidence.

## For judges: where to look

| Criterion | Evidence |
|---|---|
| Impact | The user and the decision are above. What that is worth: a wear decision with calibrated uncertainty instead of a guess, and a refusal that says what to measure next. `docs/evidence/EVAL.md`: wear flagged 20 of 20 times when planted, 0 false alarms in 20, refusal 20 of 20 when the data cannot answer. |
| Technical | `core/inverse_core/`: identifiability by SVD of the sigma-whitened log-parameter Jacobian before any fit; whitened least squares with the initial state as nuisance parameters; Laplace intervals with Birge scaling; six validators; held-out rollouts. Measured interval coverage 93-100% (`docs/evidence/EVAL.md`). 80+ tests, CI on every push. |
| Innovation | Refusal before fitting with the resolving experiment named; a better-fitting model vetoed on physics grounds (0 of 80 trap seeds accepted a negative-damping model); experts that review the plan; a lead that creates an expert when none fits; code-review findings that must point at a real line or are dropped. |
| Demo | `docs/DEMO_SCRIPT.md`, saved runs replayable in the UI without a model, traces with the served model per call in `docs/evidence/traces/`. |
| Product & UX | One wording layer (`ui/plain.py`, tests fail on jargon), three one-click scenarios, live progress in plain sentences, a plan you can edit before it runs, an experts panel to change the team without code. |
| Sponsor tech | The table below: every sponsor has a code path, a test and an evidence file. |

## What it does (three seeded, reproducible scenarios)

1. **Pump P-104, has it worn?** Damping is recovered with a 95% interval; H-MEM recalls last month's baseline; the agent raises a **maintenance flag** when the change is beyond the combined uncertainty (3-sigma rule, `inference/drift.py`).
2. **Rig T-200, better fit versus physics.** A 4-parameter SINDy-style model fits better (lower chi-square and AIC) but has *negative damping*. The **stability and energy validators veto it**; the honest linear model is accepted. The veto is written to H-MEM with source `validator`.
3. **Pump P-104, mass unknown.** From free-decay data only the ratios c/m and k/m are determined (Jacobian rank 2 of 3). The agent **refuses before fitting** and recommends *a forced response with a known 1 N force at 1.5 Hz* (largest Fisher determinant among candidate experiments).

**Memory works:** rerun a question and refuted models are skipped (fewer rounds, fits and LLM calls). Stop the H-MEM sidecar and that behaviour visibly breaks; this is an automated test.

## Evidence (measured, reproducible)

- `docs/evidence/EVAL.md`: planted-scenario evaluation of the deterministic pipeline (no LLM): wear flagged 20/20 at +40%, 0/20 false alarms, wrong trap model accepted 0/80 (vetoed every time the bait fit better, 31/80), refusal 20/20 with the forced version identifiable 20/20, interval coverage 93% (c) and 100% (k). `scripts/eval_report.py` regenerates it.
- `docs/evidence/EVAL_LIVE.md` (produced by `scripts/eval_live.py` whenever Nightshift is reachable; costs model calls): the three demo questions run end to end through Zetaris, Nightshift/Nemotron and H-MEM, repeated; verdict stability, every number in the narrative checked against the verified result, citation validity in the team answer, run times.
- `docs/evidence/traces/`: JSONL traces of live runs with the served model per call. `docs/evidence/*-conformance.txt`: the Meterless reference implementations pass their conformance suites in our setup.

## Architecture

```
Nightshift host (Windows laptop)                 Workstation (Ubuntu, Docker)
┌─────────────────────────┐  SSH reverse    ┌─────────────────────────────────────────────┐
│ Meterless Nightshift    │◄─ tunnel 8088 ──│ Zetaris platform (UI :3000, REST :8888)     │
│  Runtime :8088          │                 │ obs-service (FastAPI): sensor data source   │
│  NVIDIA key → Nemotron  │                 │ Node sidecar: H-MEM + World Model :8100     │
└─────────────────────────┘                 │ Python core: orchestrator, math, validators │
                                            │ Team: lead, experts, critic, tools          │
                                            │ Streamlit UI :8501                          │
                                            └─────────────────────────────────────────────┘
Single machine:  question → Planner → Zetaris join (samples + sensor σ/units + registry) + maintenance query
        → injection guard → Identifiability (Jacobian rank, Fisher; REFUSE early)
        → rounds [ SINDy + Proposer(LLM) → MAP fit + Laplace → Validators (no LLM) ]
        → Critic (LLM picks a falsification test; the test decides) → verdict → Reporter (LLM, numbers checked)
Team:            goal → Lead plans (Nemotron) → experts review the plan → delegate by dependency
        → each expert returns an answer with evidence → Critic on its own lane: accept | revise (retry) | reject
        → compose with citations [T1.E2]; unfinished tasks reported verbatim by code
Every step: JSONL trace in runs/<ts>/ · every veto and finding: H-MEM, trust by source
```

## Sponsor technology (each does real work)

| Sponsor | Role in INVERSE | Where |
|---|---|---|
| **Zetaris** | The only data path. One SQL join over the REST tables it federates (sensor samples, sensor specs whose σ and units feed the likelihood and the units validator, the equipment registry with the mass) plus a maintenance-history query; the team's Research expert and `run_sql` tool query it read-only through a guard. Tables are `CACHE TABLE`d and exploded by schemastore views. The federated source is our own `obs-service`. | `clients/zetaris.py`, `zetaris/sql/`, `team/tools.py`, `tests/test_integration.py` |
| **Meterless H-MEM** | The hypothesis ledger across runs and the team's shared memory, through the vendored reference implementation (store, tags, source and confidence on every record). Trust by source is applied before a write (`ledger.py`): a validator's refutation cannot be overwritten by an LLM claim. Engine test: stop the sidecar and recall breaks. | `services/meterless-sidecar/server.ts`, `ledger.py`, `team/memory.py`, `docs/agent/ENGINE_EVIDENCE.md` |
| **Meterless World Model** | Shared entities (equipment, dataset, hypothesis, validator result) with stable IDs and idempotent sync; the Reporter's "recalled from memory" evidence is read from it. Conformance 8/8. | `clients/world.py`, `server.ts` |
| **Meterless Nightshift** | The only LLM provider. Every call goes through its OpenAI-compatible Runtime with the required headers, retry, a fail-fast health check, and `response_format: json_object` for every structured reply. | `clients/meterless.py` |
| **NVIDIA Nemotron** | Proposer, Critic and Reporter, and the team's lead, experts and Critic, run on Nemotron routes (`team/lanes.py`: fast, deep, critic). Nightshift's router may serve a different Nemotron model than requested; the served model of every call is in the trace and in `models_used`. | `team/lanes.py`, `runs/<ts>/trace.jsonl` |
| **Development tooling** | Written with Claude Code on the team's Ubuntu workstation and a Windows laptop; Cursor was installed on the laptop. The team was told the Cursor requirement had been waived and has not yet found the announcement; if the rule stands, this is a gap we declare rather than hide. | |

Not integrated: Markovian and Scout Intent (in progress on separate branches). The injection guard (`core/inverse_core/agents/guard.py`) is a **heuristic stand-in** until Scout Intent lands.

## Math (nothing more than needed)

MAP fit with `scipy.optimize.least_squares` on sensor-σ-whitened residuals, with the initial state (x0, v0) fitted jointly · Laplace uncertainty `Cov ≈ (JᵀΣ⁻¹J)⁻¹`, scaled by `max(1, χ²_red)` so intervals widen when the sensor spec understates the noise · identifiability by Jacobian SVD in log-parameter space (rank threshold 1e-6) and Fisher spectrum · a PySINDy regression initialises the full-library candidate (threshold 0, no sparsification, so the most flexible model always faces the validators) · AIC/BIC + held-out rollouts (refit on the first 70%, predict the unseen last 30%) · drift rule `|Δθ| > 3·√(σ_now²+σ_base²)` · next measurement maximizes `det F` over simulated experiments.
Validators (`core/inverse_core/validators/`): Pint units · energy and dissipation sign · numerical integrity under tolerance refinement · regime of validity · stability of the linearization · goodness of fit (reduced χ² with residual whiteness: structured misfit is vetoed, white excess noise only widens the intervals).
Measured, not claimed: `docs/evidence/EVAL.md` (interval coverage, false alarms, trap vetoes, refusals, per-seed rows in `eval_results.json`).

## Setup

Requires Docker (with the Zetaris platform running and healthy), Node 22, Python 3.14 (versions pinned in `requirements.txt`).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # ZETARIS_* from the Zetaris UI; MODEL_BASE_URL, MODEL_API_KEY, NEMOTRON_MODEL from Nightshift's Console
git clone --depth 1 https://github.com/Meterless/Meterless ~/vendor/Meterless      # engine reference sources
(cd services/meterless-sidecar && npm install && npm run setup)                  # copies the H-MEM and World Model references into vendor/ (gitignored)
(cd services/obs-service && docker compose up -d --build)          # joins the zetaris_default network
PYTHONPATH=core .venv/bin/python scripts/setup_zetaris.py    # creates the Zetaris database, REST tables, caches and views (idempotent)
```

Nightshift runs on the machine that has the NVIDIA key; from there, open one reverse tunnel to the server so the Runtime is reachable at `127.0.0.1:8088`:
`ssh -N -R 8088:127.0.0.1:8088 <user>@<server>`

## Usage

```bash
scripts/run_demo.sh                       # starts the sidecar and the UI (http://localhost:8501)
PYTHONPATH=core .venv/bin/python scripts/run_agent.py "Rig T-200 was reassembled. What governs its vibration?" --reset T-200
PYTHONPATH=core .venv/bin/python scripts/run_team.py "Pump P-104 vibration changed. Has it worn, and what does its registry mass imply for the spring force at 5 mm given the fitted stiffness?" --collaborate
PYTHONPATH=core .venv/bin/python -m pytest -q tests     # unit tests with a scripted model; the live Zetaris + sidecar tests skip when those are down
PYTHONPATH=core .venv/bin/python scripts/eval_report.py # regenerates docs/evidence/EVAL.md (no model calls, ~20 min)
```

## Team of experts (orchestrator)

A lead agent turns a goal into a plan (tasks + assigned experts), delegates by dependency, a Critic on a separate Nemotron lane can send work back, and the final answer cites expert evidence. The single-machine page and CLI above are unchanged and remain the fallback.

In the UI choose **Mode → Team of experts**: make a plan, edit it in the table, **Approve and run**, or **Replay a saved run** without a model.

- **Experts are config, not code:** `experts/*.yaml` (name, kind, role, `system_prompt` or `system_prompt_file`, tools, `model_lane`, budget, enabled). `experts.local/*.yaml` (gitignored) adds experts or overrides a built-in; the UI panel **Experts · customize the team** writes there. Kinds: `physics` (wraps the existing pipeline unchanged), `research` (Zetaris read-only SQL, cites queries), `reasoning` (decompose, solve, recompute every calculation), `custom` (a tool-using agent defined only by its config; the built-in `solver` is one), `vulnerability` (defensive code review of this repository; every finding is checked against the file and line it cites). Details: `docs/agent/EXPERTS.md`.
- **Tools** (`team/tools.py`, read-only and budgeted): `run_sql` (same guard as the Research expert), `calc`, `list_files`/`read_file`/`grep` (inside this repository only, never secrets), `scan` (fixed weak-spot rules with severities), `memory`.
- **The lead can create an expert** when none fits a task (a `custom` expert with a fixed budget, registered for the run; **Keep it** saves it). **Experts review the plan** before it runs (`--collaborate` / the UI toggle): each reworks only its own tasks; the physics expert reviews by rule (a task must name a machine).
- **Safety scope:** code we own, defensive only. A task that asks for exploit code or names an external system is refused before any model call, traced (`refused_scope`), rejected by the Critic by rule, and written to team memory as refuted.
- Lanes (`fast`, `deep`, `critic`) map to Nemotron routes in `team/lanes.py`; override with `LANE_*` in `.env`. The serving model of every call is in `runs/<ts>/trace.jsonl`.
- Team memory lives in H-MEM (`team:shared`); **Forget past results** clears it too. Evidence: `docs/agent/ENGINE_EVIDENCE.md`.

## Honest limitations

- **Data is synthetic** (fixed seeds, documented in `data/README.md`); the trap case is constructed (seed 68 was chosen by search; the full trap occurs in 31 of 80 seeds and the wrong model was accepted in 0 of 80). No real plant data was used.
- **The method needs a release (bump) test:** free decay from a known initial state, with displacement and velocity channels. Operational (forced) vibration is not supported yet, and the forced-response measurement the agent recommends after a refusal cannot be ingested by this version.
- **Two machines and three datasets** are configured in the data source, the Zetaris views and the client; onboarding a new machine means adding it in those three places.
- One physical family (1-DOF vibration). The `software` adapter is only an interface stub.
- The initial state (x0, v0) is estimated jointly with the parameters; the first sample is only the starting guess.
- The planner is deterministic: a question naming no known equipment is refused rather than mapped to a default.
- Nightshift runs on a laptop: the tunnel and laptop must be on when the agent calls a model; the UI shows health and fails fast, and saved runs can be replayed without it.

## License

Apache License 2.0 (`LICENSE`). Pre-existing work: `docs/agent/PREEXISTING.md`.
