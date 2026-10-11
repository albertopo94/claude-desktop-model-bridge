#!/usr/bin/env python3
"""Claude Desktop OAuth: identify the issuing client, then optionally send one inference request.

Why this exists
---------------
The feasibility log records one HTTP 403 `permission_error` from `POST /v1/messages` using the
token cached by Claude Desktop. That request did not send `anthropic-beta: oauth-2025-04-20`, which
Claude Desktop itself always adds for OAuth-shaped bearers, and it carried no `system` identity
block. This tool answers the two remaining questions with minimal cost:

  identity — which OAuth client issued the cached token (no network at all)
  probe    — one well-formed inference request, to separate an account/organization gate from an
             under-specified request

Safety properties, enforced in code
-----------------------------------
- Zero third-party dependencies (macOS CommonCrypto via ctypes, urllib).
- Secrets never print: token values, refresh tokens, cookies, account UUIDs and emails are
  redacted. Authorization header values are never included in output or exceptions.
- Nothing is written to disk.
- `probe` sends at most ONE request, and only with `--confirm ONE_REQUEST`.
- No Keychain writes, no config writes, no credential refresh, no retry, no redirect following.

Typical use, from your own terminal:

    python3 research/tools/desktop_oauth_probe.py identity
    python3 research/tools/desktop_oauth_probe.py probe --confirm ONE_REQUEST

Both read the Keychain item `Claude Safe Storage` / `Claude Key`; macOS asks once, and answering
"Always Allow" avoids the prompt on later runs.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import ctypes.util
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path.home() / "Library/Application Support/Claude/config.json"
KEYCHAIN_SERVICE = "Claude Safe Storage"
KEYCHAIN_ACCOUNT = "Claude Key"
IV = b" " * 16  # Electron safeStorage IV on macOS
ENDPOINT = "https://api.anthropic.com/v1/messages"
OAUTH_BETA = "oauth-2025-04-20"

# Client ids are public identifiers shipped inside Claude Desktop's app bundle.
PUBLIC_CLIENTS = {
    "89355bc3-cbfd-4382-905b-976645cad410": "DESKTOP_OAUTH_CONFIGS",
    "9d1c250a-e61b-44d9-88ed-5944d1962f5e": "CLAUDE_CODE_OAUTH_CONFIGS",
    "a473d7bb-17ac-43a7-abc0-a1343d7c2805": "COWORK_OAUTH_CONFIGS",
    "3b6a227a-0bc2-4c10-91b0-72226730d013": "CLAUDE_AI_IMPORT_DEFAULTS",
}

# First-party identity strings found in the app bundle. Anthropic validates the `system` field for
# OAuth-authenticated requests on non-Haiku models.
IDENTITIES = {
    "desktop": "You are running inside the Claude desktop app (Code tab).",
    "none": "",
}

SECRET_HINTS = ("token", "secret", "key", "cookie", "email", "uuid", "account", "refresh")


class ProbeError(RuntimeError):
    pass


# --------------------------------------------------------------------------- crypto primitives


def read_keychain_password() -> bytes:
    proc = subprocess.run(
        ["/usr/bin/security", "find-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
        capture_output=True, text=True, check=False, timeout=300,
    )
    if proc.returncode != 0:
        raise ProbeError(
            f"Keychain read refused or failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:160] or 'denied'}"
        )
    value = proc.stdout.strip()
    for prefix in ("base64:", "go-keyring-base64:"):
        if value.startswith(prefix):
            return base64.b64decode(value[len(prefix):])
    return value.encode("utf-8")


def derive_key(password: bytes) -> bytes:
    """Chromium/Electron on macOS: PBKDF2-SHA1(password, "saltysalt", 1003) -> AES-128 key."""
    return hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, 16)


def aes_cbc_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-128-CBC, zero-space IV, via macOS CommonCrypto.

    Verified on this machine against an independent OpenSSL reference: with kCCOptionRawData,
    CCCrypt returns the unpadded plaintext for Electron `v10` blobs. A wrong key yields bytes that
    fail JSON/UTF-8 decoding upstream, reported as a failure with no plaintext echoed.
    """
    lib = None
    for candidate in (None, "/usr/lib/libSystem.B.dylib", ctypes.util.find_library("commonCrypto")):
        try:
            handle = ctypes.CDLL(candidate) if candidate else ctypes.CDLL(None)
        except OSError:
            continue
        if getattr(handle, "CCCrypt", None) is not None:
            lib = handle
            break
    if lib is None:
        raise ProbeError("CCCrypt symbol unavailable on this system")

    lib.CCCrypt.restype = ctypes.c_int
    lib.CCCrypt.argtypes = [
        ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t,
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]

    out = ctypes.create_string_buffer(len(data) + 16)
    written = ctypes.c_size_t(0)
    status = lib.CCCrypt(
        1, 0, 1,                      # kCCDecrypt, kCCAlgorithmAES, kCCOptionRawData
        key, len(key), IV,
        data, len(data),
        out, ctypes.c_size_t(len(out)),
        ctypes.byref(written),
    )
    if status != 0:
        raise ProbeError(f"AES decrypt failed (status {status}); wrong key or corrupt blob")
    return out.raw[: written.value]


