# Claude Browser Gateway

Source-agnostic gateway architecture, ported from the verified design of
`agy-model-bridge`. The Claude subscription source is implemented as a
placeholder (`TokenProvider` protocol matching `bridge/auth.py`) and stays
dark until either (a) the organization-level authorization is lifted, or
(b) a different first-party Claude subscription credential with the correct
audience is provided.

No attempt is made to observe, replay, or extract the Claude Desktop session
without explicit user authorization. The captured `claude-desktop-model-bridge`
work (notebook `research/notes/`) shows exactly what was verified, what was
retracted, what the correct request shape looks like, and why free tier has no
subscription OAuth entitlement.

## Status

- **Source (Desktop free-tier)**: blocked at organization level (HTTP 403).
- **Bridge (source-agnostic)**: scaffolded (`src/claude_browser_gateway/`),
  with session-manager (Playwright) and FastAPI layer.
- **Extraction tool (`desktop_oauth_probe.py`)**: verified with fabricated
  payloads, protects secrets, runs with `--confirm ONE_REQUEST` gate.
- **Version gate**: `version` CLI prints the supported Claude Desktop
  version tied to the verified bundle (`2.31226.1`, build 2026-10-09).

## Usage (once a source is authorized)

```bash
# Fresh interactive login to claude.ai (headed browser; saves session)
claude-browser-gateway login

# Start the gateway
claude-browser-gateway start

# Probe one request (only after identity is confirmed)
python3 research/tools/desktop_oauth_probe.py probe --confirm ONE_REQUEST
```

No package upload or release has been made; no code is intended to run
against Claude Desktop's internal session without the user's explicit,
single-request authorization.
