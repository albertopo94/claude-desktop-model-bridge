#!/usr/bin/env bash
# capture-run.sh — start mitmproxy capturing claude.ai traffic, redacted to shape only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$ROOT/research/raw/mitm-venv"
PROXY_PORT="${PROXY_PORT:-8080}"
LOG="/tmp/capture-chat.jsonl"
DURATION="${DURATION:-120}"

echo "clearing previous log..."; : > "$LOG"
echo "starting mitmproxy for ${DURATION}s on port ${PROXY_PORT}..."
"$VENV/bin/mitmdump" \
  --mode "regular" \
  --set "quiet=true" \
  --set "listen-port=${PROXY_PORT}" --set "eventlog=${LOG}" \
  --scripts "$ROOT/research/tools/capture-chat-addon.py" \
  --set "upstream_cert=true" \
  --set "ssl_insecure=true" \
  --flow-detail 1 &
MITM_PID=$!

sleep 3
echo "proxy running (pid $MITM_PID)."
echo "Now send ONE chat message in Claude Desktop. Then run capture-teardown.sh."
echo "Captured events (host, path, method, status, header names, body shapes only):"
echo "  tail -f $LOG"
echo
echo "Auto-stopping in ${DURATION}s. Press Ctrl-C to stop earlier."
wait "$MITM_PID" 2>/dev/null || true
echo "mitmproxy stopped. Log: $LOG"