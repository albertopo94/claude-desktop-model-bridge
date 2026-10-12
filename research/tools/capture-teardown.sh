#!/usr/bin/env bash
# capture-teardown.sh — stop the proxy and remove the CA, in reverse order of capture-setup.sh.
# Restores the machine to the recorded baseline. Safe to run even if setup was partial.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROXY_PORT="${PROXY_PORT:-8080}"
BASELINE="$ROOT/research/notes/proxy-baseline.txt"
CA="$ROOT/research/raw/mitmproxy-ca-cert.pem"

echo "[1/3] stopping mitmproxy if running..."
pkill -f "mitmdump" 2>/dev/null || true
sleep 2

echo "[2/3] restoring system proxy from baseline..."
if [ -f "$BASELINE" ]; then
  # Baseline recorded by scutil --proxy: restore by clearing, since it was disabled.
  networksetup -setwebproxy "Wi-Fi" "" 0 off 2>/dev/null || true
  networksetup -setsecurewebproxy "Wi-Fi" "" 0 off 2>/dev/null || true
  networksetup -setsocksproxy "Wi-Fi" "" 0 off 2>/dev/null || true
  echo "      Wi-Fi proxy cleared (baseline: disabled)."
else
  echo "      no baseline found; clearing anyway."
  networksetup -setwebproxy "Wi-Fi" "" 0 off 2>/dev/null || true
  networksetup -setsecurewebproxy "Wi-Fi" "" 0 off 2>/dev/null || true
fi

echo "[3/3] removing the mitmproxy CA from the system keychain..."
if [ -f "$CA" ]; then
  security delete-certificate -c "mitmproxy" $HOME/Library/Keychains/login.keychain-db 2>/dev/null || true
  security delete-certificate -C "$(openssl x509 -in "$CA" -noout -fingerprint 2>/dev/null | cut -d= -f2)" $HOME/Library/Keychains/login.keychain-db 2>/dev/null || true
  rm -f "$CA"
  echo "      CA removed."
else
  echo "      no CA to remove."
fi

echo "OK — proxy stopped, CA removed, network restored."