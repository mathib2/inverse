# Sponsor technology: where each one does real work

The submission asks how Zetaris and Meterless were integrated, how Cursor was used (if it was), where NVIDIA technology contributes, and what was unique about our use of the sponsor technologies. Every row names the code and the evidence; nothing listed here is a mention without a code path and a test.

## Zetaris (data)

**What it does:** it is the only data path. The equipment registry, the sensor specifications, the sensor samples and the maintenance history are REST tables that Zetaris federates from the team's `obs-service`, cached with `CACHE TABLE` and exposed through schemastore views. Scout and Ada query them read-only through a guard (one SELECT on known tables only; every table behind an alias or a comma checked; subqueries refused); maintenance notes pass the injection guard before any model sees them; Warden's "new data" check is a Zetaris query per machine.

**Where:** `core/inverse_core/clients/zetaris.py`, `data/zetaris/*.sql` (REST tables, cache, views), `scripts/admin/setup_zetaris.py` (idempotent setup), `core/inverse_core/team/sql_guard.py: check_sql` and `team/tools.py: Tools._run_sql` (the `run_sql` tool), `core/inverse_core/team/watch.py: Watcher.fingerprint`.

**Evidence:** `tests/test_guard.py` (the SQL guard: known tables only, every table behind an alias or a comma, subqueries and Spark built-ins refused), `tests/test_integration.py` (a live registry query), every query in a mission's files (Scout's as `sql` evidence in `plan.json`, the `run_sql` tool's as `tool` events in the trace), `smoke_test.py`.

**Honest note:** the federated source is one synthetic service; the data is seeded and documented in `data/README.md`.

## Meterless (engines and provider)

| Engine / product | What it powers | Where | Evidence |
|---|---|---|---|
| **Nightshift** (provider) | The primary provider (`MODEL_PROVIDER=nightshift`, the default): the live crew's model calls go to its OpenAI-compatible Runtime with the required headers, retries and `response_format: json_object`. It serves NVIDIA Nemotron-Mini-4B from a Nightshift lane on a laptop GPU (`local-runtime/nemotron-mini-4b-instruct-q4-k-m`). A call Nightshift cannot answer goes to the workstation's Ollama with the same model; for the next two minutes every call goes there directly, and then Nightshift is tried first again. | `core/inverse_core/clients/meterless.py`, `team/lanes.py` | the `llm` events in every trace since the provider change of 26 October name the served model and the provider (`nightshift` or `fallback`); `tests/test_provider.py`; benchmark rounds 26 and 27 on Nightshift, 8/8 in 30 s each, every number exact (7/8 read strictly) (`docs/evidence/bench/round26-exact.json`, `round27-planlane.json`) |
| **H-MEM** | The crew's shared memory across missions: findings written only after Vera accepts, refuted claims with a trust order (a deterministic check outranks a tool result, which outranks a model's claim), and reviewer lessons per agent (Reflexion-style), shown to an agent only for a task like the one they came from. | `services/meterless-sidecar/server.ts`, `core/inverse_core/ledger.py`, `team/memory.py` | `tests/test_integration.py::test_team_memory_on_hmem_survives_runs_and_breaks_without_engine` and `test_engine_honesty_stopping_the_sidecar_breaks_refuted_memory` (stop the sidecar, recall breaks); conformance 13/13 in `docs/evidence/conformance/hmem.txt` |
| **World Model** | The council's shared record: every proposal is a hypothesis about the crew with its decision as status, and every vote is a result linked to it, with stable IDs and idempotent sync through the sidecar, mirrored into the World Model with stable IDs and idempotent sync; the council book under `council/` is what the agents and the Council panel read. | `core/inverse_core/team/council.py: Council._world`, `core/inverse_core/clients/world.py`, `server.ts` | `tests/test_council.py` (a session hands every decision and vote to the World Model client), `test_world_model_idempotent_and_shared_evidence`; conformance 8/8 in `docs/evidence/conformance/world-model.txt` |
| **Markovian** | Sentinel's long code reviews run as one bounded chunk per file with a compressed carryover instead of a growing context. The vendored reference engine owns the mode prompts, the marker protocol, the carryover compression cascade, accounting and history; the host supplies the model replies. Measured usage is reported next to the engine's estimate. | `services/meterless-sidecar/markovian/`, `core/inverse_core/clients/markovian.py`, `team/vulnerability.py: _review_chunked` | `tests/test_markovian.py` (scripted engine, and the real engine over HTTP); conformance 8/8 in `docs/evidence/conformance/markovian.txt` |
| Scout Intent | Not integrated in this branch. The injection guard is a heuristic stand-in and says so: every string cell of every query result is scrubbed before a model sees it. | `core/inverse_core/injection_guard.py` | `tests/test_guard.py` (the planted note is withheld; renamed columns too); the planted note withheld in a real mission, `docs/evidence/missions/20261026-195911` |

