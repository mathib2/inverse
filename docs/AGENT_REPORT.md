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

1. **Vera must doubt numbers and scope by rule, not by taste.** Two rules landed from this measurement (a number from nowhere; an
   asked value left out). Still missing: an unsupported phrase in an otherwise grounded answer ("as the manual says" was accepted twice); the next step is a structured-output schema for her verdict (Ollama `json_schema`) and a second local model on her lane
   (`LANE_CRITIC=qwen2.5:3b-instruct`), measured by her probe accuracy, not by mission time.
2. **Atlas must stop misrouting**: the guard fixes four cases; the raw planner should get them right. Give the planner three worked
   plans of the crew's own goal types in its stable prefix (the plan is a schema, not prose, so copying is harmless here, unlike
   the experts) and measure raw routing with the Atlas probe before and after.
3. **Scout must answer the whole question**: every column the task names in one query, no filter the task did not ask for, and the
   ids when the task says "which". `complete_columns` and `_facts` do it by code for known concepts; the remaining misses are
   filters (`quantity = 'v'`) and a COUNT where a list was asked. A deterministic "list columns when the task says which/what ids"
   rule is the next fix.
4. **Euler must always return a sentence.** Enforce by schema (`answer` a non-empty string) and resolve names from the context before
   computing (done). Then the five-step cap should become a two-call budget: one plan of steps, one check.
5. **Ada must finish what she starts.** Three rules would fix three of her four misses: a final answer that is a bare word such as "Error" or a number alone is not an answer (ask again, by code); when the task names two things to count or add, a plan of two tool calls and one `calc` is written by code before the model speaks (the solver's version of Scout's `complete_columns`); and `ask_expert` becomes a required step, traced, when the task says "ask the reasoning expert". Lessons from her own failed queries must not be fed back to her as facts (the `id = 1` echo).
6. **Forge must be reachable.** A deterministic trigger: when the goal says the crew lacks something ("we have no", "no converter", "nobody can") or names a unit or domain no expert's role mentions, the plan guard adds an architect task first. Then the design-build-test loop gets its own probe with a budget, measured by whether the created expert's task is accepted.
7. **Sentinel must read before it claims**: with hits, read the lines around each hit before naming a finding (the loop allows it,
   the prompt should require it); with no hits, code already answers. Cap the whole review at ninety seconds of model time.
8. **All of them: fewer, shorter calls.** The three numbers that govern this machine are 53 prompt tokens per second, 10 generated
   tokens per second and a warm prefix in under a second. Every change that removed a call or a hundred generated tokens showed in
   the benchmark; nothing that touched the server did. The next lever is Ollama structured outputs for every JSON-returning call
   (no unreadable replies, no re-asks), then a measured trial of `nemotron-3-nano:4b` (pulled, never loaded) against this same
   probe set, which is the only fair way to decide whether a newer Nemotron is smarter on this CPU.

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
