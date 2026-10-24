# Meterless engine evidence

| Engine | Where it is used | Feature it powers | Passing test / evidence |
|---|---|---|---|
| **H-MEM** | `services/meterless-sidecar/server.ts` (`/ledger/*`), `core/inverse_core/ledger.py: SidecarLedger`, **`core/inverse_core/team/memory.py: TeamMemory`** (namespace `team:shared`) | Refuted hypotheses and trust rules for the physics agent; for the team, shared findings and refuted claims across experts and runs. An LLM claim cannot overwrite a validator's refutation. | `tests/test_integration.py::test_team_memory_on_hmem_survives_runs_and_breaks_without_engine` (refutation recalled in a new run; trust rule holds; stopping the sidecar breaks recall), `test_engine_honesty_stopping_sidecar_breaks_refuted_memory`, conformance 13/13 in `docs/evidence/hmem-conformance.txt` |
| **World Model** | `server.ts` (`/world/*`), `clients/world.py` | Shared equipment/dataset/hypothesis/validator_result entities, idempotent sync, used by the Reporter's "recalled from memory" evidence | `test_world_model_idempotent_and_shared_evidence`, conformance 8/8 in `docs/evidence/world-model-conformance.txt` |
| **Scout Intent** | not yet integrated | planned: routing gate and safety gate replacing `agents/guard.py` | waiting for the official engine prompt |

The old regex guard (`agents/guard.py`) is still the only injection filter. It is applied to maintenance text before the Research expert's rows reach a model.
