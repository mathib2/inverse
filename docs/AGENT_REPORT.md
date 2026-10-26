# How smart are the agents? Measured, rated, and what each must improve

Measured on 25 October 2026 on the workstation (Intel i5-6500, 4 cores, no GPU; Ollama 0.40; every lane on
`nemotron-mini`, Nemotron-Mini-4B-Instruct Q4_K_M). Two instruments:

- **The benchmark** (`scripts/bench.py`, `docs/BENCH.md`): eight whole missions with checkable answers, run eight times while the
  crew was being fixed. 64 missions, 391 model calls, every trace kept under `runs/`.
- **The probes** (`scripts/probe.py`, `docs/evidence/probe/`): each agent alone, on its own questions, scored by code. Accuracy is
  the share of right answers; honesty is the share of answers with no number from nowhere; efficiency is seconds per probe against
  a target; robustness is the share without errors, loops or unreadable replies. The mark is 0.45 accuracy + 0.2 honesty + 0.15
  efficiency + 0.2 robustness, out of 10. A probe is one expert run, one review or one plan: the mark is the agent's, not the crew's,
  and the Lead's retries do not rescue it.

The one-line verdict: **the rails are smart, the models are not.** Every mark above 7 comes from code that checks the model (the
calculator, the query guard, the scan, the plan guard, the reviewer's rules), and every failure below comes from the 4B model
doing what 4B models do: answering one half of a two-part question, naming a quantity instead of its value, accepting what it
should doubt, calling the same tool again. The crew got from 4 of 8 missions to 7 of 8, and from 588 s to 365 s for the eight,
by adding rules, not by making the model think harder.

## The marks

| agent | role | probes | mark | accuracy | honesty | efficiency | robustness | mean s per probe |
|---|---|---|---|---|---|---|---|---|
| Sentinel | code review | 3 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.6 |
| Scout | data lookups | 6 | 8.5 | 6.7 | 10.0 | 10.0 | 10.0 | 14.8 |
| Atlas | planning | 6 | 8.3 | 6.7 (raw) | 10.0 | 8.6 | 10.0 | 9.6 |
| Euler | reasoning | 6 | 8.1 | 6.7 | 8.3 | 9.4 | 10.0 | 22.2 |
| Vera | review | 7 | 8.1, then 9.4 | 5.7, then 8.6 | 10.0 | 10.0 | 10.0 | 5.0 |
| Ada | tools, multi-step | 4 | 6.6 | 2.5 | 10.0 | 10.0 | 10.0 | 23.4 |
| Forge | builds an agent | 1 | 5.5 | 0.0 | 10.0 | 10.0 | 10.0 | 78.0 |
| Warden | the watch loop | (record) | 7.5 | | | | | |

Vera was probed twice: before and after the two rules this measurement produced. Read the accuracy column, not the mark: honesty, efficiency and robustness are high because code enforces them (every number is
checked against the evidence, replies are capped, loops are cut), and they lift the mark of agents whose own judgement is middling.
The accuracy column is the model's intelligence as such: between 2.5 and 6.7 out of 10 for every agent that has to think, and 10 only where a rule answers.

## Each agent: what it got wrong, exactly

**Atlas (lead, plans the mission).** Raw plans right in 4 of 6. It sent a summary to Euler (a lookup of what the crew knows went to
the arithmetic agent) and put a lookup-plus-computation on Scout alone, with no step to compute. Across the 64 benchmark missions
the plan guard corrected 33 task routings; without it the crew failed on the same goals. In round 3 it gave a code review's first
step to Euler, who then "computed the cube root of 27"; in round 2 it sent the maintenance history to Euler. It does not split a
two-part question reliably: "which machines are in the registry, and which has no baseline" became two tasks about the baseline
in three rounds out of eight. Model calls are short (7.9 s mean, 49 tokens) and it never produced an unreadable plan.

**Vera (critic).** Right in 4 of 7 reviews. She accepted "P-104 has a mass of 12.5 kg" with a row that says 1.0, accepted "the
noise level is 0.01" when the task asked for the sampling rate, and accepted "six is 6, as the manual says" with no manual anywhere.
She caught the invented code finding and the correct arithmetic, and a rule caught "not available" while the rows held the value.
In the benchmark she accepted "0.01" as the sampling rate twice and Euler's "the cube root of 27 is 3" as a maintenance history.
Before her verdict became a checkable shape (quotes from the answer, kept only when the evidence does not cover them) she rejected
correct work on made-up reasons; now her false accepts are the problem, and two of the three probe misses are rules since this
measurement (a number from nowhere; an asked value the rows hold).

**Scout (research, read-only SQL).** Right in 4 of 6. Both misses are queries that answer half the question: "how many machines and
what are their ids" became `COUNT(*)` alone; "noise level and sampling rate of T200-DISP-1" became a filter on `quantity = 'v'`
(that sensor measures 'x'), so zero rows, honestly reported. In the benchmark, before the fixes, it selected one column when two
were asked (`SELECT sigma` for "sampling rate and noise level"), wrote `WHERE id = 1` and `WHERE baseline_dataset IS NULL` (the value
is the text 'none'), and added `LIMIT 1` to "list the records". Eight of its queries were rejected by the platform across the rounds.
It never invents a number: every one of its answers rests on rows, and it says so when a filter finds nothing.

**Euler (reasoning, calculator-checked).** Right in 4 of 6. The two misses were empty answers: for "12.5 kg times 9.81" and "0.05
up by 40 percent" it returned no answer text at all (a number or a null where a sentence was due); in a mission the Lead asks again,
alone it fails. It wrote `calc(mass_kg * 9.81)` with "mass_kg = 1.0" in front of it (now resolved by code). Given a task with no
numbers it invents arithmetic ("the cube root of 27 is not 3, but 3", "the factorial of 5 is 120, not 120!"), which is why the
plan guard no longer lets it see such tasks. It is the slowest agent per call (26.7 s mean, 95 s max in the benchmark) because it
writes long step lists; capped at five steps now.

**Ada (solver, tools and questions to others).** Right in 1 of 4, and the one pass is a summary whose words are poor. Asked for P-104's weight from the registry mass, she returned the literal answer "Error" after two calls. Asked for the samples across two datasets, she counted one (400, not 800). Asked to get the period of a 2 Hz oscillation from Euler, she answered 0.2 without a question on the bus. Her summary mixes real facts (T-200, 400, the registry rows) with an invented one ("no equipment with id 1 exists", an echo of her own failed query from an earlier mission, kept as a lesson). In the benchmark she called `memory({})` eight times in a row until the clock ran out (now cut by code), and wrote `WHERE id = 1` three times while the platform's error named the right column. She is the agent whose judgement matters most (tools, several steps, questions to teammates) and the weakest at it; her honesty mark is high only because the rails strip numbers the tools did not return.

**Sentinel (code review).** 3 of 3, but read the three: one is a rule (a clean scan is answered by code), one is a rule (an
exploit request is refused), and one is the model: given `zetaris.py` it named the SQL built from a string at line 44 and the line
checks out. Its weakness shows in the benchmark, not the probe: with no scan hit it invented "untrusted text reaching a model",
twice, until Vera stopped it; it scanned the whole repository when the task lost the path; its long reviews produced six
unreadable chunk replies in a row. All three are now rails. It is slow (33 s mean per call) and a bad review can run minutes.

**Forge (architect, builds a new agent).** 0 of 1, and never asked. Given "what does 12.5 kg weigh on the Moon, where gravity is 1.62; we have no converter", Atlas planned Scout then Euler and never named the architect, so Forge's design-build-test loop ran only in the test suite today (where it works, scripted). The 4B planner does not recognise a missing capability; it stretches the agents it has. The mission then failed on a rule of this measurement's own making: Scout used the goal's 1.62 and the new number rule, which counted only tool evidence, sent it back; the task's own numbers now count as evidence.

**Warden (the watch loop; no model of its own).** 22 missions started on its own: 15 done, 3 failed, 4 interrupted by deploys and
re-queued once as designed; 71 cycles without a crash; a queued goal picked up within a minute. Its weakness is inherited: a
mission it starts is only as good as the planner, and it runs standing missions whether or not anything changed.

## What they must improve, in order

Refreshed on 26 October after the fourth batch (probes `probe5` before, `ten2` after, in `docs/evidence/probe/`). Each item is still
open, names the agent, points at one region, and is measured by one probe. This list is Tinker's backlog: `scripts/tinker.py` reads
the bold text of each item, `REGIONS` maps a phrase of it to the file and the lines, and a file in `backlog_tests/` named after the
item defines done.

1. **Atlas must route right in the raw plan**: the probe sends plain arithmetic, a summary and a lookup-then-compute to Scout alone
   (3 of 6 right before the guard repairs them). The routing rules are in `PLAN_SYSTEM` in `core/inverse_core/team/lead.py`; the
   model does not follow them. What is left is the model's judgement: a measured trial of structured outputs or a different
   planner model, by a person. Measured by the Atlas probe with the guard bypassed.
2. **Forge's template expert must get the Moon question**: the plan sends "What does a 12.5 kg mass weigh on the Moon ... we have
   no converter" to Scout, who reports the registry mass, and the forged expert with its given values never runs. Where:
   `_guard` in `core/inverse_core/team/lead.py` (the `LACK_WORDS` branch must make the forged expert's task the one that answers).
   Measured by the Forge probe: 20.25 N; today the answer is Scout's rows.
3. **Ada must compute a weight from the registry mass she fetched**: the mass 1.0 kg is in her evidence and she answered 981.0 N
   once in `ten2` (9.81 N in `probe5`). Where: the calculator nudge in `_loop`, `core/inverse_core/team/custom.py`, which could
   name the fetched value in its example. Measured by her probe: 9.81.

Done since the first list, all by code and all recorded in `docs/BENCH.md`: Vera's three rules and her checkable verdict; the routing
guard and, from round 11, a one-task plan that carries the goal verbatim, placeholder tasks refused, arithmetic to Euler, a lookup
that feeds a computation rewritten as a lookup; Scout's whole goal, columns, ids, sensor pin, errors as evidence, row values that
ride along and replace numbers the rows lack, and (26 Oct) the unasked quantity filter dropped; Euler's empty answer re-asked, names
resolved before the calc, and (26 Oct) a number in prose sent to the repair turn; Ada's facts, consultations and memory fetched by
code, a bare word refused, a computation ended with the calculator, a repeated tool call ended, a doubted digest read out of the
memory, and (26 Oct) a total across datasets summed by code; Forge planned in when the goal says the crew lacks something, built by
rule when the architect loops, and (26 Oct) given the goal's constants; Sentinel's clean scan answered by code and (26 Oct) the lines
around each hit read by code.

For people, not for Tinker: Ollama structured outputs (`json_schema`) for every JSON-returning call, a measured trial of a different
planner model against the Atlas probe, and a second local model on Vera's lane. Each touches the model server or the lane layout,
which the loop must not change.

## After the fourth batch (26 October)

| agent | probe5, before | ten2, after | what moved it | what still fails |
|---|---|---|---|---|
| Euler | 5.9 (2 of 6) | 9.4 (6 of 6) | the KNOWN LIMITATIONS note was taken out of his prompt (with it 6.9, without it 9.4, same code); a number in prose goes to the repair turn | one unverified number on the cube root |
| Ada | 7.8 (2 of 4) | 8.4 (3 of 4) | the total across datasets summed by code (800); the calculator hint no longer multiplies 104 from P-104 | the registry weight once (981.0) |
| Atlas | 7.7 (3 of 6) | 7.8 (3 of 6) | routing rules in the prompt; the model ignores them | arithmetic, a summary and a lookup-then-compute sent to Scout; the guard repairs all three in missions |
| Scout | 10.0 | 9.9 | the unasked quantity filter dropped | nothing; a slower probe |
| Vera | 10.0 | 10.0 | unchanged | nothing |
| Sentinel | 10.0 | 10.0 | reads around each hit by code | nothing |
| Forge | 5.2 (0 of 1) | 5.5 (0 of 1) | given values in the template expert | the Moon question goes to Scout, never to the forged expert |

The lesson of this batch: telling a 4B model its own flaws in its system prompt made it worse, measured twice on the same code; the
awareness lives on the Crew panel and in Tinker's backlog instead, where it does work.

## After three batches of fixes (the same evening)

Every item in the list above that could be a rule was made one, in three batches, each measured by the same probes and one
benchmark round (`docs/evidence/probe/probe3.json`, `probe4.json`; `docs/BENCH.md` rounds 9 and 10).

| agent | before | after | what moved it | what still fails |
|---|---|---|---|---|
| Scout | 8.5 (acc 6.7) | 10.0 (acc 10) | the ids are listed when the task says which; a named sensor is selected by its id | nothing in the probes |
| Vera | 8.1 (acc 5.7) | 10.0 (acc 10) | a number from nowhere, an asked value left out, a phrase from nowhere: all rules | nothing in the probes; she is now mostly rules with a model behind them |
| Sentinel | 10.0 | 10.0 | unchanged | one of three probes exercises the model |
| Euler | 8.1 (acc 6.7) | 9.5 (acc 10) | an empty answer is asked once more; names in a calc resolved from the context | one unverified number on the cube root (a text step) |
| Ada | 6.6 (acc 2.5) | 8.9 (acc 7.5) | facts and consultations fetched by code; a bare word is not an answer; a computation ends with the calculator | the total across two datasets: she had both counts and answered 9.81 |
| Atlas | 8.3 (raw 4/6) | 8.3 (raw 4/6) | nothing on the raw planner; the guard makes missions 8 of 8 right-expert | a summary to Euler, a computation to Scout alone: the guard's two most frequent repairs |
| Forge | 5.5 (never planned in) | 5.5 (planned in, built by rule) | the guard plans it in; when it loops, a rule builds the expert from a template and the work goes on | the architect's own loop still fails; the template expert answered the Earth weight, not the Moon's |

The benchmark went from 7 of 8 (rounds 7 to 9) to **8 of 8, all clean, in 405 s** (round 10): the two-part registry question
passed once Scout carried the whole goal and listed the ids. One run is one run; the next failure will show up in a trace.

What is left is the model's own judgement, which no rule reaches: Atlas routing a summary to the arithmetic agent in its raw
plan, Ada adding two numbers she has in front of her, Forge designing an expert without looping. Those three are where a
better 4B model (the newer Nemotron, measured by this same probe set) or structured outputs would pay, and nothing else would.

## How to re-measure

```bash
~/.local/bin/inverse-watch stop
PYTHONPATH=core .venv/bin/python scripts/warmup.py
PYTHONPATH=core .venv/bin/python scripts/probe.py --label after      # every agent; --only euler,vera for two
PYTHONPATH=core .venv/bin/python scripts/bench.py --label after
~/.local/bin/inverse-watch start
```

Compare `docs/evidence/probe/before.json` with `after.json` per agent: a change is real when the same probe moves the same way
twice. The probes are deliberately small and checkable; add one whenever a mission trace shows a new way to be wrong.
