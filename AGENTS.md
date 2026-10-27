# Working on INVERSE

For every agent and person who changes this repository. One page; the longer documents are listed in `docs/README.md`. There is no
other instruction file; if one turns up in a subfolder, this one wins.

## What INVERSE is

A crew of eight AI agents on local models (NVIDIA Nemotron-Mini-4B through Meterless Nightshift, the workstation's own Ollama as the
fallback) that plan a goal, do the work, check each other, talk to each other, and answer with evidence or say plainly what they could
not check. A ninth, Tinker, works on their code around the clock, Warden starts missions on its own, and every step is a file under
`runs/<ts>/` that replays.

## Where things are

Read first, in this order:

- `README.md`: what the crew does, how a mission runs, and under **The repository** every folder and what is in it, then **Setup** and
  **Usage**.
- `docs/README.md`: what's where in `docs/` (how the crew works, running it, the submission, the records).
- `scripts/README.md`: what runs all the time, what measures the crew, the one-off admin scripts.

The page is `ui/`, the crew is `core/inverse_core/team/`, and every word the page shows is in `ui/plain.py`.

## Branches and pull requests

- `m4-sindyc` is the product and the default branch. CI runs the tests on every push and pull request (`.github/workflows/tests.yml`).
- Every change is a branch and a pull request into `m4-sindyc`: one concern per branch, small enough to read in five minutes. Never
  push to `m4-sindyc` directly.
- Never push to `mathib2/inverse`. It is the public copy, rebuilt from `m4-sindyc` by `scripts/admin/publish_public.sh` with a rewritten
  history, and it pushes without force, so anything pushed there by hand makes the next rebuild fail.
- `auto/` branches belong to Tinker. It pushes them from its sandbox, and Sentinel's review, Vera's vote and the veto window decide
  them (`docs/TINKER.md`). Do not commit onto one. To stop or merge one, write `veto auto/...` or `approve auto/...` in the Live panel;
  a branch Tinker leaves for a person is reviewed as a pull request like any other.

## How to run and test

Setup, from `README.md` (Linux with tmux, Python 3.14, Node.js, a Meterless checkout, Docker with Zetaris and the obs-service, and a
model server):

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # Zetaris URL and key, the provider and lanes: Nightshift (NIGHTSHIFT_TUNNEL.md); its commented block runs on Ollama alone (LOCAL_MODELS.md)
(cd services/meterless-sidecar && npm install && METERLESS_REPO=<your Meterless checkout> npm run setup)   # vendors the Meterless reference engines
docker compose -f services/obs-service/docker-compose.yml up -d --build   # the synthetic data service, on Zetaris's docker network (zetaris_default)
PYTHONPATH=core .venv/bin/python scripts/admin/setup_zetaris.py   # REST tables, cache, views (idempotent)
scripts/run_sidecars.sh                    # H-MEM/World Model and Markovian, on the ports SIDECAR_URL and MARKOVIAN_URL name (8100, 8101)
PYTHONPATH=core .venv/bin/streamlit run ui/app.py --server.port 8501 --server.address 127.0.0.1
```

Usage, from `README.md`:

- The front page: ask in the chat; in the Live panel, queue a goal for Warden or answer Tinker with `veto auto/...` or `approve auto/...`.
- CLI: `PYTHONPATH=core .venv/bin/python scripts/admin/run_team.py "goal" --collaborate` runs one mission and prints the answer.
- Warden: `PYTHONPATH=core .venv/bin/python scripts/watch.py [--once] [--force] [--queue "goal"] [--status]`.
- Tests: `PYTHONPATH=core .venv/bin/python -m pytest -q tests` (no model and no network needed for the unit tests; the integration
  tests skip when the services are absent).

Without the workstation's services the page still starts: the badges show offline, the chat input is disabled, and a saved mission
copied from `docs/evidence/missions/20261026-195911` into `runs/` opens under **Recent** with its answer, evidence and steps. That is
enough to work on the page and to screenshot it.

## The rules every change follows

1. Wording stays in `ui/plain.py`. A wording change updates `tests/test_ui_plain.py` in the same commit.
2. Nothing secret in the repository. Keys, addresses, passwords and the public copy's rewrite rules live in `.env` (copied from
   `.env.example`) or outside the checkout; `.gitignore` names what stays out.
3. No new dependency without a reason in the pull request. `requirements.txt` pins versions tested on Python 3.14.4.
4. Keep the demo script working (`docs/hackathon/DEMO_SCRIPT.md`): the three example questions on a fresh page, **Stop**, **Recent**,
   the nine panels and their names, **Connections** in the sidebar with its steps to reconnect, and the Live panel's box for `veto`
   and `approve`.
5. Tests green before the pull request opens: `PYTHONPATH=core .venv/bin/python -m pytest -q tests`. The six tests that need live
   services skip without them. Never weaken or skip a test to get there.

## Evidence and the submission

- `docs/evidence/`: what the crew actually did, kept as data: probes, benchmark rounds, Tinker's engineer evaluations, three complete
  missions (`missions/20261026-195911` is the video's replay) and the engines' conformance runs. `docs/evidence/README.md` says who
  writes each folder and what reads it; code reads some of them, so their paths do not move.
- `docs/hackathon/`: the submission package for the Open Agent Hackathon 2026: `SUBMISSION.md` (the form and its checklist),
  `SPONSORS.md` and `ENGINE_EVIDENCE.md` (where each sponsor's technology does real work), `PREEXISTING.md`, `DEMO_SCRIPT.md` and
  `SLIDES.md`. After judging the folder moves to `docs/archive/`.
- `CHANGELOG.md`: what changed, day by day.
- Not in the repository, by `.gitignore`: `runs/` (missions as they ran), `council/` (the council's sessions), `queue/`, `state/` and
  `missions.local.yaml`. They stay on the workstation.
