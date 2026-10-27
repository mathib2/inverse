# Changelog

> Entries before 2026-10-24 describe features that were removed when the entry was refocused on the crew (the physics subsystem, the
> Physics bench page, the evaluation report); they live in the git history before commit `db408c1`.

## The audit before the recording (2026-10-27, afternoon)
- The example questions on the chat page start a mission again: clicking one had raised StreamlitWidgetAlreadyInstantiatedError, started nothing and left the pill stuck (`ui/chat_ui.py: _take_example`). The live app shows an error's type only, never a traceback with file paths.
- A goal with "<" and ">" in it (t < 1 ... t >= 3) is no longer refused as a copied placeholder. The SQL guard refuses backtick-quoted and try_ JVM built-ins; the web tools never read the tailnet's addresses (<tailnet-ip>/10). A replay opened from Warden or Recent shows its own duration. The Alerts panel no longer prints the ntfy topic. The publish script refuses to run after the deadline.
- The headline is honest: 8/8 with every number exact, 7/8 read strictly. The crew against one agent holding all of it, on 13 reverse-engineering tasks: 2 of 26 against 0 (`docs/BENCH.md`). The public repository is public (it was made so on 27 Oct).
- Tests: 214; CI runs 208.

## The page polished, the core tidied (2026-10-27, morning)
- The chat page shows a run panel while a mission runs and under Steps afterwards (`ui/run_ui.py`): a status timeline (planned, working, reviewing, answered) and one card per task with its agent, attempts and tool calls, read from the trace the page already collects; the eight-line bullet list in the bubble goes. One toast when the mission ends, none when a saved run is opened. Stop stays where it was.
- The nine artifact pills sit in two labelled groups, "This answer" (Answer, Evidence, Who did what, Steps) and "The crew" (Live, Crew, Warden, Council, Alerts), instead of three ragged rows; a fresh page shows a dashed empty state that points to the three example questions. The wording is in `ui/plain.py` and pinned by `tests/test_ui_plain.py`.
- One header row: brand, tagline, the three status badges on one line on the right. Connections in the sidebar is a one-line status with the detail behind an expander, so Recent is visible without scrolling. The page's fade-in and the decorative blur are toned down. Under 820 px the artifact panel comes before the thread, so an answer is not lost below the fold.
- In separate pull requests: lint (imports sorted, unused imports and stale `noqa` comments dropped, regex flags spelled out, no behaviour change; `ruff.toml` enables only what the code already passes and CI runs `ruff check` with a pinned version, so it cannot go red on the team); seven files opened without `with` now use a context manager; a root `AGENTS.md` that says where the code is, the branch and pull-request rule, how to run and test, the wording rule, and what never to push.
- Tests: 208; CI runs 202 and skips the 6 that need live services.

## Answers in plain words (2026-10-27)
- Scout says its rows in sentences, the id first, every value and its citation kept (`team/research.py: rows_in_words`, `reword_rows`): "P-104 has the baseline dataset p104-baseline [Q1]. T-200 has no baseline dataset [Q1]." where it said "Rows: equipment_id = P-104, baseline_dataset = p104-baseline [Q1]; equipment_id = T-200, baseline_dataset = none [Q1]". A JSON array of records the model pastes into its answer is said the same way, a number as the model wrote it; a bare number or id the model answers is not repeated in front of the sentences that hold it. Euler reads a value out of Scout's sentence as he read it out of `mass_kg = 1.0`.
- The answer code assembles is paragraphs, not labelled forms (`team/words.py`, `Lead.compose`, trace field `by_code`): "The mass is 1.0 kg [Q1]. [T1.E1]" and then "The weight of P-104 is 9.81 newtons. [T2.E1]" where it read "**T1 (research)**: Rows: mass_kg = 1.0 [Q1]; ..." and "**T2 (reasoning)**: ...". The writer's own text is untouched.
- The summary of what the crew knows is sentences written by code from the memory (`team/summary.py`): one per finding under "What the crew found", newest first, each once; the refuted claims with their reasons under "What was ruled out"; what the findings' authors left unchecked on the last line. A summary is never written back into the memory, so no digest of a digest. The memory keeps each refuted claim's reason and each finding's unchecked notes (`team/memory.py: refutations`, `unchecked`).
- Nothing in the model path changes: prompts, lanes, budgets, routing and review rules are as they were; every number, id and citation present before is present after, and no number is reformatted. Tested with the fakes and an offline run of the eight benchmark cases through the grader's rule; a benchmark round on Nightshift before merging is the right check.
- Tests: 235; CI runs 229 and skips the 6 that need live services.

