# Evidence

Data the crew produced, kept as it was written. Code reads some of these folders, so their paths do not change.

| folder | what it holds | written by | read by |
|---|---|---|---|
| `probe/` | Each agent's probe run: every question, the answer, the checks and the mark out of ten. The newest full file is the baseline. | `scripts/measure/probe.py` | `core/inverse_core/team/limits.py`, `scripts/tinker.py` |
| `bench/` | Benchmark rounds: the eight goals, pass or fail, seconds, model calls and tokens per case. | `scripts/measure/bench.py` | people (`docs/BENCH.md`) |
| `engineer/` | Models measured as Tinker's engineer on four small edits and on the real backlog. | `scripts/measure/engineer_eval.py` | people (`docs/TINKER.md`) |
| `missions/` | Two complete missions from 24 October: plan, trace, the agents' messages and the answer. | Warden | people, the hackathon evidence |
| `conformance/` | The three Meterless engines' conformance runs (H-MEM, World Model, Markovian). | the sidecar's setup | people, the hackathon evidence |