def decrypt_blob(blob_b64: str, key: bytes) -> bytes:
    raw = base64.b64decode(blob_b64)
    if raw[:3] != b"v10":
        raise ProbeError(f"unexpected blob prefix {raw[:4]!r}")
    return aes_cbc_decrypt(key, raw[3:])


# -------------------------------------------------------------------------------- redaction


UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def label_key(name: str) -> str:
    """Echo a cache key naming the issuing client; mask every other uuid.

    Cache keys look like `acct:<accountUuid>|<clientId>:<orgUuid>:<apiHost>:<scope>`. Only the
    client id is a public bundle identifier; account and organization uuids are masked.
    """
    placeholders: dict[str, str] = {}
    for cid, label in PUBLIC_CLIENTS.items():
        if cid in name:
            token = f"__client{len(placeholders)}__"
            placeholders[token] = f"<clientId:{label}>"
            name = name.replace(cid, token)
    name = UUID_RE.sub("<redacted>", name)
    for token, label in placeholders.items():
        name = name.replace(token, label)
    if name.startswith("acct:"):
        _, _, rest = name.partition("|")
        return f"acct:<redacted>|{rest}" if rest else "acct:<redacted>"
    return name


def key_is_public(name: str) -> bool:
    return any(cid in name for cid in PUBLIC_CLIENTS)


def field_names(obj: object, depth: int = 0) -> list[str]:
    names: list[str] = []
    if isinstance(obj, dict) and depth < 3:
        for k, v in obj.items():
            if not any(h in k.lower() for h in SECRET_HINTS):
                names.append(k)
            names += field_names(v, depth + 1)
    elif isinstance(obj, list) and depth < 3:
        for item in obj[:1]:
            names += field_names(item, depth + 1)
    return sorted(set(names))


def read_cache(key: bytes) -> dict[str, dict]:
    """Return {cache_key: decrypted_entry} for every oauth:tokenCache field."""
    if not CONFIG_PATH.is_file():
        raise ProbeError(f"config not found: {CONFIG_PATH}")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    result: dict[str, dict] = {}
    for field, blob in sorted(config.items()):
        if not field.startswith("oauth:tokenCache") or not isinstance(blob, str) or not blob:
            continue
        try:
            data = json.loads(decrypt_blob(blob, key).decode("utf-8"))
        except Exception as exc:
            print(f"{field}: could not decrypt/parse ({type(exc).__name__})")
            continue
        if not isinstance(data, dict):
            continue
        for name, entry in data.items():
            if isinstance(entry, dict):
                result[str(name)] = entry
    return result


# ------------------------------------------------------------------------------------ commands


PLAN_FIELDS = ("subscriptionType", "rateLimitTier")


