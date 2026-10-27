# Pre-existing versus hackathon work

The hackathon window opened on 22 Oct 2026. The first commit in this repository is dated **23 Oct 2026, 14:14** (Central), so
nothing in the history predates the window. The public repository is this history rewritten by `scripts/admin/publish_public.sh`:
dates, messages and authors stay, private strings such as addresses are replaced, and the commit ids change. Apart from the
third-party pieces below, everything in the tree was written during the hackathon by two of the team's five members, with Claude Code on an
Ubuntu workstation and a Windows laptop,, except one line by Tinker, the crew's own improvement loop: `return expr.strip()` in
`core/inverse_core/team/reasoning.py`, merged on 26 October as approved by the council. Its two other council-approved one-line
changes were removed again the same day. The history shows them as the commits authored `Tinker`.

**Third-party, not authored here**

- Zetaris data platform: Docker images run unmodified from the organizers' starter (`~/zetaris-platform`, outside this repository).
- Meterless open core (Apache-2.0): the H-MEM, World Model and Markovian reference engines, copied into
  `services/meterless-sidecar/vendor/` by `npm run setup` (gitignored); the Nightshift Runtime, the primary provider, runs as a
  separate app on the Windows laptop.
- `smoke_test.py`: the organizers' starter script, kept as provided.
- NVIDIA Nemotron-Mini-4B-Instruct: served by Nightshift on the laptop's GPU through one lane
  (`local-runtime/nemotron-mini-4b-instruct-q4-k-m`), and as `nemotron-mini` by the workstation's Ollama, the fallback.
- Libraries in `requirements.txt`: numpy, requests, python-dotenv, pyyaml, pandas, streamlit, pytest, fastapi, uvicorn, openai.
- Other tools and services the crew runs or calls: Ollama (the `ollama/ollama` Docker image) on the workstation;
  `qwen2.5-coder:7b`, the model of Tinker's engineer step; `tsx`, which runs the sidecar; Cloudflare's quick tunnel for the
  public link (Tailscale Funnel once the tailnet allows it); ntfy.sh, Telegram, Textbelt or a carrier's e-mail gateway for phone
  alerts, whichever `.env` configures; DuckDuckGo for Tinker's web search.

**Removed during the hackathon.** A physics-based analysis subsystem built on 23 and 24 October (an orchestrator, validators,
inference code, its evaluation and evidence) was deleted on 24 October when the team refocused the entry on the crew of agents.
It remains in the history before the commit "The experts are the product: remove the physics subsystem, Warden starts missions
on new data" (`db408c1` in the private repository; the public rewrite gives it a new id); nothing in the current tree depends on it.
