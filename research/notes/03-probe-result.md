# One well-formed OAuth inference request — result

Command: `python3 research/tools/desktop_oauth_probe.py probe --confirm ONE_REQUEST`
Single request, no retries, no writes. New request id: `req_011Cfw6mH8FgYDusHWmQEtQu`.

    using cached entry: acct:<redacted>|<clientId:DESKTOP_OAUTH_CONFIGS>:<redacted>:…:user:inference
    token shape: len=108 prefix=sk-ant-oat…  (value not printed)
    POST https://api.anthropic.com/v1/messages
      model=claude-haiku-4-5-20251001 max_tokens=1 system=yes anthropic-beta=oauth-2025-04-20
    HTTP 403
      error.type: permission_error
      error.message: OAuth authentication is currently not allowed for this organization.

## Interpretation

The request carried everything the feasibility test omitted: `anthropic-beta: oauth-2025-04-20` and a
first `system` block with the first-party identity string from the bundle. The response is byte-for-
byte the same failure mode, with a new request id.

**H4 is excluded.** The OAuth beta header and the identity block are not the problem.

**H3 is confirmed.** `permission_error` naming the *organization* is an authorization-layer
rejection, which precedes request-body validation. Community reports for the OAuth-shape failure
modes produce 400 `invalid_request_error` or a misleading 429, never this message. So the block is
a server-side policy on this account's organization: subscription-based OAuth inference is not
enabled for it. The token, its scope and its audience are all correct; the organization is not
authorized to spend them this way.

Caveat, stated plainly: the identity string used was the one found in the bundle
(`"You are running inside the Claude desktop app (Code tab)."`). A different exact string could in
principle matter for a request that got further than this one did. It cannot change this result,
because an org-authorization check runs before any `system`-shape validation.

## Consequence

Reusing the Claude Desktop subscription for an independent local gateway is blocked by account
policy, not by our engineering. Nothing in the bridge design fixes it.

Two non-technical avenues remain, both belonging to the account holder:

1. Ask Anthropic support to enable subscription OAuth for the organization. The exact message is
   documented on Claude Code issues with staff replies describing it as a server-side organization
   setting that local configuration cannot override. Reported account details worth including: a
   personal paid plan, working chat, no admin UI found for the toggle, and one report theorizing a
   duplicate-billing state on the account.
2. Accept a credential whose audience is already authorized, which means API billing, and changes
   the "no extra cost" requirement.

The product decision is unaffected in one direction: the gateway itself is source-agnostic and
reusable from agy-model-bridge regardless of how this resolves.
