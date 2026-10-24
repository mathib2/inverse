#!/usr/bin/env bash
# Start the H-MEM sidecar and the Streamlit UI. Zetaris and obs-service must already be running (docker).
set -e
cd "$(dirname "$0")/.."
(cd services/meterless-sidecar && nohup npx tsx server.ts > /tmp/sidecar.log 2>&1 &)
(cd services/meterless-sidecar && nohup npx tsx markovian/serve.ts > /tmp/markovian.log 2>&1 &)   # Meterless Markovian for long reviews
sleep 4
PYTHONPATH=core .venv/bin/streamlit run ui/app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
