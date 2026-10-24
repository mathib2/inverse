# Sponsor technology: where each one does real work

The submission asks how Zetaris, Meterless, Cursor and NVIDIA are used. Every row names the code and the evidence; nothing listed here is a mention without a code path and a test.

## Zetaris (data)

**What it does:** it is the only data path. The equipment registry (mass), the sensor specifications (σ and units, which feed the whitened likelihood and the units validator), the sensor samples and the maintenance history are REST tables that Zetaris federates from the team's `obs-service`, cached with `CACHE TABLE` and exposed through schemastore views. One SQL join returns samples plus sensor σ/units plus registry mass; a separate query returns the maintenance notes (which pass the injection guard before any model sees them). The team's Research expert and the `run_sql` tool query Zetaris read-only through a guard (single SELECT, known tables only, comma lists and subqueries checked).

**Where:** `core/inverse_core/clients/zetaris.py` (the join, `maintenance`, `dataset_id`), `zetaris/sql/01_*.sql` and `02_obs_tables_and_views.sql` (REST tables, cache, views), `scripts/setup_zetaris.py` (idempotent setup), `core/inverse_core/team/experts.py: check_sql` and `team/tools.py: run_sql`.

**Evidence:** `tests/test_integration.py` (live SQL over REST), `smoke_test.py` (Zetaris web and SQL), every trace's `zetaris_join` event with row count, σ and mass.

**Honest note:** the federated source is one synthetic service; the data is seeded and documented in `data/README.md`.

## Meterless (engines and provider)

| Engine / product | What it powers | Where | Evidence |
|---|---|---|---|
| **Nightshift** (provider) | The only LLM provider. Every call of the single agent (Proposer, Critic, Reporter) and of the team (lead, experts, Critic) goes through its OpenAI-compatible Runtime with the required headers, a fail-fast health check, retries, and `response_format: json_object` for structured replies. | `core/inverse_core/clients/meterless.py`, `team/lanes.py` | the `llm` events in every trace with the served model; `smoke_test.py` |
| **H-MEM** | The hypothesis ledger across runs (refutations persist, trust by source: a validator's veto cannot be overwritten by an LLM claim), the team's shared memory (findings written only after the Critic accepts), and the team's lessons (a reviewer's reason kept per expert, Reflexion-style). | `services/meterless-sidecar/server.ts`, `core/inverse_core/ledger.py`, `team/memory.py` | `tests/test_integration.py::test_team_memory_on_hmem_survives_runs_and_breaks_without_engine` and `test_engine_honesty_stopping_sidecar_breaks_refuted_memory` (stop the sidecar, recall breaks); conformance 13/13 in `docs/evidence/hmem-conformance.txt` |
| **World Model** | Shared entities across agents and runs (equipment, dataset, hypothesis, validator result) with stable IDs and idempotent sync; the Reporter's "recalled from memory" evidence is read from it. | `core/inverse_core/clients/world.py`, `server.ts` | `test_world_model_idempotent_and_shared_evidence`; conformance 8/8 |
| **Markovian** | Long code reviews run as one bounded chunk per file with a compressed carryover instead of a growing context. The vendored reference engine owns the mode prompts, the marker protocol, the carryover compression cascade, accounting and history; the host supplies the model replies. Measured Nightshift usage is reported next to the engine's estimate. | `services/meterless-sidecar/markovian/`, `core/inverse_core/clients/markovian.py`, `team/custom.py: _review_chunked` | `tests/test_markovian.py` (scripted engine, and the real engine over HTTP); conformance 8/8 in `docs/evidence/markovian-conformance.txt` |
| Scout Intent | Not integrated in this branch (in progress separately). The injection guard is a heuristic stand-in and says so. | `core/inverse_core/agents/guard.py` | `test_live_progress_lines_are_plain` (a planted note is withheld) |

Details and file:line pointers: `docs/agent/ENGINE_EVIDENCE.md`.

## NVIDIA Nemotron (reasoning)

**What it does:** all reasoning calls run on Nemotron routes through Nightshift: the Proposer (model forms), the Critic (which falsification test to run), the Reporter (plain-language summary with every number checked), the team's lead (planning, optional self-consistency voting), every expert, the plan review and the team Critic on its own lane. The deterministic layer decides; Nemotron proposes, explains and reviews.

**Where:** `core/inverse_core/team/lanes.py` (`fast`, `deep`, `critic` map to Nemotron routes, overridable with `LANE_*`), `agents/proposer.py`, `agents/critic.py`, `agents/reporter.py`, `team/lead.py`.

**Evidence:** every trace records the served model per call (`llm` events, `models_used`); today's live single-agent runs show Nemotron-proposed candidates reaching the fit (`survivor` events for `llm_*` forms). Nightshift's router may serve a different Nemotron model than the lane asked for; the trace tells the truth.

## Cursor (build)

The repository was written with Claude Code on the team's Ubuntu workstation and a Windows laptop; Cursor was installed on the laptop. The team was told the Cursor requirement had been waived for this hackathon and has not yet found the announcement. If the rule stands as written, this is a gap the team declares rather than hides. Nothing in the repository blocks opening or editing it in Cursor.
