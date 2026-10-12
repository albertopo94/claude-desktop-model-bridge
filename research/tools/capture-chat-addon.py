"""mitmproxy addon: capture one Claude Desktop chat turn, redacted to shape only.

Every captured line is host, path, method, status, header NAMES, and body key/length
shapes. Authorization and Cookie header VALUES, message bodies, and any token-shaped
string are never written to disk or to the terminal.

Run from the isolated venv, e.g.:

    research/raw/mitm-venv/bin/mitmdump \
        --mode regular:8080 --set quiet=true \
        --scripts research/tools/capture-chat-addon.py \
        --set eventlog=/tmp/capture-chat.jsonl
"""

import json
import re

# Never log these header names' values; names themselves are fine to keep.
SENSITIVE_HEADERS = {
    "authorization", "cookie", "set-cookie", "x-csrf-token", "x-xsrf-token",
    "x-api-key", "x-ant-",
}
# Never write these tokens anywhere, even in redacted form.
TOKEN_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}", re.I)
KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{10,}", re.I)
SECRET_RE = re.compile(r"Bearer [A-Za-z0-9_\-\.]{20,}", re.I)


def _shape(value, depth=0):
    """Return a structural description: type plus length for containers."""
    if isinstance(value, dict):
        if depth >= 3:
            return f"object({len(value)})"
        return {k: _shape(v, depth + 1) for k, v in list(value.items())[:12]}
    if isinstance(value, list):
        if depth >= 3:
            return f"array({len(value)})"
        return [_shape(v, depth + 1) for v in value[:3]]
    if isinstance(value, str):
        return f"str({len(value)})"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return type(value).__name__
    if value is None:
        return "null"
    return type(value).__name__


def _redact(text):
    """Strip token-like and bearer strings from any text we are about to log."""
    text = SECRET_RE.sub("Bearer <redacted>", text)
    text = TOKEN_RE.sub("sk-ant-<redacted>", text)
    text = KEY_RE.sub("sk-<redacted>", text)
    return text


def _record(entry):
    """Write one redacted event to the event log."""
    try:
        with open("/tmp/capture-chat.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def request(flow):
    url = flow.request.pretty_url
    if "claude.ai" not in url:
        return
    try:
        body = flow.request.content.decode("utf-8", "replace") if flow.request.content else ""
        parsed = json.loads(body) if body and body.strip().startswith("{") else None
    except Exception:
        parsed = None
    entry = {
        "dir": "request",
        "host": url.split("://", 1)[-1].split("/", 1)[0],
        "path": "/" + url.split("/", 3)[-1] if "/" in url.split("://", 1)[-1] else "/",
        "method": flow.request.method,
        "headers": {
            name: "<value>" for name in flow.request.headers
            if name.lower() not in SENSITIVE_HEADERS
        },
        "body_keys": list(parsed.keys()) if isinstance(parsed, dict) else None,
        "body_shape": _shape(parsed) if parsed is not None else None,
    }
    _record(entry)


def response(flow):
    url = flow.request.pretty_url
    if "claude.ai" not in url:
        return
    try:
        body = flow.response.content.decode("utf-8", "replace") if flow.response.content else ""
        parsed = json.loads(body) if body and body.strip().startswith("{") else None
    except Exception:
        parsed = None
    entry = {
        "dir": "response",
        "host": url.split("://", 1)[-1].split("/", 1)[0],
        "path": "/" + url.split("/", 3)[-1] if "/" in url.split("://", 1)[-1] else "/",
        "method": flow.request.method,
        "status": flow.response.status_code,
        "headers": {
            name: "<value>" for name in flow.response.headers
            if name.lower() not in SENSITIVE_HEADERS
        },
        "body_keys": list(parsed.keys()) if isinstance(parsed, dict) else None,
        "body_shape": _shape(parsed) if parsed is not None else None,
    }
    _record(entry)