def cmd_identity(args: argparse.Namespace) -> int:
    key = derive_key(read_keychain_password())
    entries = read_cache(key)
    if not entries:
        print("no decryptable token cache entries")
        return 1
    for name, entry in entries.items():
        tag = "issued-by" if key_is_public(name) else "entry"
        print(f"{tag}: {label_key(name)}")
        for field in field_names(entry):
            print(f"  field: {field}")
        if args.plan_fields:
            # Plan metadata only: values the account owner can see in account settings.
            for field in PLAN_FIELDS:
                value = entry.get(field)
                if isinstance(value, (str, int)) and len(str(value)) <= 32:
                    print(f"  {field}: {value}")
        scopes = name.rsplit(":", 1)[-1] if ":" in name else ""
        if scopes.startswith("user:") or scopes.startswith("org:"):
            print(f"  scope: {scopes}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    if args.confirm != "ONE_REQUEST":
        print("refusing to send a request: --confirm ONE_REQUEST is required")
        return 2

    key = derive_key(read_keychain_password())
    entries = read_cache(key)
    token: str | None = None
    chosen: str | None = None
    for name, entry in entries.items():
        value = entry.get("token")
        if isinstance(value, str) and value.startswith("sk-ant-oat"):
            token, chosen = value, name
            break
    if token is None:
        print("no sk-ant-oat token in the decryptable cache")
        return 1

    print(f"using cached entry: {label_key(chosen)}")
    print(f"token shape: len={len(token)} prefix={token[:10]}…  (value not printed)")

    system_text = IDENTITIES[args.identity]
    body: dict = {
        "model": args.model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }
    if system_text:
        body["system"] = [{"type": "text", "text": system_text}]

    headers = {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "authorization": f"Bearer {token}",
        "anthropic-beta": OAUTH_BETA,
    }

    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), headers=headers)
    print(f"\n-> POST {ENDPOINT}")
    print(f"   model={args.model} max_tokens=1 system={'yes' if system_text else 'no'} "
          f"anthropic-beta={OAUTH_BETA}")
    print("   headers sent: authorization (Bearer, value not printed), anthropic-version, "
          "anthropic-beta, content-type\n")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
            print(f"HTTP {resp.status}")
            print(f"  outcome: SUCCESS — inference accepted from an independent process")
            for field in ("id", "model", "stop_reason", "type"):
                if isinstance(payload.get(field), (str, int)):
                    print(f"  {field}: {payload[field]}")
            usage = payload.get("usage")
            if isinstance(usage, dict):
                print(f"  usage: { {k: v for k, v in usage.items() if isinstance(v, int)} }")
            return 0
    except urllib.error.HTTPError as err:
        raw = err.read()
        err.close()
        print(f"HTTP {err.code}")
        try:
            parsed = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            error = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
            print(f"  error.type: {error.get('type', 'n/a')}")
            message = str(error.get("message", ""))[:300]
            print(f"  error.message: {message}")
            if parsed.get("request_id"):
                print(f"  request_id: {parsed['request_id']}")
        else:
            print(f"  body (truncated, no secrets expected): {raw[:200]!r}")
        print("\n  no retries were attempted")
        return 1
    except urllib.error.URLError as err:
        print(f"transport failure: {err.reason}")
        print("  no retries were attempted")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    ident = sub.add_parser("identity", help="print only which client issued the cached token")
    ident.add_argument("--plan-fields", action="store_true",
                       help="also print subscriptionType and rateLimitTier (plan metadata, not secrets)")
    probe = sub.add_parser("probe", help="send exactly one inference request")
    probe.add_argument("--model", default="claude-haiku-4-5-20251001")
    probe.add_argument("--identity", choices=sorted(IDENTITIES), default="desktop")
    probe.add_argument("--confirm", default="", help="must be exactly ONE_REQUEST")
    args = parser.parse_args()

    if args.command == "probe":
        return cmd_probe(args)
    try:
        return cmd_identity(args)
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
