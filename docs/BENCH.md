# The benchmark: how the crew is tested, and what changed

`scripts/bench.py` runs eight checkable goals (`bench/cases.yaml`) through the crew exactly as the crew page would, and records
for each: whether every expected item is in the final answer (a number within 1 %, text as a substring), whether at least one
task was accepted, seconds, model calls, prompt and completion tokens, the reviewer's verdicts, re-asks and unreadable replies.
Results land in `docs/evidence/bench/<label>.json`; `--compare a.json b.json` prints two runs side by side.

```bash
~/.local/bin/inverse-watch stop                     # Warden shares the CPU: pause it for a clean measurement
PYTHONPATH=core .venv/bin/python scripts/warmup.py  # one two-token request per agent prefix, so the server's prefix cache is warm
PYTHONPATH=core .venv/bin/python scripts/bench.py --label mine [--only sensor,weight] [--parallel 1] [--collaborate on]
PYTHONPATH=core .venv/bin/python scripts/bench.py --compare docs/evidence/bench/baseline.json docs/evidence/bench/mine.json
~/.local/bin/inverse-watch start
```

The eight goals: an arithmetic derivation (Euler), four data lookups of growing difficulty (Scout: the registry, sample counts,
one sensor's two numbers, the maintenance history with dates), a lookup-plus-computation (Scout then Euler), a review of one
file of our own code (Sentinel), and a summary of what the crew knows (Ada with the shared memory). Every expected value comes
from the synthetic data (`data/README.md`) or from arithmetic, so a pass is a right answer, not a plausible one.

## What a run measures, and what it cannot

One run per case is a noisy signal: the same code gives different plans on different runs, because the planner is a 4B model
at temperature 0 whose output still depends on the prefix cache state and on what shared memory holds. Read a round against the
previous ones, not alone; a change is real when it moves the same case the same way twice, or when the trace shows the mechanism.
The traces under `runs/<ts>/` are the ground truth: every failed case in the rounds below was diagnosed from its trace, and the
fix was aimed at the mechanism, by code where code can decide.

The machine: one Intel i5-6500 (4 cores, no GPU), Ollama 0.40 in Docker, `nemotron-mini` (Nemotron-Mini-4B-Instruct, Q4_K_M).
Measured raw speed: prompt processing 53 tokens/s, generation 9-11 tokens/s; an identical prompt prefix is served from the cache
in under a second. Everything below follows from those three numbers: fewer calls, fewer generated tokens, stable prefixes.

## Rounds (25 October 2026)

| round | pass | clean | total s | calls / case | what changed before it |
|---|---|---|---|---|---|
| baseline | 4/8 | 4 | 588 | 6.1 | the code as merged that morning (`m4-sindyc` 42dd4ea) |
| 1 | 3/8 | 3 | 584 | 6.5 | reply caps per call, one shared proposal sentence, a value-annotated SQL schema with examples, query errors as evidence, the reviewer judges quotes against evidence values |
| 2 | 4/8 | 4 | 687 | 6.8 | research prompt asks for every column the task names; a worked tool call in the solver prompt; summaries routed to the solver |
| 3 | 3/8 | 3 | 824 | 6.4 | one accepted result is the answer by code; Scout answers in one conversation; shorter steps; smaller tool results |
| 4 | 4/8 | 4 | 669 | 5.9 | a routing guard on every model plan; "not available" with rows present is sent back; a missing column the task asks for is added to the query |
| 5 | 5/8 | 4 | 781 | 6.4 | values the answer leaves out ride along from the rows; Euler only for arithmetic; Sentinel gets the path; chunked reviews in JSON |
| 6 | 6/8 | 5 | 903 | 6.4 | a reviewer's reject retried once; two short results composed by code; prompts kept inside the 4K window; warm-up (the summary case alone took 402 s: Ada looped on tools without calling the memory) |
| 7 | 7/8 | 7 | 365 | 4.5 | a calc that names a quantity resolved from the context; a clean scan answered by code; summaries start from the shared memory |
| 8 | 7/8 | 7 | 383 | 4.5 | a repeated tool call ends the loop by code (the same seven passes twice in a row: the gain holds; the registry case is the known remaining failure) |
| 9 | 7/8 | 7 | 513 | 4.6 | the second batch from the agent report: Ada's facts and consultations by code, a bare word is not an answer, Forge planned in when the goal says the crew lacks something, a phrase from nowhere sent back (the summary case took 242 s: Ada writes long from a full memory) |
| 10 | 8/8 | 8 | 405 | 4.6 | the third batch: a computation ends with the calculator, a named sensor selected by its id, the ids listed when the task says which, the expert the architect did not build is built by rule; the first fully passing round |
| 11 | 6/8 | 6 | 794 | 6.1 | the same mission code as round 10 plus the autonomy work, run at 21:49 with Tinker and Warden stopped: the arithmetic case lost to a plan whose only task was the schema's example text ("Write the instruction for the task 'T1'"), the weight case to Scout computing (10.0 N from 1.0 kg) and being refused three times; the summary case took 256 s |
| 12 | 7/8 | 7 | 507 | 4.8 | a one-task plan carries the goal verbatim, placeholder tasks are refused, plain arithmetic goes to Euler, a lookup that feeds a computation is rewritten as a lookup, and numbers Scout states that the rows do not contain are replaced by the row values (the arithmetic case: 37 s and 3 calls; the summary case failed: Ada reported zero confidence three times on a memory of ten refuted findings) |
| 13 | ROUND13_PASS | ROUND13_CLEAN | ROUND13_SECONDS | ROUND13_CALLS | a summary the model doubts, or leaves empty, is read out of the memory by code (`summary_by_code`) |

The failures that remained longest, and what decided them:

- **Scout selected one column when the task asked for two** ("sampling rate and noise level" became `SELECT sigma`): prompt
  wording did not fix it; `complete_columns` adds the columns the task's words call for, and `_facts` appends the row values the
  answer left out, cited. Both are code.
- **The planner sent lookups, summaries and a code review's first step to Euler**, who then invented arithmetic ("the cube root
  of 27"): `Lead._guard` reroutes by rule (data words to Scout, a summary to Ada with the memory tool, code words to Sentinel, a
  computation after lookups to Euler) and traces every change as `plan_guard`.
