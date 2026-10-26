#!/usr/bin/env bash
# Start this checkout's H-MEM/World Model sidecar and its Meterless Markovian service if they are not answering. The ports come
# from SIDECAR_URL and MARKOVIAN_URL (the environment, else this checkout's .env, else 8100 and 8101), so each checkout can run
# its own. Safe to re-run: a port that already answers is left alone, and the script says whose folder serves it.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/state"; mkdir -p "$LOGS"
cd "$ROOT/services/meterless-sidecar" || exit 1
from_env() { [ -f "$ROOT/.env" ] && grep -m1 "^$1=" "$ROOT/.env" | cut -d= -f2- | tr -d '"'"'"'\r'; }
port_of() { echo "$1" | sed -n 's|.*:\([0-9][0-9]*\).*|\1|p'; }
HP=$(port_of "${SIDECAR_URL:-$(from_env SIDECAR_URL)}"); HP=${HP:-8100}
MP=$(port_of "${MARKOVIAN_URL:-$(from_env MARKOVIAN_URL)}"); MP=${MP:-8101}
up() { curl -sf --max-time 2 "http://127.0.0.1:$1/healthz" 2>/dev/null | grep -q "\"engine\""; }
owner() { pid=$(ss -ltnp 2>/dev/null | grep ":$1 " | grep -o "pid=[0-9]*" | head -1 | cut -d= -f2); [ -n "$pid" ] && readlink "/proc/$pid/cwd"; }
up "$HP" || (SIDECAR_PORT=$HP nohup npx --no-install tsx server.ts >> "$LOGS/sidecar.log" 2>&1 &)
up "$MP" || (MARKOVIAN_PORT=$MP nohup npx --no-install tsx markovian/serve.ts >> "$LOGS/markovian.log" 2>&1 &)
sleep 4
for p in "$HP" "$MP"; do
  if up "$p"; then
    o=$(owner "$p"); case "$o" in "$ROOT"/*) echo "$p up";; "") echo "$p up";; *) echo "$p up, but served from $o, not this checkout";; esac
  else echo "$p not answering yet (see state/sidecar.log, state/markovian.log)"; fi
done
