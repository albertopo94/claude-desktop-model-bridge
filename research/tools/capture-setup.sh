#!/usr/bin/env bash
# capture-setup.sh — install the mitmproxy CA and route system traffic through the proxy.
# Reversible: capture-teardown.sh undoes every change in reverse order.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$ROOT/research/raw/mitm-venv"
PROXY_PORT="${PROXY_PORT:-8080}"
CA="$HOME/.mitmproxy/mitmproxy-ca-cert.cer"
BASELINE="$ROOT/research/notes/proxy-baseline.txt"
LOG="/tmp/capture-chat.jsonl"

echo "[1/4] generating CA if missing..."
if [ ! -f "$CA" ]; then
  mkdir -p "$HOME/.mitmproxy"
  "$VENV/bin/mitmdump" --set "confdir=$HOME/.mitmproxy" --listen-port 18999 >/dev/null 2>&1 &
  CA_PID=$!
  sleep 3
  kill "$CA_PID" 2>/dev/null || true
  wait "$CA_PID" 2>/dev/null || true
fi
if [ ! -f "$CA" ]; then
  echo "ERROR: CA not produced at $CA"; exit 1
fi
echo "      CA: $CA"

echo "[2/4] recording current system proxy state..."
scutil --proxy > "$BASELINE" 2>/dev/null || true
echo "      baseline -> $BASELINE"

echo "[3/4] clearing any previous capture log..."
: > "$LOG"

echo "[4/4] installing CA into the system keychain..."
security add-certificates -k $HOME/Library/Keychains/login.keychain-db "$CA" 2>/dev/null || \
  security add-certificates -k $HOME/Library/Keychains/login.keychain-db "$CA"
security find-generic-password -a "Claude Desktop" -s "claude-desktop-proxy-ca" 2>/dev/null || \
  security add-generic-password -a "Claude Desktop" -s "claude-desktop-proxy-ca" -w "$CA" $HOME/Library/Keychains/login.keychain-db 2>/dev/null || true

echo "OK — proxy port $PROXY_PORT, CA installed, baseline saved."
echo "Next: run capture-run.sh, then send ONE chat message in Claude Desktop, then capture-teardown.sh."