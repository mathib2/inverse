# Scripts

Run everything from the checkout root with `PYTHONPATH=core .venv/bin/python <script>`.

**What runs all the time** (the workstation's services; their paths are fixed, the control scripts start them):

| file | what it is |
|---|---|
| `watch.py` | Warden's loop: queued goals, standing missions, new sensor data, the phone digest. Started by `inverse-watch`. |
| `tinker.py` | Tinker's loop: picks an item, researches, edits in the sandbox, tests, probes, asks the council. Started by `inverse-tinker`. |
| `public_link.py` | The public HTTPS link to the page (Cloudflare quick tunnel). Started by `inverse-public`. |
| `inverse-watch`, `inverse-tinker`, `inverse-public` | Control scripts: `start`, `stop`, `restart`, `status`, `log`. Installed in `~/.local/bin`. |
| `deploy-live` | Pulls the latest code into `~/inverse-live` and restarts the page and Warden; waits for a running mission first. |
| `run_sidecars.sh`, `run_demo.sh` | Start the memory and Markovian services, and the page, on a fresh machine. |

**Measuring the crew** (`measure/`): `bench.py` with `bench_cases.yaml` (eight checkable goals), `probe.py` (each agent alone,
marked out of ten), `warmup.py` (fills the model server's prompt cache), `engineer_eval.py` (a model as Tinker's engineer).

**One-off admin** (`admin/`): `set_password.py` (the page's sign-in), `send_alert.py` (a test alert to the phone), `council.py`
(file, list or decide proposals by hand), `run_team.py` (one mission from the shell), `setup_zetaris.py` and `zsql.py` (the data
platform's tables, from `data/zetaris/`).
