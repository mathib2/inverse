#!/usr/bin/env bash
# Start the H-MEM/World Model sidecar (8100) and the Meterless Markovian service (8101) if they are not answering. Safe to re-run:
# a service that already answers /healthz is left alone (another checkout may be serving it).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/state"; mkdir -p "$LOGS"
cd "$ROOT/services/meterless-sidecar" || exit 1
up() { curl -sf --max-time 2 "http://127.0.0.1:$1/healthz" 2>/dev/null | grep -q "\"engine\""; }
up 8100 || (nohup npx --no-install tsx server.ts >> "$LOGS/sidecar.log" 2>&1 &)
up 8101 || (MARKOVIAN_PORT=8101 nohup npx --no-install tsx markovian/serve.ts >> "$LOGS/markovian.log" 2>&1 &)
sleep 4
for p in 8100 8101; do up "$p" && echo "$p up" || echo "$p not answering yet (see state/sidecar.log, state/markovian.log)"; done
