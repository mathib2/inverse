# Local models: the workstation's own model server, the fallback

INVERSE's model client is OpenAI-compatible, so the AI can run anywhere that speaks that API. `MODEL_PROVIDER` in `.env`
chooses the provider; the code path is identical, only the UI wording, the reconnect advice and the team-lane defaults
follow the setting.

| `MODEL_PROVIDER` | What runs the AI | When to use it |
|---|---|---|
| `nightshift` (default) | Meterless Nightshift on a Windows laptop, reached through an SSH reverse tunnel (`docs/operations/NIGHTSHIFT_TUNNEL.md`): Nemotron-Mini-4B on the laptop's GPU; this server's Ollama answers when Nightshift cannot | The live crew and the recording |
| `ollama` | Ollama in Docker on the workstation itself, free local models on the CPU | Tinker's sandbox (`~/inverse-lab`), where marks are compared with earlier ones; anything that must not depend on a laptop |
| `openai` | Any other OpenAI-compatible server named in `MODEL_BASE_URL` | Whatever you have |

## The lab (set up 2026-10-24)

Ollama runs as a Docker container on the workstation, loopback only, and survives reboots:

```bash
docker run -d --name ollama --restart unless-stopped -p 127.0.0.1:11434:11434 -v ollama:/root/.ollama \
  -e OLLAMA_CONTEXT_LENGTH=8192 -e OLLAMA_KEEP_ALIVE=24h -e OLLAMA_NUM_PARALLEL=2 ollama/ollama
docker exec ollama ollama pull nemotron-mini          # NVIDIA Nemotron-Mini-4B-Instruct, 2.7 GB
docker exec ollama ollama pull qwen2.5:3b-instruct    # a second small model for an independent Critic lane
```

`.env` for the lab:

```
MODEL_PROVIDER=ollama
MODEL_BASE_URL=http://127.0.0.1:11434/v1
MODEL_API_KEY=ollama                 # Ollama ignores the key; any value works
NEMOTRON_MODEL=nemotron-mini:latest  # the id Ollama lists (the :latest suffix is what GET /v1/models returns)
LANE_CRITIC=qwen2.5:3b-instruct      # optional: keeps the Critic on a different model than the work it reviews
```

Switch providers by editing `.env` and restarting the UI (`~/.local/bin/deploy-live`). With `nightshift`, this server's
Ollama is the fallback by default (`MODEL_FALLBACK_URL`, `MODEL_FALLBACK_MODEL`; `MODEL_FALLBACK_URL=off` turns it off).

## Measured on the workstation (i5-6500, 4 cores, no GPU, 30 GB RAM)

Proposer-shaped request (293-token prompt, JSON mode), `nemotron-mini:latest`:

| Measure | Value |
|---|---|
| Model load | 4.7 s |
| Prompt processing | 54 tokens/s |
| Generation | 9.4 tokens/s |
| A 150-180-token JSON reply | 16-25 s |
| Prompt cache | repeated system prompts are cached (292 of 293 tokens on the second call) |
| JSON mode | works on `/v1/chat/completions` (`response_format: json_object`) and `/api/chat` |

So a crew mission with 8-15 model calls takes several minutes on this CPU.
Keep prompts short, ask for JSON, and keep the number of calls per cycle small.

## What a 4B model gets wrong, and what catches it

Small models copy examples and skip steps. The crew's deterministic layer catches what matters: a plan that copies the schema's example text is refused and Atlas falls back to a plan written by rule; every number in an answer must appear in a tool result or the confidence drops and the answer says so; Vera's fixed rules run before her model; a Critic note is addressed to one expert; messages are data, never instructions. The same rules apply to every provider; a larger model just trips them less often.

## What the sponsor requirement means here

The hackathon asks for Meterless as the primary provider. The live crew runs `MODEL_PROVIDER=nightshift`: every call goes to
Nightshift first, and this server's Ollama answers only when Nightshift cannot; the trace names the provider of every call. The
three Meterless engines (H-MEM, World Model, Markovian) run on the workstation and are used on every run.