Details with file and symbol pointers: `docs/hackathon/ENGINE_EVIDENCE.md`. The tests in `tests/test_integration.py` and the real-engine test in `tests/test_markovian.py` need Zetaris or the vendored Meterless engines, which CI does not have, so CI skips these six tests. Real artifacts: `docs/evidence/missions/` (three missions with their traces and conversations: two from 24 October whose traces name `nemotron-mini:latest`, and Warden's maintenance review of 26 October, every call served by Nightshift) and `docs/evidence/bench/` (every benchmark round: rounds 18 to 31 ran through Nightshift on the laptop's GPU, and `nightshift-round1` through the sponsor's hosted Nemotron).

## NVIDIA Nemotron (reasoning)

**What it does:** every model call of the live crew runs on Nemotron-Mini-4B-Instruct: through Nightshift on a laptop GPU, or, when Nightshift cannot answer, served by Ollama on the workstation. The exception is Tinker, which runs in its own sandbox on Ollama; its engineer step uses `qwen2.5-coder:7b` (`TINKER_ENGINEER_MODEL`). With a hosted Nightshift the lanes map to larger Nemotron routes: Lightning-30B for the workers (`fast`, `deep`), Ultra-550B for Atlas's planning and write-up (`plan`) and Vera's review (`critic`) (`team/lanes.py`). Any lane can have its own endpoint (`LANE_<NAME>_URL`, `_KEY`): Atlas's `plan` lane and Vera's `critic` lane can run on a hosted Nightshift serving Nemotron-3-Ultra-550B while the workers stay on the laptop, and a call the endpoint cannot answer goes to the laptop's model (`clients/meterless.py: LaneEndpoint`). On the Ollama provider a lane can be pointed at another local model (`LANE_CRITIC=qwen2.5:3b-instruct` keeps Vera on a different model). The live crew runs all four lanes on the one Nightshift route (`plan` follows `deep`), and the fallback always answers with `MODEL_FALLBACK_MODEL`, so there Vera reviews on the same Nemotron as the work; her independence comes from her fixed rules and the code checks that run before her model. The trace always names the served model. The deterministic layer decides (the SQL guard, the number check, Vera's rules, the plan rule, the file-and-line check); Nemotron proposes, explains and reviews.

**Where:** `core/inverse_core/team/lanes.py`, `clients/meterless.py`, `docs/operations/NIGHTSHIFT_TUNNEL.md` (the Nightshift lane, about 59 tokens a second), `docs/operations/LOCAL_MODELS.md` (measured speeds).

**Evidence:** every trace records the served model per call (`llm` events, `models_used`). The benchmark runs the same Nemotron-Mini-4B both ways: 222 s on the workstation's CPU (round 17) and 40 s through Nightshift on the laptop's GPU (round 19), both 7/8 graded exactly (8/8 under the earlier 1 % grader); the current code passes 8/8 in 30 s on Nightshift with every number exact (rounds 26 and 27; 7/8 read strictly), and the crew did on the CPU in round 14 (548 s) (`docs/BENCH.md`). Nightshift's router may serve a different Nemotron model than the lane asked for; the trace tells the truth.

## What was unique about our use of the sponsor technologies

- **Zetaris drives the autonomy, not just the answers.** It is the crew's only data path, and Warden's trigger for a new mission is a
  Zetaris query per machine (`team/watch.py: Watcher.fingerprint`): when a machine's data changes, a mission starts with nobody at
  the keyboard. Every query passes a read-only guard, and every text cell passes an injection guard before a model sees it; a note
  planted in the maintenance table as an instruction to the AI is withheld in a real mission
  (`docs/evidence/missions/20261026-195911`).
- **Meterless H-MEM as a memory with a trust order.** A deterministic check outranks a tool result, which outranks a model's claim, so
  a refuted claim cannot be written back by a later model answer; reviewer lessons reach an agent only for a task like the one they
  came from (`team/memory.py`). Stopping the sidecar visibly breaks recall, and a test proves it.
- **Meterless World Model as the record of the crew's own governance.** Every change an agent proposes to its own crew is a hypothesis
  in the World Model, every council vote a result linked to it, and every adopted change is applied by code and can be undone
  (`team/council.py`).
- **Meterless Markovian for bounded code reviews.** Sentinel reviews long code one chunk per file with a compressed carryover instead
  of a growing context, so a 4B model with a 4,096-token window reviews up to six files with scan hits, one chunk each, and lists the files it did not review (`team/vulnerability.py: _review_chunked`).
- **Meterless Nightshift as a provider with a per-call fallback and per-lane endpoints.** Each call goes to Nightshift first and to the
  workstation's own Nemotron when it cannot answer; Atlas's planning and Vera's review can run on a hosted Nemotron-3-Ultra-550B
  while the workers stay on the laptop's Nemotron-Mini-4B (`clients/meterless.py: LaneEndpoint`). Every trace names the model and
  provider of every call.
- **NVIDIA Nemotron-Mini-4B made reliable by code around it.** A 4B model gets the numbers wrong, so the crew does not trust its
  arithmetic: in Euler's and Ada's answers a number near a calculator result is replaced by the calculator's value, any other number
  the evidence lacks is sent back by Vera's number rule (or, in the final answer, makes code assemble it), a number counts only as a tool's value at the precision it
  is written with, and code accepts a result only when the tool output proves it. On eight checkable goals, numbers graded exactly, it scores 8/8 in 30 s
  (`docs/BENCH.md`, rounds 26 and 27).

## Cursor (build)

Not used. The official rules (05) make Cursor optional: "Using Cursor for development is optional." The repository was written with
Claude Code on the team's Ubuntu workstation and a Windows laptop. Nothing in the repository depends on an editor; it opens in
Cursor like any other folder.
