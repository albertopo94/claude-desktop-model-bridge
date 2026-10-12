"""CLI entry point for claude-browser-gateway."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import Settings
from .auth import AuthManager
from .chat import ChatSession
from .version_gate import VersionGate


def _supported_versions() -> str:
    """The Claude Desktop build this gateway was verified against."""
    return "Claude 2.31226.1 (857652) — build 2026-10-09T17:56:07.000Z"


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude Browser Gateway")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("start", help="Start the gateway server (default: 127.0.0.1:8315)")
    sub.add_parser("login", help="Open a headed browser for interactive claude.ai login")
    sub.add_parser("status", help="Check session authentication and health")
    sub.add_parser("version", help="Show version and supported Claude Desktop versions")
    sub.add_parser("teardown", help="Stop proxy, remove CA, restore network (for recovery)")

    args = parser.parse_args()

    if args.command == "version":
        print("claude-browser-gateway 0.1.0")
        print(f"Supported Claude Desktop: {_supported_versions()}")
        print("Version gate: warns and refuses to run if claude.ai DOM changes.")
        return 0

    if args.command == "teardown":
        print("Run: bash research/tools/capture-teardown.sh")
        return 0

    if args.command == "login":
        settings = Settings.from_env()
        session = AuthManager(settings)
        asyncio.run(_interactive_login(session))
        return 0

    if args.command == "status":
        settings = Settings.from_env()
        session = AuthManager(settings)
        if settings.session_path.is_file():
            print(f"session file present: {settings.session_path}")
        else:
            print("no session file — interactive login required")
        print(f"version gate: supported Claude Desktop = {_supported_versions()}")
        return 0

    if args.command == "start" or args.command is None:
        import uvicorn
        settings = Settings.from_env()
        uvicorn.run(
            "claude_browser_gateway.api:app",
            host=settings.host,
            port=settings.port,
            reload=False,
            log_level="warning",
        )
        return 0

    parser.print_help()
    return 2


async def _interactive_login(session: AuthManager) -> None:
    await session.start()
    ok = await session.interactive_login()
    await session.stop()
    if not ok:
        sys.exit(1)