## A reply cut short is read; a sentence asked for is taken (2026-10-27, morning)
- A model reply that stops after a complete value but before its closing brackets is closed and read (`clients/meterless.py: extract_json`); one cut inside a string is not. Nemotron-Mini on Nightshift had stopped Scout's query reply one brace short three times in a row, and two fresh P-104 maintenance reviews on the live crew lost their mass lookup.
- Euler: an empty answer re-asked as one sentence may come back as just the sentence, with no JSON around it; that sentence is the answer, and Vera still checks its number (`answer_in_prose`). Benchmark rounds 36 and 37: 8/8 in 30 s each.
- Tests: 210.

## The submission, checked against the rules (2026-10-27, morning)
- The video script ends at 3:45 and names Track 03, who it is for, and where each sponsor works on screen (Zetaris and H-MEM in Connections, the World Model in the council, Markovian in the close). `SPONSORS.md` says what was unique about our use of the sponsor technologies, and that Cursor was not used, which the rules allow. Four screenshots of the app are in the README and on a product slide.
- Every benchmark claim is the exactly graded one: 8/8 in 30 s on Nightshift (rounds 26 and 27) and 8/8 on the CPU in round 14. Rounds 17, 19, 23 and 24, cited before, are 7/8 graded exactly. Only numbers are graded exactly; the registry and summary cases check less, and `docs/BENCH.md` says so.
- Warden's standing missions show their goal with the machines filled in, not the template's `{machines}`; the trace table in the Advanced view names the provider of each call.
- Claims narrowed to what the code does: the calculator replaces a model's number only in Euler's and Ada's answers; Markovian reviews up to six files with scan hits; the World Model mirrors the council's record, which the agents read from `council/`.

## A planner lane, and a lane on its own endpoint (2026-10-27, morning)
- Atlas plans and writes the final answer on his own lane, `plan` (`Lead(plan_lane="plan", compose_lane="plan")`). Left unset it follows `LANE_DEEP`, so the live crew plans on the model it always did.
- A lane can have its own endpoint: `LANE_<NAME>_URL`, `_KEY`, `_TIMEOUT`, `_BACKUP` (`clients/meterless.py: LaneEndpoint`). A call the endpoint cannot answer goes to the crew's own provider with the backup model, and later calls go there directly for two minutes; the endpoint's failure never marks the laptop down. This is how Atlas and Vera can run on a hosted Nemotron-3-Ultra-550B while the workers stay on the laptop's Nemotron-Mini-4B.
- On Nightshift the lane defaults are Lightning-30B for the workers and Ultra-550B for `plan` and `critic` (they were Lightning-30B, Ultra-550B and Super-120B). The live `.env` names every lane, so nothing changes until it names `LANE_PLAN_URL` or `LANE_CRITIC_URL`; not yet measured on the benchmark.
- Worked examples in the agents' prompts were measured and not adopted: 7/8, 7/8, 6/8 and 6/8 against 8/8 without them (rounds 28 to 31, `docs/BENCH.md`). The 4B planner copied a phrase of his example into a real task, and Euler copied the shape of an example answer. They stay on the branch `crew/worked-examples` for a larger model.
- Tests: 208.

## Exact numbers, every answer with its sources (2026-10-27, early morning)
- A number counts only as a tool's value rounded to the precision it is written with (`verify.rounds_to`): 122.6, 122.63 and 123 are 122.625 rounded, 122.55 is not. Within 1 % had counted, so 122.55 N stood for 12.5 kg x 9.81 m/s^2 = 122.625 N: code overruled Vera's objection, and the benchmark graded it right. The benchmark grades the same way, and its arithmetic case expects 122.625.
- The answer states the calculator's value, not the model's arithmetic: a number Euler or Ada writes within 1 % of a calculator result, that no evidence covers, is replaced by that result (`reconcile_numbers`, trace event `numbers_from_calculator`). Euler's evidence carries the calculator's value only; it had carried the figure the model expected, which then counted as evidence for itself.
- When the writer of the final answer cites nothing, code lists the sources after it (`Sources: T1 (research) [T1.E1]; ...`), so every answer can be checked against its evidence.
- Benchmark rounds 25 and 26 on Nightshift (`docs/BENCH.md`): 7/8 and 8/8, the arithmetic case right both times; rounds 23 and 24 re-graded with the exact grader are 7/8 each.
- Tests: 206; CI runs 200 and skips the 6 that need live services.

