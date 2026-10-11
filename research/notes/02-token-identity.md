# Which OAuth client issued the Claude Desktop token

Command: `python3 research/tools/desktop_oauth_probe.py identity` (no network, reads local config +
Keychain item, redacted output).

    issued-by: acct:<redacted>|<clientId:DESKTOP_OAUTH_CONFIGS>:<redacted>:https://api.anthropic.com:user:inference
      field: expiresAt
      field: rateLimitTier
      field: subscriptionType

`oauth:tokenCacheV2` decrypts to an empty object, so there is exactly one cached credential.

## What this settles

The credential is issued to `DESKTOP_OAUTH_CONFIGS` (clientId `89355bc3-…`), the Claude Desktop app
identity, with scope exactly `user:inference`. Key shape is
`acct:<accountUuid>|<clientId>:<orgUuid>:<apiHost>:<scope>`; account and org uuids are masked.

So the earlier scope-based inference in the feasibility log was right, and it is now proven rather
than inferred. It also rules out the "wrong client audience" theory as a *simple* explanation: the
token carries exactly the scope its client asks for, and `user:inference` is the inference scope.

## What this does not settle

Whether the organization is authorized to use that scope from an independent process. Both
remaining causes survive:

- **H3** — account/organization gate on subscription OAuth. Best fit for the exact 403 text seen.
- **H4** — the earlier test request was under-specified for OAuth authentication: no
  `anthropic-beta: oauth-2025-04-20`, no first `system` identity block. Untested until now.

Only a correctly-shaped request separates them. `desktop_oauth_probe.py probe` sends exactly one.
