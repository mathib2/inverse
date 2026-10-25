# The council: how the crew changes itself

Any agent can propose a change to the crew at any time, at no cost. The council decides those proposals in short, rare sessions,
and an adopted proposal changes one real thing, reversibly, by code. Nothing is decided per idea, nobody waits for a meeting,
and agents never edit their own code.

## 1. The wire: CW/1

The agents speak a tiny protocol: one JSON object per message, short keys, hard caps, five verbs. Strict JSON because the
runtime already enforces JSON mode; short keys and caps because a 4B model must be able to say it reliably in a few tokens.
Text that is too long is truncated, never refused; a message with an unknown verb, kind or target is dropped with a traced
reason (`proposal_dropped`). `core/inverse_core/team/wire.py` is the whole grammar.

| Verb | Who writes it | Shape |
|---|---|---|
| **P** propose | any agent, a rule, a person | `{"k":"cfg\|mission\|note\|agent\|code","t":"<target>","w":"<what, 140>","y":"<why, 140>","e":["T1.E2"],"p":{<patch>}}` |
| **S** support | any agent or person | the same idea filed again becomes a backer; `{"id":"P-3f9a2c"}` through the `support` tool |
| **V** vote | Vera; the agent a change concerns | `{"votes":{"P-3f9a2c":"y" \| "n:<reason>" \| "r:<change asked>" \| "?"}}` |
| **D** decide | code only | `{"id","d":"adopt\|reject\|defer\|expire\|needs_human","r","votes","s"}` |
| **X** effect | code only | `{"id","x":"applied\|failed\|reverted","u":<undo file>,"summary"}` |

Kinds and the exact change (`p`, a whitelist checked by code):

| kind | target | patch keys |
|---|---|---|
| `cfg` | an agent id | `budget.tool_calls` (1..16), `budget.tokens` (1000..200000), `budget.seconds` (30..900), `model_lane` (fast\|deep), `tools+`/`tools-` (from a small grantable list, never the architect's tools), `system_prompt+` (one dated sentence, at most three per agent) |
| `mission` | a mission name | `every` (0.5..168 hours), `enabled`, `goal`, `name` (to add one; at most eight missions) |
| `note` | `shared` | none: `w` is the claim to remember |
| `agent` | the agent's id | `config`: the full config of an agent Forge built in a run |
| `code` | `repo` | none: `w` names the change; it always becomes a task card for people |

A proposal's id is the hash of its kind, target and what (`P-` plus six hex characters), so the same idea filed by two agents is
one proposal with two backers, and backing is what makes it urgent.

## 2. Filing: free, any time

- **Inside a reply an agent already returns.** Every expert's final JSON may carry `"propose": [...]` (at most two). The Lead hands
  them to the council when Vera accepts the result. Zero extra model calls.
- **The `propose` and `support` tools** (one tool turn), for tool-using agents such as Ada.
- **Rules in the Lead**, after every mission: an agent whose tool-call budget ran out gets a proposal to raise it by two
  (`rule:budget`); an agent Forge built and used gets a proposal to keep it (`rule:keep`).
- **People**, from the crew page or `scripts/council.py propose '{...}'`.

Filing writes one line to `council/book.jsonl` (append-only, replayed at start) and a `proposal_filed` trace event. It never
convenes anything.

## 3. Sessions: rare, short, decided by rule

A session happens only when a code rule says so (`Council.due`): three or more open proposals, a proposal with two backers,
a proposal that waited a day, Warden's cycle (which checks these rules), or a person pressing the button. Never more than once
an hour unless a person asks. Each session is bounded by `Budget(max_llm_calls=4, max_seconds=180)` and an agenda of at most
five (most backed, then oldest):

1. **Code first.** Expire what waited a week or was deferred twice. Check the rails on every item without a model: a budget may move
   by half at most per decision; the architect's configuration is never changed; an agent is never left without tools and a code reviewer keeps
   its code tools; a note needs an evidence reference or a second backer; only the keep rule (an agent Forge built and used) or a person keeps an
   agent, never over a built-in; code changes are never applied. Prompt addenda, granted tools, new missions or new goals become task cards for
   people unless a person filed them; an agent may not schedule a mission more often than every six hours.
2. **Vera votes on the whole agenda in one call** (lane `critic`): `y`, `n:reason`, `r:what to change`, `?`.
3. **Each agent a change concerns votes on its own items in one call** (lane `fast`, its own prompt), at most two such calls.
4. **The rule:** `n` from Vera or the owner rejects; `r` defers with the requested change kept as a note; `?` (or an unreadable
   reply, an offline model or a budget stop) defers without counting as a vote; a change an agent asks for itself, or a rule files, needs
   a second backer; otherwise adopt. The proposer never votes on its own change. Two deferrals expire a proposal. Votes are read in
   a small model's own words (`accept`, `reject`, `approve`); a copied example is an abstention.
5. **Effects by code**, each with an undo record in `council/undo/`: `cfg` writes `experts.local/<agent>.yaml` through the registry's
   validation and reloads; `mission` writes `missions.local.yaml` (merged over `missions.yaml` by `core/inverse_core/missions.py`);
   `note` writes shared memory with source `council`, which no deterministic check can be overwritten by; `agent` keeps Forge's config;
   `code` appends to `council/human.md`.

On a 4B model at about 10 tokens per second a session costs one to three calls and 30 to 90 seconds. A session that runs out of
budget records the votes it has and defers the rest; nothing is repeated.

## 4. What is traced and shared

Every step is a line in the book, a trace event (`proposal_filed`, `proposal_backed`, `council_session`, `council_decision`,
`council_effect`, `council_done`, `council_vote_unreadable`), a message on the bus (`council → everyone` for adoptions), a file
under `council/sessions/`, and a shared entity in the Meterless World Model (the proposal as a hypothesis about the crew with its
decision as status, each vote as a result). The crew page shows open proposals, decisions, the last session, a form for people, a
button to hold a session, and an undo for applied changes.

## 5. Tests

`tests/test_council.py`: the wire (caps, dedup ids, patch whitelist, vote parsing); filing from an accepted reply, the tools and the
book replay; a full session with scripted votes (adopt, reject, needs_human) and every effect applied and reverted; rails and
abstentions never adopting without a vote; the once-an-hour and quorum rules; the two Lead rules. No model, no network.
