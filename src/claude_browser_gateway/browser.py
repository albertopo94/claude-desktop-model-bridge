"""Playwright-based browser manager and persistent session handler."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Playwright, async_playwright

from .config import Settings


class SessionManager:
    """Manages the persistent browser session on claude.ai."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None

    async def start(self) -> None:
        """Start the browser with the persisted session state, if present."""
        self.settings.session_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = await async_playwright().start()

        storage_state = (
            str(self.settings.storage_state_path)
            if self.settings.storage_state_path.is_file()
            else None
        )

        user_data_dir = self.settings.user_data_dir or (
            self.settings.session_dir / "browser-profile"
        )
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.settings.headless,
            storage_state=storage_state,
        )

    async def save_storage_state(self) -> None:
        """Persist the current storage state to disk."""
        if self.context:
            await self.context.storage_state(path=str(self.settings.storage_state_path))

    async def is_authenticated(self) -> bool:
        """Check if the current session is signed in to claude.ai."""
        if not self.context:
            return False
        page = await self.context.new_page()
        try:
            await page.goto(self.settings.claude_url, wait_until="domcontentloaded")
            # If redirected to login, the URL changes or a sign-in button appears
            is_login = "/login" in page.url or await page.locator("text=Log in").count() > 0
            return not is_login
        finally:
            await page.close()

    async def interactive_login(self) -> None:
        """Launch a headed browser for the user to sign in manually."""
        if not self.context:
            await self.start()
        assert self.context
        page = await self.context.new_page()
        await page.goto(self.settings.claude_url)
        print("Please sign in to claude.ai in the opened browser window.")
        print("Waiting for authentication to complete...")
        # Poll until the page indicates authentication
        while True:
            await page.wait_for_timeout(2000)
            if "/login" not in page.url and await page.locator("text=Log in").count() == 0:
                break
        await self.save_storage_state()
        print("Authentication complete! Session saved.")
        await page.close()

    async def stop(self) -> None:
        """Save session state and shut down the browser."""
        if self.context:
            await self.save_storage_state()
            await self.context.close()
            self.context = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None