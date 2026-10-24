# Onboarding a machine (and what a real plant would change)

INVERSE knows two machines today (P-104, T-200) and three datasets. They are configured in three places; adding a machine means touching all three. This is the honest state of the data path, and the shortest route to a real one.

## The three places

| Place | What it holds | File |
|---|---|---|
| The data source | the sample generators, the equipment registry rows (id, name, mass), the sensor specs (quantity, unit, σ, sampling rate), the maintenance notes | `services/obs-service/app.py` |
| Zetaris | one REST table per dataset, the cache, the schemastore views (`obs.*_samples`) | `zetaris/sql/01_*.sql`, `zetaris/sql/02_obs_tables_and_views.sql`, applied by `scripts/setup_zetaris.py` |
| The client | the dataset id → view mapping | `core/inverse_core/clients/zetaris.py: SAMPLE_VIEWS` |

Steps for a new machine `X-300` with a release-test record:

1. `obs-service`: add the equipment row (`X-300`, name, `mass_kg` or `NULL` if unknown), its `x` and `v` sensor rows with σ and units, a dataset id (`x300-current`, and `x300-baseline` if a previous test exists), and the samples endpoint that serves them. Rebuild: `docker compose up -d --build` in `services/obs-service`.
2. Zetaris: add a REST table for each new dataset (copy `01_obs_p104_current.sql`), register the view in `02_obs_tables_and_views.sql`, run `scripts/setup_zetaris.py`, then `UNCACHE TABLE` / `CACHE TABLE` for the new tables.
3. Client: add `"x300-current": "obs.x300_current_samples"` (and the baseline) to `SAMPLE_VIEWS`.
4. Ask: "Machine X-300 was reassembled. What governs its vibration, and has it worn?" The planner recognises any equipment id present in the registry.

## What the method needs from a plant

- A **release (bump) test**: free decay from a known initial displacement, with displacement and velocity channels sampled fast enough to resolve the oscillation (the demo uses 100 Hz for a 1.6 Hz mode). Operational, forced vibration is not supported yet.
- The sensor **σ and units** in the registry: they set the likelihood and the units check; an understated σ widens the intervals rather than breaking the fit (Birge scaling).
- The **mass** in the registry, or a forced-response test when it is unknown (the agent will ask for it).
- A previous test's result in H-MEM to flag wear against; the first run on a machine stores the baseline.

## What would make it real (not in this version)

- An ingestion path for the forced-response measurement the agent recommends after a refusal (today `u` is always `None` in the client), closing the refuse → measure → recover loop.
- A second physical family (the `software` adapter is a stub), so the "domain-agnostic core" is more than a name.
- A real sensor recording with its own noise, to measure the intervals against something that is not the generator.
