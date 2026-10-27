# The benchmark: how the crew is tested, and what changed

`scripts/measure/bench.py` runs eight checkable goals (`scripts/measure/bench_cases.yaml`) through the crew exactly as the crew page would, and records
for each: whether every expected item is in the final answer (a number as the expected value rounded to the precision the answer writes it with, text as a substring; until
27 October a number within 1 % counted, which passed 122.55 for 122.625), whether at least one
task was accepted, seconds, model calls, prompt and completion tokens, the reviewer's verdicts, re-asks and unreadable replies.
Results land in `docs/evidence/bench/<label>.json`; `--compare a.json b.json` prints two runs side by side.

```bash
~/.local/bin/inverse-watch stop                     # Warden shares the CPU: pause it for a clean measurement
PYTHONPATH=core .venv/bin/python scripts/measure/warmup.py  # one two-token request per agent prefix, so the server's prefix cache is warm
PYTHONPATH=core .venv/bin/python scripts/measure/bench.py --label mine [--only sensor,weight] [--parallel 1] [--collaborate on]
PYTHONPATH=core .venv/bin/python scripts/measure/bench.py --compare docs/evidence/bench/baseline.json docs/evidence/bench/mine.json
~/.local/bin/inverse-watch start
```

The eight goals: an arithmetic derivation (Euler), four data lookups of growing difficulty (Scout: the registry, sample counts,
one sensor's two numbers, the maintenance history with dates), a lookup-plus-computation (Scout then Euler), a review of one
file of our own code (Sentinel), and a summary of what the crew knows (Ada with the shared memory). Every expected value comes
from the synthetic data (`data/README.md`) or from arithmetic, so numbers must be the right value at their written precision. Text items are substrings: the registry case passes when the
answer names both machines (in rounds 23 to 27 it led with P-104, the wrong machine, and passed on the rows it quoted), and the
summary case has no expected item and passes when a task is accepted.

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
| 13 | 7/8 | 7 | 496 | 4.8 | a summary the model doubts, or leaves empty, is read out of the memory by code (`summary_by_code`); the digest fired, and the number rule refused it: a finding cut at "2026-09" read as minus nine on the evidence side |
| 14 | 8/8 | 8 | 548 | 5.5 | a hyphen after a digit is a separator on the evidence side too, and evidence numbers carry no sign, as claim numbers never did; the second fully passing round, on the deployed code (b2250af), with Tinker and Warden stopped |
| 15 | 7/8 | 7 | 693 | 5.1 | the fourth batch of agent rules (26 Oct, PR #52), run cold: the registry case needed 12 calls and left P-104 out; the memory digest alone took 282 s |
| 16 | 7/8 | 7 | 216 | 2.3 | plain goals planned by rule (no planner call), answers the tool results prove accepted by code (no critic call), the digest read out of the memory (no model call): 27 s per case; the maintenance case lost a row to a LIMIT 1 the model wrote |
| 17 | **8/8** | 8 | **222** | 2.4 | a task that asks for the records gets every row; a hundredfold number is grounded only as a percentage. 28 s per case against 68 s in round 14: 59 percent faster, nothing lost |
| 18 | 7/8 | 7 | 39 | 2.8 | Nightshift on the laptop GPU (26 Oct night, `MODEL_PROVIDER=nightshift`, the same Nemotron-Mini-4B through a Nightshift lane, about 59 tokens a second): 5 s per case; the registry case lost P-104 to a WHERE the model wrote for the "which of them" half |
| 19 | **8/8** | 8 | **40** | 2.8 | a task that asks for the whole list "and which of them" gets every row (`whole_list`); 5 s per case against 28 s in round 17: the deterministic layer keeps the result, the GPU makes it five times faster |
| 20-22 | 6/8, 6/8, 7/8 | | 39-69 | 2.4-3.5 | the same code as round 19 a few hours later: the arithmetic and weight cases failed ("3", "123.0", "9810"). Euler was shown its expert's three newest reviewer lessons whatever the task, and the newest one by then was about a cube root ("The cube root of 27 is not 3, but 3") |
| 23, 24 | **8/8**, **8/8** | 8 | **32**, **32** | 2.5 | a lesson reaches an expert only for a task like the one it came from; the final write-up's numbers are checked like every task's; the days between two dates are counted by code |
| 25, 26 | 7/8, **8/8** | 7, 8 | 36, 30 | 2.6, 2.5 | the exact grader (27 Oct): a number counts only as a tool's value rounded to its own precision, and an answer states the calculator's value, not the model's arithmetic. Re-graded this way, rounds 17, 19, 23 and 24 are 7/8 each (round 18 is 6/8; rounds 10 and 14 stay 8/8): both answered the arithmetic case 122.55 for 12.5 x 9.81 = 122.625, which the 1 % tolerance had passed. Rounds 25 and 26 answered 122.625 both times. Round 25 lost the weight case to the planner, which sent the goal to Euler without the lookup of the mass; Vera refused the 981000000000 he wrote, and his next reply was not JSON |
| 27 | **8/8** | 8 | 30 | 2.5 | Atlas plans and writes up on his own lane, `plan`, which follows `LANE_DEEP` here (the same Nemotron-Mini-4B on the laptop): nothing lost; the switch to a hosted Ultra-550B for `plan` and `critic` is one `.env` line each and is not measured yet |
| 28-31 | 7/8, 7/8, 6/8, 6/8 | | 20-32 | 2.3-3.3 | worked examples in the agents' prompts (27 Oct, branch `crew/worked-examples`, not merged). Rounds 28 and 29 with examples for Atlas too: the planner copied "(quantity 'v')" from his example into a mass lookup and Scout queried a column that does not exist, so the weight case failed both times. Rounds 30 and 31 without Atlas's: Euler answered the weight case "not computable", after his example of a question without the data, and computed 1200.25 for 12.5 x 9.81 in the arithmetic case. Few-shot examples make Nemotron-Mini-4B copy them, as the research pass had found |
| 34, 35 | 7/8, 7/8 | 7, 7 | 41, 41 | 3.0 | a reply cut before its closing brackets is closed and read (27 Oct): Scout's query reply had stopped one brace short, so two fresh P-104 maintenance reviews on the live crew failed their mass lookup three times each. With the cut reply read, Scout's three-query reply (the mass, and two sigma values nobody asked for) reached Euler, who returned his steps without an answer; the re-ask for one sentence got just the sentence, with no JSON around it, and the weight case failed |
| 36, 37 | **8/8**, **8/8** | 8, 8 | **30**, **30** | 2.5 | that sentence is the answer: an empty answer re-asked as one sentence may come back as just the sentence, and Vera still checks its number against the calculator's. The full P-104 maintenance review on the same code: four tasks accepted on the first attempt, three of them by code, 16.4 s and 13 model calls |
| nano | stopped | | | | `nemotron-3-nano:4b` on every lane (26 Oct): the arithmetic case took 130 s against 31 s, so the round was stopped; a newer 4B is not faster on this CPU |
| hosted | 7/8 | 7 | 893 | 7.4 | the sponsor's hosted Nemotron through the tunnel (26 Oct, `MODEL_PROVIDER=nightshift`, served by `nemotron-3-ultra-550b`): a 40-token request answers in 2 s, but the whole benchmark is slower than local round 14 because the big model writes five times more (146k prompt + 14.8k completion tokens against 37k + 3k) and the pipeline makes more calls; the code case alone took 409 s and 15 calls; the summary case failed by rule twice. Not adopted |

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

## Where the time went, and where it does not go any more

Round 15, read from its traces: the planner's call cost 6 to 12 s on every goal, Vera's review 5 to 10 s on every task, and
Ada's two calls on a 3,600-token memory dump 254 s for the digest. Round 17 removes them where nothing is lost: a plain lookup,
an arithmetic with its numbers in the goal, a summary or a review of a named path is planned by rule and then gets the same
guard every plan gets; an answer whose every number is in its own rows or calculator results, with nothing hedged or unchecked,
is accepted by code; a digest is read out of the memory by code. The model still plans anything else, still judges prose and
code findings, and the probes for Atlas and Vera switch both shortcuts off so they keep measuring the model.

## What the hardware allows

The workstation is a Dell OptiPlex 7040 mini tower: an i5-6500 with four cores and no graphics card, 31 GB of memory. On it the
crew's 4B model writes 6 to 10 tokens a second and reads a prompt at 30 to 110 tokens a second. That is the memory bus, not the
code: every generated token reads the whole 2.7 GB model, and two channels of DDR4 move about 34 GB a second, so the ceiling is
about 12 tokens a second. After round 17 a goal costs 2.4 model calls, so what is left of a mission's time is the model writing.

Three things were measured on 26 October and fixed in code: the loops took turns badly (a Tinker cycle ran beside a person's or
Warden's mission and the crew's model fell to 6.7 tokens a second; now every model call waits its turn, `team/gate.py`), the 7B
coder stayed in memory for a day (the machine was swapping with 27.5 of 31 GB used; Tinker now unloads it after each use), and the
crew's own model process had grown to 12 GB over three days (freeing and reloading it took memory use from 26 GB to 7 GB).

The next step is hardware. The mini tower has one full-length PCIe x16 slot; a graphics card that draws all its power from the slot
(75 W or less, so no change of power supply), such as an RTX 3050 6 GB or an RTX A2000, moves 168 to 288 GB a second: about five to
eight times faster writing and ten to twenty times faster reading, which takes a mission from tens of seconds to a few. Ollama uses
the card on its own once the container is started with GPU access (the NVIDIA container toolkit and `--gpus all`, one time, with
sudo). The other routes measured here: the sponsor's hosted Nemotron answers a short call in two seconds but is metered, which the
owner ruled out on 24 October, and a newer local 4B was four times slower on this processor.

## Bigger is not faster here

Two measurements on 26 October settle the "use something bigger" question for this machine. A newer 4B (`nemotron-3-nano`) is four
times slower per case on the CPU. The sponsor's hosted 550B answers a short request in two seconds, yet the full benchmark through it
took 893 s against 548 s locally: the hosted model generates far more text per call and the mission makes more calls, and the
benchmark measures missions, not tokens. The crew stays on the local 4B; the levers that moved the benchmark were always fewer calls
and shorter replies, and they would apply to a hosted model too.

## What the research said, and what was kept

A 23-agent research pass (web sources on Ollama internals, the Nemotron-Mini card, small-model agent prompting, evaluation
practice; two code audits; a synthesis; two skeptical lenses per item) produced the plan behind rounds 5 to 7. Kept: fewer
calls and shorter replies (each 100 generated tokens is about 10 s), byte-stable prefixes, per-role caps inside the 4,096-token
window, deterministic checks before the model, a reject treated as a strong revise, the warm-up. Rejected with reasons, and
recorded here so nobody retries them: more Ollama parallel slots (no cache gain on 4 cores), KV-cache quantization or flash
attention for speed (no gain on CPU), a different quantization (slower or worse), speculative decoding (not available for this
model), few-shot examples in the small-model prompts (they copy the example; measured again on 27 October, rounds 28 to 31), moving the second model under the planner or the
composer (breaks the Nemotron default), and swapping the default model two days before the demo without a full bench pass.