## Whole lists, no made-up numbers, lessons that fit the task, a replay for the video (2026-10-26, night, and 2026-10-27, early morning)
- Scout: a task that asks "which X are there, and which of them Y" gets the whole list (`whole_list`). On Nightshift the model had filtered the registry to the machines without a baseline and left P-104 out (benchmark round 18). PR #63.
- `deploy-live`: a sidecar port with nothing listening is no longer an error. The empty pid lookup had ended the deploy before it started the sidecars and restarted Warden. PR #62.
- No made-up numbers in the final answer: the writer's numbers are checked like every task's, and a number that no accepted result, tool output or goal holds sends the answer back to code, which assembles it from the accepted results and says so (`compose_numbers_refused`). A Warden mission had stated 32 days between 2026-09-02 and 2026-10-05, which are 33 days apart. PR #64.
- Days between two dates are counted by code: the calculator takes two ISO dates (`days_between`, its only call that takes text); Atlas sends "how many days between" to Euler with the lookups it needs, instead of Scout, whose SQL date functions the platform refused three times; with exactly two dates in the task and the earlier results, Euler answers with no model call (`days_by_code`). PR #64.
- A reviewer's lesson reaches an expert only for a task like the one it came from: at least two content words in common with the task's goal (`team/memory.py`). Every task had been shown its expert's three newest lessons whatever it was about, and a lesson about a cube root made a plain multiplication answer 3. PR #64.
- Benchmark rounds 18 to 24 on Nightshift (`docs/BENCH.md`, `docs/evidence/bench/round18-nightshift.json` to `round24-nightshift.json`): round 18 7/8 in 39 s; round 19 8/8 in 40 s, against 222 s for round 17 on the workstation's CPU; rounds 20 to 22 fell to 6/8, 6/8 and 7/8 on the lesson problem; rounds 23 and 24 8/8 in 32 s each after the fix.
- The replay for the video: `docs/evidence/missions/20261026-195911`, Warden's maintenance review of P-104 on Nightshift, queued by a person and run by Warden, 16 s and 13 model calls; Vera accepted all four results, three of them by code. It found the mass (1.0 kg), the two maintenance records with their dates, the weight (9.81 N) and the 33 days between the records, counted by code; the injection guard withheld the note of record M-002.
- `scripts/admin/publish_public.sh` publishes the crew to a new public repository with the history rewritten by git filter-repo. Its rules live outside the repository, because they hold the strings they remove, and it refuses to push if anything is left. Nothing is public yet: the owner runs it. Benchmark run paths are stored relative to the checkout, and a goal queued from the shell is recorded as `shell`, so new evidence holds no home folder or login name.
- Tests: 203; CI runs 197 and skips the 6 that need live services.

## Nightshift first, inverse-live on its own, no false findings (2026-10-26, night)
- Nightshift is the primary provider. Every model call goes to Meterless Nightshift first: Nemotron-Mini-4B on a laptop GPU, about 59 tokens a second against 6 to 10 on the workstation's CPU. A call Nightshift cannot answer goes to the workstation's Ollama with the same model; the trace names the provider of every call and the sidebar says which one runs the AI. Nightshift's engine had never opened its API on the laptop: it froze creating a workspace in the OneDrive Documents folder; the launcher now points it at a local folder (`docs/operations/NIGHTSHIFT_TUNNEL.md`).
- `~/inverse-live` stands on its own: its own `.env`, its own Node packages, its own H-MEM/World Model and Markovian sidecars on ports named in `.env` (`SIDECAR_URL`, `MARKOVIAN_URL`), with a copy of the crew's memory. It had been writing its memory into a sidecar another folder started on Oct 24, which lacked inverse-live's fix for malformed requests.
- Sentinel no longer reports "no timeout" for a call that sets one: the scan reads the whole call across nested brackets, the finding is re-checked against the rule on its line, and Vera's objection stands when the evidence shows the opposite of an absence (`timeout=20` for "no timeout").
- The measurement history that lived only on the workstation (benchmark rounds 1 to 17, probes, engineer evaluations) is in `docs/evidence/`; each agent's baseline is its newest measured probe by recorded time.
- The public link moves to Tailscale Funnel's permanent address by itself once the tailnet's owner allows Funnel for the workstation (`docs/operations/ACCESS.md`).

