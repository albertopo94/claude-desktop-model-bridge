# Static recon of Claude Desktop 2.31226.1

Target: `/Applications/Claude.app/Contents/Resources/app.asar`, sha256 `08446bcf…b6bc5b`,
analyzed from a working copy under `research/raw/` (never the original).

Method: REA `analyze-javascript-application` (graph + Electron boundaries) plus targeted string
and source-range reads of the extracted bundle. All findings below are **identifier-level**:
OAuth client IDs, hostnames, paths, header names, env-var names. No token, secret, header value,
or message content was read or recorded.

Primary bundle: `.vite/build/index.chunk-Cyt2WTko.js` (6.88 MB, main process). It is the only
file containing `oauth:tokenCache`, `"/v1/messages"` and `api.anthropic.com` together.

## Finding A — four OAuth clients share one apiHost

All resolve `apiHost = https://api.anthropic.com` (constant `iO`) in production. Client IDs are
public identifiers embedded in the shipped bundle, not secrets.

| Exported config | production clientId | scope | redirectUri |
| --- | --- | --- | --- |
| `DESKTOP_OAUTH_CONFIGS` | `89355bc3-cbfd-4382-905b-976645cad410` | `user:inference` | `https://claude.ai/desktop/callback` |
| `CLAUDE_CODE_OAUTH_CONFIGS` | `9d1c250a-e61b-44d9-88ed-5944d1962f5e` | `user:inference user:file_upload user:profile` | `https://console.anthropic.com/oauth/code/callback` |
| `COWORK_OAUTH_CONFIGS` | `a473d7bb-17ac-43a7-abc0-a1343d7c2805` | above + `user:sessions:claude_code` | console callback |
| `CLAUDE_AI_IMPORT_DEFAULTS` | `3b6a227a-0bc2-4c10-91b0-72226730d013` | (issuer + claude.ai origin) | — |

The credential observed in `config.json` carried scope `user:inference` with no `user:profile`.
That scope matches `DESKTOP_OAUTH_CONFIGS` exactly. The cache key format is
`[acct:<accountUuid>|]<clientId>:<apiHost>:<scope>`, so the cached key string itself names the
issuing client — **which client minted the token is readable from the key without touching the
token value.** Not done: it requires a Keychain read (`security … -w`), held pending authorization.

## Finding B — the chat does not use the OAuth bearer (H1 confirmed)

The main window loads `https://claude.ai`. Requests to the app's own hosts pass through a
`webRequest.onBeforeSendHeaders` hook that injects **client-identification** headers only:
`anthropic-client-os-platform`, `anthropic-client-os-version`, `anthropic-desktop-topbar: 1`, and
the `anthropic-client-app` family. It actively **strips** `x-authorization` and never injects
`Authorization`. Authentication for the chat is the web session, not the bearer.

Corollary: the `oauth:tokenCache` bearer is a secondary credential, not the chat's inference path.

## Finding C — what the `user:inference` bearer is actually used for

Observed consumers of the bearer against `api.anthropic.com`: `/api/oauth/profile`, an EventLogging
telemetry token mint, the preview blocklist, Chrome-extension MCP pairing
(`scope: user:inference user:office`), and OTLP export under `authMode: "inference-credential"`.
These are desktop support features, not conversation inference. All of them hit the same
authorization gate that returned the 403.

## Finding D — the 403 is likely audience/client scope, not a broken token

In this build `"/v1/messages"` appears inside a **provider abstraction** (`inferenceProvider`,
`inferenceGatewayAuthScheme`, `inferenceGatewayHeaders`, `baseUrl`, `adminHeaders`,
`classifyFailure`) with probe methods such as `ytn` posting `max_tokens: 1` — a configurable
third-party/self-hosted provider surface (`3p`, `vertex`, `bedrock`, `gateway`), not the app's
own first-party chat path.

First-party inference resolves a **gateway origin**: `gatewayOrigin()` returns the credential's
`baseUrl` origin only when `provider === "gateway"`, and the code refuses keys sent as `x-api-key`
("keys sent as x-api-key are not forwarded"). No `a-api.anthropic.com` string exists anywhere in
the bundle — the `a-api.anthropic.com/v1/m` route reported from logs was a parsing artifact.

