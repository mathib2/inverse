# Sponsor technology: where each one does real work

The submission asks how Zetaris, Meterless, Cursor and NVIDIA are used. Every row names the code and the evidence; nothing listed here is a mention without a code path and a test.

## Zetaris (data)

**What it does:** it is the only data path. The equipment registry, the sensor specifications, the sensor samples and the maintenance history are REST tables that Zetaris federates from the team's `obs-service`, cached with `CACHE TABLE` and exposed through schemastore views. Scout and Ada query them read-only through a guard (one SELECT, known tables only, aliases, comma lists and subqueries checked); maintenance notes pass the injection guard before any model sees them; Warden's "new data" check is a Zetaris query per machine.

**Where:** `core/inverse_core/clients/zetaris.py`, `zetaris/sql/*.sql` (REST tables, cache, views), `scripts/setup_zetaris.py` (idempotent setup), `core/inverse_core/team/experts.py: check_sql` and `team/tools.py: run_sql`, `core/inverse_core/watch.py: fingerprint`.

**Evidence:** `tests/test_team.py` (the SQL guard), `tests/test_review_fixes.py` (aliases and subqueries), `tests/test_integration.py` (a live registry query), every trace's `tool` events with the query, `smoke_test.py`.

**Honest note:** the federated source is one synthetic service; the data is seeded and documented in `data/README.md`.

## Meterless (engines and provider)

| Engine / product | What it powers | Where | Evidence |
|---|---|---|---|
| **Nightshift** (provider) | The provider on the sponsor path (`MODEL_PROVIDER=nightshift`): every call of every agent goes through its OpenAI-compatible Runtime with the required headers, a fail-fast health check, retries, and `response_format: json_object`. The default is `ollama`, fully local, with the same client; the recording and the live evaluation can use Nightshift by changing one line of `.env`. | `core/inverse_core/clients/meterless.py`, `team/lanes.py` | the `llm` events in every trace with the served model; `tests/test_provider.py` |
| **H-MEM** | The crew's shared memory across missions: findings written only after Vera accepts, refuted claims with a trust order (a deterministic check outranks a tool result, which outranks a model's claim), and reviewer lessons per agent (Reflexion-style). | `services/meterless-sidecar/server.ts`, `core/inverse_core/ledger.py`, `team/memory.py` | `tests/test_integration.py::test_team_memory_on_hmem_survives_runs_and_breaks_without_engine` and `test_engine_honesty_stopping_the_sidecar_breaks_refuted_memory` (stop the sidecar, recall breaks); conformance 13/13 in `docs/evidence/hmem-conformance.txt` |
| **World Model** | Shared entities with stable IDs and idempotent sync through the sidecar. Honest status: wired and tested (`/world/record`, `/world/summary`), but after the physics subsystem was removed no mission writes to it yet; the council (in progress) records proposals and decisions there. | `core/inverse_core/clients/world.py`, `server.ts` | `test_world_model_idempotent_and_shared_evidence`; conformance 8/8 |
| **Markovian** | Sentinel's long code reviews run as one bounded chunk per file with a compressed carryover instead of a growing context. The vendored reference engine owns the mode prompts, the marker protocol, the carryover compression cascade, accounting and history; the host supplies the model replies. Measured usage is reported next to the engine's estimate. | `services/meterless-sidecar/markovian/`, `core/inverse_core/clients/markovian.py`, `team/custom.py: _review_chunked` | `tests/test_markovian.py` (scripted engine, and the real engine over HTTP); conformance 8/8 in `docs/evidence/markovian-conformance.txt` |
| Scout Intent | Not integrated in this branch. The injection guard is a heuristic stand-in and says so. | `core/inverse_core/agents/guard.py` | `tests/test_team.py` (a planted note is withheld) |

Details and file:line pointers: `docs/agent/ENGINE_EVIDENCE.md`.

## NVIDIA Nemotron (reasoning)

**What it does:** every agent's model calls run on Nemotron: locally, `nemotron-mini` (Nemotron-Mini-4B-Instruct) served by Ollama on the workstation; on the Nightshift path, the `fast`, `deep` and `critic` lanes map to Nemotron routes. The deterministic layer decides (the SQL guard, the number check, Vera's rules, the plan rule, the file-and-line check); Nemotron proposes, explains and reviews.

**Where:** `core/inverse_core/team/lanes.py`, `clients/meterless.py`, `docs/agent/LOCAL_MODELS.md` (measured speeds).

**Evidence:** every trace records the served model per call (`llm` events, `models_used`). Nightshift's router may serve a different Nemotron model than the lane asked for; the trace tells the truth.

## Cursor (build)

The repository was written with Claude Code on the team's Ubuntu workstation and a Windows laptop; Cursor was installed on the laptop. The team was told the Cursor requirement had been waived for this hackathon and has not yet found the announcement. If the rule stands as written, this is a gap the team declares rather than hides. Nothing in the repository blocks opening or editing it in Cursor.