## The repository reorganized: what's where (2026-10-26, evening)
- Code, one module per agent: `team/research.py` (Scout), `team/reasoning.py` (Euler), `team/sql_guard.py` (from `team/experts.py`); `team/vulnerability.py` (Sentinel, from `team/custom.py`, which keeps Ada); `team/watch.py` (Warden, from `core/inverse_core/watch.py`); `core/inverse_core/injection_guard.py` (from `agents/guard.py`); `team/council_wire.py` (from `team/wire.py`). No behaviour changes.
- Page modules named after what the sidebar shows: `ui/advanced_ui.py` (was `team.py`), `ui/warden_ui.py` (was `autonomy.py`), `ui/live_ui.py` (was `live.py`); the dead old crew page is gone and its live helpers live in `ui/chat_ui.py`. The Live panel has the veto and approve box again, which Tinker's phone alert points to.
- Scripts by role: the services at the top of `scripts/`, plus `deploy-live` and `inverse-watch`, which existed only on the workstation; `scripts/measure/` and `scripts/admin/` (`notify.py` is `send_alert.py`); the data platform's SQL in `data/zetaris/`.
- Documents: current reference at the top of `docs/`, `docs/operations/`, `docs/hackathon/`, `docs/archive/`; `docs/README.md` and the README say what's where.
- Tests: one file per agent or subsystem, the same 188 tests as before the move (203 by 27 October); shared helpers in `tests/fakes.py`.

## Agents that get things done, and take turns (2026-10-26, afternoon)
- The conflicts the logs showed, fixed at their cause: a tool ignores arguments it does not take (the model's `why` inside `args` had crashed Ada's queries); Sentinel's answer carries no number the evidence lacks (a code-made count sent the daily code review back three times until it ran out of time); the same rule objection twice ends a task; a question about the crew ("what are you capable of") is answered from its records with no model call (it had taken 27 calls and 431 s and failed); Warden reviews code four files at a time, changed files first, every six hours.
- Turns on the one CPU (`core/inverse_core/team/gate.py`): people and benchmarks first, Warden second, Tinker last, before every model call; markers carry their pid so a crash never blocks anyone.
- Tinker: a compile check and one repair turn when a change breaks a test; research from the crew's own probe evidence, the web on every third cycle; the coder unloaded after each use; a change merges on its own only with a measured improvement against a real baseline or its own passing test.
- The deploy script waits for a running mission instead of cutting it short, and gives up rather than deploy over one.
- `docs/BENCH.md` "What the hardware allows": the memory bus sets the ceiling at about 12 tokens a second; a slot-powered graphics card is the next step.

## Half the time, and the flaws a review found (2026-10-26)
- Plain goals are planned by rule without a planner call (`simple_goal`, then the same guard); an answer whose every number is in its own rows or calculator results, with nothing hedged or unchecked, is accepted by code (`verified_by_code`); a digest is read out of the memory by code; shorter caps for Euler's steps and Scout's answer. Round 17: 8 of 8 clean in 222 s against 548 s in round 14 (`docs/BENCH.md`).
- A task that asks for the records gets every row (a small `LIMIT` the model wrote is dropped, `sql_unlimited`); the number check's hundredfold allowance applies only to percentages (9.81 no longer covers 981.0); the Atlas and Vera probes switch the two shortcuts off so they measure the model; an empty tool list means no tools; `fetch_url` never follows a redirect; `weigh` counts as a computation word; a sensor selected by id in the SELECT list no longer blocks the id rewrite.
- `docs/AGENT_STRUCTURE.md` states the shape every agent shares, and `tests/test_structure.py` checks it: the nine config fields, a prompt that exists, a known kind and lane, a budget, a crew name, a probe set.

## Toward ten of ten: the fourth batch, a phone digest, Tinker's merge gate, a visual theme (2026-10-26)
- By code: Atlas gets routing rules in the planner prompt; Ada sums a total across datasets with the calculator before speaking (`total_by_code`) and the calculator hint uses the goal's own numbers, never an id; Forge's template expert carries the goal's constants as given values; Euler's number in prose goes to the repair turn; Scout drops a quantity filter the task never asked for (`sql_unfiltered`); Sentinel reads the lines around each scan hit by code (`hits_read`). Probes before and after in `docs/evidence/probe/probe5.json` and `ten2.json`: Euler 5.9 → 9.4, Ada 7.8 → 8.4, Scout, Vera and Sentinel at 10, Atlas 7.8, Forge 5.5. Measured and reversed: the KNOWN LIMITATIONS note in a 4B's prompt cost Euler 2.5 points, so it is opt-in (`LIMITS_NOTE=on`) and the awareness lives on the Crew panel and in Tinker's backlog.
- The phone: every alert is logged with the channels that took it (`state/alerts.jsonl`, first in the Alerts panel); Warden sends a digest of what the crew said every `NOTIFY_DIGEST_MINUTES` (30) on the ordinary channels (`core/inverse_core/digest.py`).
- Tinker: a change merges only when the agent's probe improves, a test executes a changed line (coverage over the suite) or the item's own test in `backlog_tests/` passes; otherwise the branch is pushed and left for a person. Merged items are not picked again while anything else is open. Overnight it had merged three no-ops through every gate.
- The look: Space Grotesk, Manrope and JetBrains Mono; violet, cyan and amber on deep navy; layered backgrounds, glass panels, tinted chat bubbles, a glowing chat input, a gradient wordmark (`.streamlit/config.toml`, `ui/parts.py`).

