# Pre-existing versus hackathon work

The hackathon window opened on 22 Oct 2026. The first commit in this repository is dated **23 Oct 2026, 14:14**, so nothing in
the history predates the window. Everything in the tree was written during the hackathon by the team (two people, with Claude
Code on an Ubuntu workstation and a Windows laptop).

**Third-party, not authored here**

- Zetaris data platform: Docker images run unmodified from the organizers' starter (`~/zetaris-platform`, outside this repository).
- Meterless open core (Apache-2.0): the H-MEM, World Model and Markovian reference engines, copied into
  `services/meterless-sidecar/vendor/` by `npm run setup` (gitignored); the Nightshift Runtime, when used, runs as a separate app.
- `smoke_test.py`: the organizers' starter script, kept as provided.
- NVIDIA Nemotron models: `nemotron-mini` through Ollama locally, Nemotron routes through Nightshift.
- Libraries in `requirements.txt`: numpy, requests, python-dotenv, pyyaml, pandas, streamlit, pytest, fastapi, uvicorn, openai.

**Removed during the hackathon.** A physics-based analysis subsystem built on 23 and 24 October (an orchestrator, validators,
inference code, its evaluation and evidence) was deleted on 24 October when the team refocused the entry on the crew of agents.
It remains in the git history before commit `db408c1`; nothing in the current tree depends on it.