- **The reviewer accepted "not available" while the rows held the value**: a deterministic rule now sends that back with the rows.
- **Sentinel with nothing to triage invented a finding, then scanned the whole repository for 173 s**: a clean scan on the named
  path is answered by code; the path named in the goal is carried into the task.
- **Euler wrote `calc(mass_kg * 9.81)`** with `mass_kg = 1.0` in its context and failed three times: `resolve` substitutes the
  value before the calculator runs.
- **Atlas copied the example text as the task** and **Scout computed when its task said "compute"** (round 11): a one-task plan now
  carries the goal verbatim (a paraphrase by a 4B planner can only drop a detail or be the example), the placeholder patterns are
  refused so the planner is re-asked, plain arithmetic with nothing to look up goes to Euler, a lookup that feeds a computation is
  rewritten as "look up the values; the computation is another task's", and when Scout's answer states numbers the rows do not
  contain, the code-made row values become the answer (`scout_numbers_dropped`): Scout and Vera agree by construction instead of
  after three refusals.

## What the research said, and what was kept

A 23-agent research pass (web sources on Ollama internals, the Nemotron-Mini card, small-model agent prompting, evaluation
practice; two code audits; a synthesis; two skeptical lenses per item) produced the plan behind rounds 5 to 7. Kept: fewer
calls and shorter replies (each 100 generated tokens is about 10 s), byte-stable prefixes, per-role caps inside the 4,096-token
window, deterministic checks before the model, a reject treated as a strong revise, the warm-up. Rejected with reasons, and
recorded here so nobody retries them: more Ollama parallel slots (no cache gain on 4 cores), KV-cache quantization or flash
attention for speed (no gain on CPU), a different quantization (slower or worse), speculative decoding (not available for this
model), few-shot examples in the small-model prompts (they copy the example), moving the second model under the planner or the
composer (breaks the Nemotron default), and swapping the default model two days before the demo without a full bench pass.
