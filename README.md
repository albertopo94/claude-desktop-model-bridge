# Claude Desktop Model Bridge

Research project to evaluate whether a local inference gateway can reuse the session that
Claude Desktop keeps on macOS, and expose it as a standard model endpoint for other coding
agents.

**Status: research / feasibility.** No implementation is authorized yet. See
[`notion.md`](notion.md) for the evidence log and the current decision.

## Current decision

**NO-GO** for the direct method tested so far: the OAuth credential extracted from Claude
Desktop's local config was decrypted successfully and rejected by `api.anthropic.com` with
HTTP 403 `permission_error` — `OAuth authentication is currently not allowed for this
organization`. The root cause is unresolved.

Proven: local extraction and decryption.
Not proven: independent inference, streaming, tool calling, session renewal.

## Relationship to agy-model-bridge

This project follows the same shape as
[agy-model-bridge](https://github.com/albertopo94/agy-model-bridge), which bridges the Google
Cloud Code Assist backend used by Google Antigravity to standard client protocols. The
intended source here is Anthropic via Claude Desktop instead.

The two sources are not symmetric:

| | agy-model-bridge | this project |
| --- | --- | --- |
| Source | Google Antigravity | Claude Desktop (Electron shell of claude.ai) |
| Credential | OAuth token in macOS Keychain, plaintext JSON | OAuth token in local `config.json`, encrypted with a Keychain key |
| Upstream | Undocumented `v1internal` Google endpoints | Undocumented application API of claude.ai |
| Translation cost | High (Anthropic/OpenAI to Google dialect) | Unknown — the inference path is not identified yet |

## Ground rules for this research

- Never print tokens, Keychain values, authorization headers, or decrypted payloads.
- Never modify, rotate, or refresh local credential caches.
- Never loop requests to probe the server.
- Investigation tooling must leave Claude Desktop in its original configuration: read copies
  of state files, use transient launch flags instead of persistent settings, and restore any
  change made to enable an observation.
- Treat internal formats as unspecified details that may change between app versions.

## Layout

- `notion.md` — feasibility investigation, evidence log, and GO/NO-GO decision.
