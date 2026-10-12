"""Persistent claude.ai session via Playwright.

The gateway does not touch Claude Desktop's internal session at all. It drives a real
Chromium browser against claude.ai and persists the storage state (cookies, localStorage,
IndexedDB) so the session survives restarts. The user signs in once, interactively.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from .config import Settings


# Selectors on claude.ai's chat page. These are the version-gate contract: if claude.ai
# changes its DOM, the gateway must warn and refuse to run until updated.
SELECTORS = {
    "composer": "[data-testid='composer-input']",
    "send_button": "[data-testid='send-message-button']",
    "message_stream": "[data-testid='message-stream']",
    "final_response": "[data-testid='final-response']",
    "login_button": "text=Log in",
    "login_url": "/login",
    "new_chat": "[data-testid='new-chat-button']",
}


@dataclass
class SessionState:
    """Persisted session metadata, kept separate from the browser storage state."""

    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    claude_url: str = "https://claude.ai/"
    authenticated: bool = False
    fingerprint: str = ""  # version-gate fingerprint of claude.ai's page


class AuthManager:
    """Manages the persistent browser session on claude.ai."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.session_dir.mkdir(parents=True, exist_ok=True)
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.state = SessionState()
        self._load_state()

    def _state_path(self) -> Path:
        return self.settings.session_dir / "session_state.json"

    def _load_state(self) -> None:
        if self._state_path().is_file():
            try:
                data = json.loads(self._state_path().read_text())
                self.state = SessionState(**data)
            except Exception:
                self.state = SessionState()

    def _save_state(self) -> None:
        self._state_path().write_text(json.dumps(self.state.__dict__, indent=2))

    async def start(self) -> None:
        """Start the browser with the persisted session state, if present.

        For persistent contexts, storage state is managed automatically via the
        user_data_dir. We don't pass storage_state to launch_persistent_context.
        """
        self.playwright = await async_playwright().start()

        user_data_dir = self.settings.user_data_dir or (
            self.settings.session_dir / "browser-profile"
        )
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.settings.headless,
        )

    async def stop(self) -> None:
        """Shut down the browser. Storage state is auto-persisted by persistent context."""
        if self.context:
            await self.context.close()
            self.context = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        self._save_state()

    async def _new_page(self) -> Page:
        if not self.context:
            raise RuntimeError("Browser context not started")
        return await self.context.new_page()

    async def is_authenticated(self) -> bool:
        """Check if the current session is signed in to claude.ai."""
        if not self.context:
            return False
        page = await self._new_page()
        try:
            await page.goto(self.settings.claude_url, wait_until="domcontentloaded")
            # If redirected to login, the URL changes or a sign-in button appears
            is_login = "/login" in page.url or await page.locator(SELECTORS["login_button"]).count() > 0
            return not is_login
        finally:
            await page.close()

    async def interactive_login(self) -> bool:
        """Open a headed browser for the user to sign in manually. Returns True on success.

        Waits for the chat composer to appear, which only happens after a successful login.
        """
        if not self.context:
            await self.start()
        assert self.context
        page = await self.context.new_page()
        await page.goto(self.settings.claude_url)
        print("Please sign in to claude.ai in the opened browser window.")
        print("Use your Google account / email that has access to claude.ai.")
        print("Waiting for authentication to complete (waiting for chat composer to appear)...")

        # Poll until the chat composer appears (only visible after successful login)
        deadline = time.time() + 600  # 10 minute timeout
        authenticated = False
        while time.time() < deadline:
            try:
                await page.wait_for_selector(SELECTORS["composer"], timeout=2000)
                authenticated = True
                break
            except Exception:
                await page.wait_for_timeout(1000)
                continue
        if not authenticated:
            print("Login timed out — please try again.")
            await page.close()
            return False

        self.state.authenticated = True
        self.state.claude_url = page.url
        self._save_state()
        print("Authentication complete! Session saved (persisted automatically).")
        await page.close()
        return True

    async def send_message(self, text: str, timeout_ms: int = 120000) -> str:
        """Send a message to claude.ai and return the final response text.

        Drives the chat UI: type into the composer, click send, wait for the
        final response to appear. Raises on timeout or auth failure.
        """
        if not self.context:
            raise RuntimeError("Browser context not started")
        if not await self.is_authenticated():
            raise RuntimeError("Not authenticated to claude.ai — run interactive_login first")

        page = await self.context.new_page()
        try:
            await page.goto(self.settings.claude_url, wait_until="domcontentloaded")

            # Type the message
            await page.locator(SELECTORS["composer"]).fill(text)

            # Click send
            await page.locator(SELECTORS["send_button"]).click()

            # Wait for the final response to appear
            await page.wait_for_selector(
                SELECTORS["final_response"], timeout=timeout_ms
            )

            # Extract the text content
            response = await page.locator(SELECTORS["final_response"]).inner_text()
            return response.strip()
        finally:
            await page.close()