-- Run one statement at a time via scripts/admin/zsql.py (all verified working 2026-10-23).
CREATE LIGHTNING DATABASE OBS_REST DESCRIBE BY "Observation service REST source";
CREATE LIGHTNING REST TABLE p104_current FROM OBS_REST REQUEST(endpoint "http://obs-service:8000/datasets/p104-current/samples", method "get", response_type "json", http_encoding "URLENCODED") HEADER () BODY ();
CACHE TABLE obs_rest.p104_current;
CREATE SCHEMASTORE CONTAINER obs;
CREATE SCHEMASTORE VIEW p104_current_samples WITH CONTAINER obs AS SELECT dataset_id, s.t AS t, s.x AS x, s.v AS v FROM obs_rest.p104_current LATERAL VIEW explode(samples) AS s;
