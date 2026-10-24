# Local models: the development lab on the workstation

INVERSE's model client is OpenAI-compatible, so the AI can run anywhere that speaks that API. `MODEL_PROVIDER` in `.env`
chooses the provider; the code path is identical, only the UI wording, the reconnect advice and the team-lane defaults
follow the setting.

| `MODEL_PROVIDER` | What runs the AI | When to use it |
|---|---|---|
| `nightshift` | Meterless Nightshift on a Windows laptop, reached through an SSH reverse tunnel (`docs/agent/NIGHTSHIFT_TUNNEL.md`); NVIDIA Nemotron routes | The sponsor path: the demo recording and the live evaluation |
| `ollama` (default) | Ollama in Docker on the workstation itself, free local models on the CPU | Development, tests against a real model, unattended runs: nothing depends on a laptop or on credits |
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

Switch providers by editing `.env` and restarting the UI (`~/.local/bin/deploy-live`). The stored Nightshift key can stay
in `MODEL_API_KEY`: Ollama ignores it, and it is needed again for the recording.

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

The hackathon asks for Meterless as the primary provider. With `ollama` the provider at runtime is not Meterless; the three
Meterless engines (H-MEM, World Model, Markovian) still run on the workstation and are used on every run. For the demo
recording and the live evaluation set `MODEL_PROVIDER=nightshift` (`docs/SUBMISSION.md`, checklist item 5).
