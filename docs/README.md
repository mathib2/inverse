# What's where

## How the crew works (current)

| document | what it covers |
|---|---|
| [CREW.md](CREW.md) | The eight agents, what each one does, how they talk, how to add one. |
| [AGENT_STRUCTURE.md](AGENT_STRUCTURE.md) | The shape every agent shares: its record, its loop, how it is measured. |
| [WARDEN.md](WARDEN.md) | Warden, the loop that runs missions on its own (queued goals, standing missions, new data), and how the agents talk during a mission (the message bus). |
| [TINKER.md](TINKER.md) | Tinker, the loop that works on the crew's own code: research, one edit, tests, probe, council, veto window, phone alerts. |
| [COUNCIL.md](COUNCIL.md) | How agents propose changes to the crew, how a session decides, and how a change is undone. |
| [BENCH.md](BENCH.md) | The benchmark rounds on the workstation's CPU and on Nightshift, what each one changed, where the time goes, and what the hardware allows. |
| [AGENT_REPORT.md](AGENT_REPORT.md) | Each agent's mark out of ten and its flaws. Its numbered list is Tinker's backlog: the path is fixed, code reads it. |

## Running it (operations)

| document | what it covers |
|---|---|
| [operations/ACCESS.md](operations/ACCESS.md) | Getting in: the public link, the tailnet, the sign-in page, a permanent link through Tailscale Funnel, and access to the code. |
| [operations/NIGHTSHIFT_TUNNEL.md](operations/NIGHTSHIFT_TUNNEL.md) | Meterless Nightshift, the primary provider: Nemotron-Mini-4B on a Windows laptop's GPU, reached through an SSH reverse tunnel. How it is set up, how to set it up once, and how to tell what is wrong. |
| [operations/LOCAL_MODELS.md](operations/LOCAL_MODELS.md) | The workstation's own Ollama: the fallback when Nightshift cannot answer, and the provider of Tinker's sandbox. Its models, how the lanes map to them, and what was measured on the workstation's CPU. |

## The hackathon submission

[hackathon/](hackathon/) holds the submission package for the Open Agent Hackathon 2026: [SUBMISSION.md](hackathon/SUBMISSION.md)
(the form and its checklist), [SPONSORS.md](hackathon/SPONSORS.md) and [ENGINE_EVIDENCE.md](hackathon/ENGINE_EVIDENCE.md) (where
each sponsor's technology does real work), [PREEXISTING.md](hackathon/PREEXISTING.md), [DEMO_SCRIPT.md](hackathon/DEMO_SCRIPT.md)
and [SLIDES.md](hackathon/SLIDES.md). After judging the folder moves to `archive/`.

## Records

- [evidence/](evidence/): what the crew actually did, kept as data: probes, benchmark rounds, Tinker's engineer evaluations, three missions (one is the video's replay) and the engines' conformance runs. See [evidence/README.md](evidence/README.md).
- [archive/](archive/): finished plans and dated snapshots, kept for history: the old experts guide, the 25 October rating, and the improvement plan, whose items carry their status on 27 October.
- `../CHANGELOG.md`: what changed, day by day.
