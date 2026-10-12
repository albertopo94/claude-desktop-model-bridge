# claude-browser-gateway — spec

Local gateway that exposes the Claude chat model through a real browser session on
`claude.ai`, as a standard API for other coding agents.

## Why

Claude Desktop's OAuth bearer cannot be reused independently (free tier has no billing
entitlement). The only path to the Claude model without API billing is the web session
that `claude.ai` serves. This gateway automates that session in a headless browser and
exposes it over standard protocols — the same role `agy-model-bridge` plays for
Antigravity.

## Supported clients

Any agent speaking OpenAI Chat Completions or Anthropic Messages:

- `ANTHROPIC_BASE_URL=http://127.0.0.1:8315` → Claude Code, Codex, Aider, etc.
- `OPENAI_BASE_URL=http://127.0.0.1:8315` → OpenAI-compatible agents

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/models` | Model catalog (static, from claude.ai's known model list) |
| `GET` | `/health` | Gateway + session status |
| `POST` | `/v1/chat/completions` | OpenAI Chat Completions, streaming + non-streaming |
| `POST` | `/v1/messages` | Anthropic Messages, streaming + non-streaming |

## Session lifecycle

1. **First run** — interactive login in a headed browser. User signs in to `claude.ai`
   with their free-tier account. Gateway saves the session to `~/.claude-browser-gateway/session.json`.
2. **Subsequent runs** — gateway rehydrates the session from disk. If cookies are
   expired, it refreshes automatically (see refresh policy).
3. **Shutdown** — gateway closes the browser cleanly and persists the session.

## Refresh policy

- Probe the session every `--probe-interval` (default 300s) with a lightweight request
  (e.g. fetch the conversations list).
- If the probe fails with an auth error, run a refresh: reload `claude.ai`, and if still
  failing, require interactive re-login.
- Never send more than one refresh concurrently (single-flight lock).

## Version gate

The gateway is tied to `claude.ai`'s DOM and API. It records:

- `claude.ai` build/version fingerprint (from a known script tag or response header)
- Critical selectors used by the gateway

On startup, if the fingerprint differs from the last known-good, the gateway emits a
warning and refuses to start until the operator acknowledges or upgrades the gateway.

## Rate limiting

`claude.ai` enforces free-tier limits (windowed token budget). The gateway:

- Tracks a local token budget per window
- Queues requests beyond the budget with backoff
- Returns `429` with `Retry-After` when the window is exhausted
- Never retries upstream on its own — the client retries

## Non-goals

- No multi-account support (single session)
- No conversation persistence beyond the browser session
- No prompt injection defense beyond what claude.ai provides
- No support for Claude Desktop's own app internals (that path is closed by pinning
  and by free-tier billing policy)