## A chat front page, a live feed that narrates, agents that know their limits (2026-10-26)
- The front page is a conversation (`ui/chat_ui.py`): ask at the bottom, the crew answers in the thread, and the right-hand panel holds the artifacts of the answer (evidence, who did what, steps), the live feed, the crew with what each agent is working to fix, Warden, the council and the alerts sent to the phone with the ntfy setup and a test button. The sidebar is a slim rail: new chat, Chat/Advanced, recent missions, connections, memory, sign out.
- The trace narrates a mission into the chat log as it happens (`chat.narrate`): the plan, hand-outs, tool calls, results, Vera's verdicts, retries, the answer. The Live panel reads like a stream instead of two lines per mission.
- `core/inverse_core/team/limits.py`: the probes an agent fails and the improvement items that name it become a short standing note in its prompt, with the aim to remove them and to propose the rule that would; Atlas and Vera included. The latest full probe (`docs/evidence/probe/probe4.json`) is committed so every checkout has it.
- Measured, not adopted: `nemotron-3-nano:4b` on this CPU took 130 s for the arithmetic case against 31 s for nemotron-mini, so the bench was stopped; and the sponsor's hosted Nemotron through the tunnel passed 7 of 8 in 893 s against 548 s locally (`docs/evidence/bench/nightshift-round1.json`): a short request answers in 2 s, a whole mission does not, because the big model writes five times more. Bigger is slower here; the crew stays local.
- Tinker's first merge on the council's approval: `auto/20261026-0018-euler-must-compute-roots-and-powers-with`, one line in `ReasoningExpert._check` that passed the tests, the probe, Sentinel's review and Vera's vote and was deployed after the veto window. The line keys on a `calc_type` field no step carries, so it changes nothing: the gates let a harmless no-op through, which is the next gate to add (a change must move the probe or touch a line a test exercises).

## A coder model for Tinker's engineer, measured (2026-10-25, night)
- Tinker's engineer step runs on its own lane, `engineer`, which `TINKER_ENGINEER_MODEL` points at a coder model (unset: the deep lane); the crew's lanes are untouched. `scripts/engineer_eval.py` measures a model as the engineer on four small edits decided by tests and on the real backlog items decided by the test suite (`docs/evidence/engineer/`). On the workstation: nemotron-mini 2 of 4, qwen2.5-coder:3b 3 of 4, qwen2.5-coder:7b 4 of 4 at 55 s per task; the 7B is the engineer now.
- Tinker's backlog is six items verified open against the code, each mapped to a file region (`REGIONS`) and carrying its own "what to change" paragraph; the engineer's first reply is the edit, and `edit_file` forgives line numbers copied from the excerpt.

