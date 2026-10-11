# Desktop Session Recon — feature tasks

Goal: identify, with runtime evidence, whether the OAuth credential held by Claude Desktop can
authorize inference from an independent local process, and which upstream surface the app's chat
actually uses.

Blocked decision (from `notion.md`): direct reuse of the extracted credential against
`api.anthropic.com/v1/messages` returned HTTP 403 `permission_error`. Root cause unresolved.

Hypotheses to separate:

- H1 — `oauth:tokenCache` is not the chat credential; chat uses the claude.ai web session.
- H2 — correct token, wrong surface: chat travels to a different host than `api.anthropic.com`.
- H3 — real account/organization gate on subscription OAuth for the public Messages surface.

## Reversibility contract (binding for every task)

1. Read copies of app state, never the originals. No writes under
   `~/Library/Application Support/Claude`.
2. Keychain: attribute reads only, never `-w`. No add/delete/modify.
3. Prefer transient launch flags over persistent settings.
4. Record sha256 of pre-existing state before any probe; re-verify after each probe.
5. Every probe ends with a manual native-chat "OK" in Claude Desktop. On failure: restore from
   copy and stop the session.
6. At most one inference request per experiment. No header/model/route loops.
7. Never print tokens, Keychain values, authorization header values, cookies, or message bodies.
   Evidence is shape-only: host, path, method, status, header names, body key types and lengths,
   SSE event names.
8. REA is never registered into Claude Desktop. Claude Desktop receives zero config writes.

## Tasks

- [ ] T1 — Static map of the bundle with REA (CLI only, no MCP setup, no app mutation).
      Output: entry points, module graph, network-layer locations, IPC channels. Redacted notes
      only in `research/notes/`.
- [ ] T2 — Locate the inference call site: which host constant, which path, which headers, and
      whether the decrypted `oauth:tokenCache` token is read on that path. Settles H1 vs H2/H3
      statically.
- [ ] T3 — Locate credential lifecycle: where `oauth:tokenCache`/`tokenCacheV2` are written and
      read, refresh behaviour, sign-out/revocation handling.
- [ ] T4 — Runtime confirmation (P2, CDP launch flag) of the single observed chat request:
      host, path, method, status, header names, body shape, SSE event names. Only if T1/T2 leave
      ambiguity and only under the reversibility contract.
- [ ] T5 — Verdict and GO/NO-GO update in `notion.md`, with the evidence artifact and the
      post-check hashes proving the app state is unchanged.

## Evidence budget

Static analysis output stays in `research/raw/` (gitignored, may contain bundle strings).
Only redacted, shape-level findings are committed to `research/notes/`.
