#!/usr/bin/env bash
# Start the H-MEM sidecar and the Streamlit UI. Zetaris and obs-service must already be running (docker).
set -e
cd "$(dirname "$0")/.."
scripts/run_sidecars.sh                      # H-MEM/World Model sidecar (8100) and Meterless Markovian (8101), only if not already up
sleep 4
PYTHONPATH=core .venv/bin/streamlit run ui/app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