## Agreement and routing by code, Tinker edits in place, a compact crew page (2026-10-25, night)
- Atlas: a one-task plan carries the goal verbatim (a paraphrase by a 4B planner can only drop a detail or be the schema's example text); placeholder tasks ("write the instruction for the task") are refused and the planner re-asked; plain arithmetic with nothing to look up goes to Euler; a lookup that feeds a computation is rewritten so Scout looks up only. Scout: numbers the rows do not contain are replaced by the row values (`scout_numbers_dropped`), so Scout and Vera agree by construction. Benchmark round 11 exposed both failures; rounds 11 and 12 are in `docs/BENCH.md`.
- Tinker's engineering step works on one named file and region with `edit_file` only, and "no safe change" is an accepted answer recorded as a lesson. With `TINKER_AUTOMERGE=council` (the default) a change that passed the tests and the probe is merged on Sentinel's review and Vera's vote after a veto window (`veto auto/…` or `approve auto/…` in the Live box); `human` leaves every branch for a person.
- The crew page: one header line with the status row beside it, the examples, the goal and Go, the mission or the answer, then four sections (The crew, On its own, Council, Past missions) behind a switch; shorter captions on the Warden panel and the council.
- Textbelt's free SMS is disabled for US numbers; carrier SMS by email (T-Mobile:`number@tmomail.net`) needs SMTP credentials in `.env`.

## The crew works on itself, a Live chat, and your phone (2026-10-25)
- **Tinker** (`scripts/tinker.py`, `scripts/inverse-tinker`): an improvement loop that runs round the clock in a sandbox clone: picks the next item of the crew's improvement list or a failing probe, researches it on the web (`web_search`, `fetch_url`, through the injection guard), makes the smallest change (`edit_file`, `write_file`, sandbox only), runs the tests and the agent's probe by code, and when nothing got worse pushes a branch `auto/...`, files a council task card and alerts a person. It never touches the live checkout and cannot merge.
- One chat log for everything the crew says (`core/inverse_core/chat.py`, `state/chat.jsonl`): the message bus, Warden's log, the council and Tinker write to it; the **Live** mode of the page shows it as a chat, refreshed every three seconds, with a box that queues a goal.
- `core/inverse_core/notify.py`: alerts on the phone over free channels named in `.env` (ntfy push with a call-like priority, Telegram, a carrier's email-to-SMS gateway); `scripts/notify.py` to test one. The crew page writes `state/ui_mission.json` while a mission runs so Tinker waits.

## A benchmark, faster missions, fewer failed tasks, and the agents measured (2026-10-25)
- `scripts/bench.py` + `bench/cases.yaml`: eight checkable goals, pass/clean/seconds/calls/tokens per case, results under `docs/evidence/bench/`; `scripts/probe.py`: each agent alone on its own questions, marked 0-10; `scripts/warmup.py` warms the model server's prefix cache. Write-ups: `docs/BENCH.md`, `docs/AGENT_REPORT.md`.
- Speed: reply caps per call, the composer skipped for one or two short results (cited by code), Scout answering in one conversation, smaller tool results and a lazy fold, plan review only for three or more tasks, `prompt_too_long` traced. Rounds 7 and 8: 7 of 8 goals in about 370 s against 4 of 8 in 588 s at the start.
- Effectiveness, by code where code can decide: a value-annotated SQL schema with examples; a rejected query is evidence with the platform's message; a column the task asks for is added to the query; row values the answer leaves out ride along, cited; a routing guard on every model plan (`plan_guard`); the reviewer judges quotes against evidence values, sends back "not available" with the rows, a number from nowhere, and an asked value left out, and retries a model's reject once; a calc that names a quantity is resolved from the context; a clean scan is answered by code; a summary starts from the shared memory; a repeated tool call ends the loop by code; chunked reviews in JSON.

## Sign-in page (2026-10-25)
- `ui/auth.py`: with `UI_PASSWORD_HASH` in `.env` (written by `scripts/set_password.py`, a salted PBKDF2 hash, never the password), the UI shows a sign-in page first; a signed cookie keeps a device signed in for a week; **Sign out** in the sidebar revokes it; a wrong password slows the next try. Phone access through the tailnet is documented in the README.

## README first screen (2026-10-25)
- The tests badge, a ten-line diagram of a mission and a "Read next" links block at the top of the README; a marked place for the two screenshots.

## Vera's verdict in a checkable shape (2026-10-25)
- The Critic's model reply is `{"verdict", "problems": [{"quote", "why"}], "reason"}`: every objection quotes the words of the answer it is about. Code keeps an objection only when the quote is really in the answer and the evidence does not cover it (a number missing from the evidence, or, for a quote without numbers, most of its content words absent from the evidence). A revise or reject with no objection that checks out does not send work back: the result is accepted with the objection on record under "not checked" (`by: code` in the trace).
- A verdict that cannot be read (no JSON, or a word that is not accept, revise or reject) is asked for once more; unreadable twice, the result is kept and marked unreviewed, never silently accepted and never sent back for the reviewer's failure. `norm_verdict` reads approve, ok, pass, fail and the one-letter council forms.
- Plain lines for the new outcomes; `tests/test_critic.py` covers the checks, the re-ask, and the acceptance check of the plan: a correct arithmetic answer is no longer rejected on a made-up reason.

## Live view, Warden panel, council form (2026-10-25)
- The running mission lives in the process, not in one browser session: a click, a rerun or a page reload re-attaches to it; the status line names who is on which task, how many finished and the time elapsed; a **Stop** button (`ctx.stop`) lets the step in progress finish, starts nothing new, and the answer lists what did not finish, verbatim. Model replies, memory writes, Markovian chunks, proposals and council steps read as plain lines, live and in "How it went".
- Warden's panel refreshes itself every 10 seconds and shows the mission running now (`state/current.json`), the queue, and a button to show a mission Warden ran.
- The council section speaks in the agents' names, has a one-line empty state, a form built from choices (no JSON), the wire's own reason when a proposal is refused, and an undo that reports errors.

## Review fixes (2026-10-25)
- From the pre-submission review: votes read in a small model's own words; a second backer for self-serving or rule-filed changes; prompt addenda, granted tools, new missions and unevidenced notes become task cards or are rejected; the book replays incrementally and survives bad lines; the guard scrubs every column; Spark built-ins forbidden in SQL; plan review cannot copy the example; Critic verdicts normalised; a tool loop that overruns its budget fails honestly; client defaults and MODEL_TIMEOUT; Warden re-reads missions, retries a failed new-data mission once and plans fixed-text missions by rule; the datasets generator stands alone; evidence committed under docs/evidence/.

## The council (2026-10-24)
- CW/1 (`team/wire.py`): one small JSON object per message with short keys and hard caps; verbs P, S, V, D, X; kinds cfg, mission, note, agent, code with a per-kind patch whitelist; content-addressed ids merge the same idea into one proposal with backers.
- `team/council.py`: filing is free (a `propose` list in an agent's reply, the `propose`/`support` tools, two rules in the Lead, people); sessions happen only by rule, at most once an hour, bounded to four model calls; Vera votes on the whole agenda in one call, the agent a change concerns votes on its own items; a fixed rule decides; effects are applied by code with undo (experts.local, missions.local.yaml, shared memory, kept agents, task cards for people). Book, trace events, bus messages and World Model entities for every step. Warden holds a session when one is due.
- UI: a council section on the crew page (open proposals, decisions, a session on demand, a form, undo); `scripts/council.py` from a shell.

## The experts are the product (2026-10-24)
- The physics subsystem (orchestrator, analysis, validators, inference, the physics expert, the Physics bench page, its scripts, evidence and tests) is removed: the hackathon entry is the crew of local, autonomous agents. The data generator for the obs-service stays.
- Warden reacts to new sensor data by starting a crew mission about that machine (fixed goal text), not a physics check; the `data check` standing mission replaces `machine health`.
- `team/verify.py` keeps the one deterministic check the crew still needs (numbers in an answer must appear in its evidence).
- UI: `app.py` is the Crew page by default with Advanced beside it; `plain.py` and `parts.py` keep only crew wording.

## The crew (2026-10-24)
- The agents have names by expertise (Atlas, Vera, Warden, Newton, Scout, Euler, Ada, Sentinel, Forge; `core/inverse_core/team/crew.py`, `callsign` in `experts/*.yaml`); identifiers in configs, plans, traces and messages are unchanged. `docs/CREW.md`.
- A new front page, **Crew**, is the default: one goal box, the agents at work in plain sentences, the answer, who did what, what they said to each other, Warden's panel (standing missions, a queue, what ran on its own) and past missions to replay. The old pages remain as **Physics bench** and **Advanced**.
- Standing missions (`missions.yaml`): Warden runs them on their schedule, so the crew works without anyone asking (machine health, code review, memory digest).
- `MODEL_PROVIDER` defaults to `ollama`: fully local; `nightshift` remains the sponsor path.

## Small gaps closed (2026-10-24)
- The Proposer and the Critic ask the runtime for one JSON object (`response_format: json_object`), as the team side already did; the committed traces show the parse errors this removes. `docs/SPONSORS.md` now says what those traces show about Nemotron proposals instead of a claim that could not be true by construction. `MarkovianClient` defaults to the Markovian port (8101). The H-MEM sidecar answers 400 to a malformed body instead of dying (integration test). The unknown-mass limit is in the README and the UI explains it in plain words.

## Runs on its own, and the experts talk (2026-10-24)
- Watch mode (`scripts/watch.py`, `core/inverse_core/watch.py`): a loop on the workstation checks Zetaris for new sensor data per machine, runs the physics check, decides by rule whether the team is needed (wear flag, rejection, refusal) and runs it with a goal written from the verdict; a manifest per run, a heartbeat, a log, a goal queue people and the UI can write to, recovery of interrupted runs, and a sidecar check. `~/.local/bin/inverse-watch` keeps it running in tmux on the workstation.
- A message bus (`team/bus.py`): accepted results, the Critic's notes, questions and answers go on `runs/<ts>/messages.jsonl` and the trace; each expert sees the messages addressed to it with its next task. New tools `ask_expert` (consult another expert, one level deep, small budget), `post_message` and `read_messages`; the Solver holds them. The UI shows the conversation of every run and a watch-mode panel.

## Faster runs (2026-10-24)
- The Lead runs a plan level by level and executes independent tasks concurrently (default two at a time; `--parallel`); Trace and Budget are thread-safe; a per-run SQL cache shared by the Research expert and the tool layer; plain progress lines for both.

## Review fixes (2026-10-24)
- An adversarial review of the overnight changes confirmed eight defects; all fixed with regression tests: non-string or null model fields no longer crash a run (answer, reason, evidence detail), one unreadable plan sample no longer ends a vote, memory errors are traced instead of fatal, experts proposed by losing plan samples are dropped, the physics verdict is remembered only after review, the SQL guard checks aliased comma lists and refuses subqueries, file tools never read dot-folders or skipped folders, prompt files must live inside the repository, a Markovian chain is abandoned cleanly on any failure and unreviewed files are listed, stray final markers cannot end a chain early, the architect's test-drive budget is reported instead of failing the architect, the closed-form solver takes y0 at the first sample, the UI survives an offline Zetaris or a broken experts.local file and keeps the architect's tools when saved, the evaluation uses distinct noise realisations per scenario and varies record shapes for the refusal check.

## Submission documents (2026-10-24)
- `docs/SPONSORS.md` (sponsor technology explanation), `docs/SUBMISSION.md` (project details and the checklist), `docs/ONBOARDING.md` (adding a machine; what a plant would need); the eval report gains a ten-times-noisier scenario.

## Demo material (2026-10-24)
- `docs/DEMO_SCRIPT.md` rewritten to the real UI labels and measured timings, with a replayed team segment and fallbacks; `docs/agent/NIGHTSHIFT_TUNNEL.md` (self-reconnecting tunnel for the laptop that hosts Nightshift); honest progress label on the single-machine page.

## Research-backed algorithms (2026-10-24)
- Closed-form solution of the linear unforced oscillator in `simulate` (exact, much faster); split conformal prediction band on the unseen tail of every accepted fit (`inference/conformal.py`, reported in the verdict and the UI); Reflexion lessons per expert in H-MEM (`team/memory.py`, injected by the Lead); self-consistency plan voting (`--votes N`). References and locations in `docs/agent/ALGORITHMS.md`.

## Architect expert (2026-10-24)
- `kind: architect`: designs, creates (`create_expert`), test-drives (`test_expert`) and refines new custom experts during a run; plans may assign a task to an expert the architect will create; the Lead verifies it exists when the task's turn comes. Only an architect may hold the architect tools.

## Markovian for long reviews (2026-10-24)
- Meterless Markovian (vendored reference) driven step by step over HTTP from a stand-alone service; the vulnerability expert reviews two or more files as one bounded chunk per file with a compressed carryover; measured versus estimated tokens in the trace; engine evidence and conformance.

## Customizable experts (2026-10-24)
- New expert kinds `custom` (a tool loop defined only by config) and `vulnerability` (defensive, this repository only, findings verified against the files); built-in `solver` and `vulnerability` experts; tool layer `core/inverse_core/team/tools.py`.
- `experts.local/` overrides (gitignored); UI panel to add, edit, disable or remove experts; the lead can create an expert for a run (**Keep it** saves it); experts can review the plan before it runs (`--collaborate` / UI toggle).
- Plain-language progress lines for team runs (`ui/plain.py: team_step`). Docs: `docs/agent/EXPERTS.md`.
- Edits to existing files: `team/{lead,critic,registry,llmcall,build,experts}.py`, `ui/team.py`, `ui/plain.py`, `scripts/run_team.py`, `README.md`, `.gitignore`, tests.

## Team orchestrator (2026-10-23)
- New `core/inverse_core/team/` (Lead, Plan, Critic, TeamMemory, config-driven experts), `experts/*.yaml`, `scripts/run_team.py`, UI mode `ui/team.py`.
- Edits to existing files: `ui/app.py` (mode switch; forget also clears team memory), `requirements.txt` (+pyyaml), `.env.example`, `README.md`.
- Scout Intent not yet integrated.