So: posting a Desktop-minted bearer to the public `api.anthropic.com/v1/messages` is off-label for
that credential. **The gateway origin for a first-party subscription is not a literal in the
bundle** — it is supplied at runtime. That is the remaining unknown, and it is not answerable
statically.

## Finding E — the app itself spawns an agent runtime with bearer + base URL

The bundle downloads Claude Code from `downloads.claude.ai/claude-code-releases` and launches it
with an environment allowlist. Inherited `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN` are **stripped** from the child environment,
then fresh values are materialized per session: `credentialEnvVar()` yields `ANTHROPIC_AUTH_TOKEN`
for bearer and `ANTHROPIC_API_KEY` for `x-api-key`, with ephemeral
`host-creds-<uuid>.json` files in userData that are rotated and unlinked.

This matters for product shape: Anthropic's own supported consumption path for a bearer plus a
base URL is "hand it to an agent runtime as env vars". That is the same interface the bridge needs
to expose, and it is a legitimate reference design rather than a protocol to imitate.

## Finding F — the gateway config surface is third-party only

The inference provider schema gates the whole gateway concept to third-party deployments:

- `inferenceGatewayBaseUrl` → `provider: "gateway"`, `support.enabled.scopes: ["3p"]`, available
  from build 1.2581.0, with `originPinned` policy and a fail-closed stand-in host.
- Sibling keys under the same 3p gate: `inferenceGatewayApiKey`, `inferenceGatewayHeaders`,
  `inferenceGatewayOidc` / `OidcAuthFlow`, `inferenceGatewayAuthScheme` (`bearer` or `x-api-key`),
  `inferenceProvider` (values include `mantle`, `vertex`, `bedrock`, `gateway`).
- The validator warns when an Anthropic-host gateway `baseUrl` is paired with a non-`x-api-key`
  scheme — i.e. the only supported Anthropic-host route in this surface is **`x-api-key`**,
  which is API billing, not subscription reuse.

There is no first-party, subscription-authenticated inference endpoint in the app's configuration
surface. The gateway origin observed in `gatewayOrigin()` exists to serve 3p/enterprise
configuration that was never delivered to this installation, which is consistent with the empty
local bootstrap config (`config.json` carries no bootstrap, gateway, provider or deployment key).

## Runtime probe attempted and abandoned (CDP)

Launching the binary directly with `--remote-debugging-port=9222` bound nothing: `curl
127.0.0.1:9222/json/version` returned no response within the probe window. The app was quit
beforehand, so this is not single-instance hand-off; remote debugging is disabled in this build.
No further runtime observation is available by that route.

The CDP probe was then judged unnecessary: its question (which origin authenticates the native
chat) is already answered statically by Finding B, and neither branch it could have produced
would change the decision. One mutating action was spent establishing that, then stopped.

## Consequences for the GATE / NO-GO decision

- H1 (**token is not the chat credential**): **confirmed.** Finding B.
- H2 (**wrong surface**): **resolved as "no such surface for this account".** The bearer has no
  first-party inference endpoint to aim at: the gateway route is gated to `3p` and its Anthropic-host
  variant is `x-api-key`-only (Finding F). `a-api.anthropic.com` does not exist in the bundle.
- H3 (**account-level gate**): **not excludable and now not worth excludng.** Any test that could
  separate H3 from audience mismatch needs a paid or interactive action, not more reading.

What the evidence does **not** support: that a different header, model, path, or retry would have
produced a 200. That was already the standing conclusion in the feasibility log and the static
recon strengthens it.

Decisive next observations, in cost order:

1. **Cache-key identity** (no traffic, no mutation): read the Keychain item to decrypt only the
   cache *key* and report which clientId issued the token. Distinguishes Desktop vs Claude Code
   audience and would largely explain the 403.
2. **One chat turn, shape only**: record which origin carries the inference request and which auth
   header it carries. Branches the design: cookie-authenticated web conversation API (heavy,
   version-fragile) versus bearer-authenticated gateway origin (then a single authorized probe of
   that origin, which has never been attempted).

Constraint carried forward: no repeated probing of any endpoint, and every reversible mutation
must be restored and verified against `state-baseline.sha256`.
