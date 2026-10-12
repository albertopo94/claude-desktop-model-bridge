"""Chat session driver: turns a conversation into claude.ai messages and back.

This is the source-agnostic inference layer. It converts a list of turns (system,
user, assistant) into a single prompt sent to the chat UI, reads the streamed
response, and yields text deltas. The same layer is reused for any upstream
that exposes a chat interface — the Claude Desktop path is simply one provider.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from .auth import AuthManager, SELECTORS
from .config import Settings


@dataclass
class Turn:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatSession:
    """A conversation with the Claude chat interface."""

    auth: AuthManager
    settings: Settings
    turns: list[Turn] = field(default_factory=list)

    def add_turn(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))

    def build_prompt(self) -> str:
        """Compose the conversation into a single prompt for the chat UI.

        claude.ai's chat is single-turn-per-message with conversation history
        maintained by the page itself. We therefore send the latest user turn
        plus a compact history prefix so the model retains context.
        """
        parts: list[str] = []
        for turn in self.turns:
            if turn.role == "system":
                parts.append(f"[system]\n{turn.content}")
            elif turn.role == "user":
                parts.append(f"[user]\n{turn.content}")
            elif turn.role == "assistant":
                parts.append(f"[assistant]\n{turn.content}")
        return "\n\n".join(parts)

    async def send(self, user_message: str, timeout_ms: int = 120000) -> str:
        """Send a user message and return the final assistant response."""
        self.add_turn("user", user_message)
        response = await self.auth.send_message(user_message, timeout_ms=timeout_ms)
        self.add_turn("assistant", response)
        return response

    async def stream(self, user_message: str, timeout_ms: int = 120000) -> AsyncIterator[str]:
        """Send a user message and yield text deltas as they appear.

        claude.ai streams the response in the DOM. We poll the message stream
        element and yield new text as it grows. This is a polling-based stream,
        not a true SSE — acceptable for a gateway that proxies a web UI.
        """
        self.add_turn("user", user_message)
        page = await self.auth.context.new_page()
        try:
            await page.goto(self.settings.claude_url, wait_until="domcontentloaded")
            await page.locator(SELECTORS["composer"]).fill(user_message)
            await page.locator(SELECTORS["send_button"]).click()
            await page.wait_for_selector(SELECTORS["final_response"], timeout=timeout_ms)

            last_text = ""
            deadline = time.time() + timeout_ms / 1000
            while time.time() < deadline:
                try:
                    text = await page.locator(SELECTORS["final_response"]).inner_text()
                except Exception:
                    text = ""
                if text and text != last_text:
                    delta = text[len(last_text):] if text.startswith(last_text) else text
                    if delta:
                        yield delta
                    last_text = text
                # Stop when the response stops growing for 5 seconds
                if last_text:
                    await asyncio.sleep(1.0)
                    new_text = await page.locator(SELECTORS["final_response"]).inner_text()
                    if new_text == last_text:
                        break
                await asyncio.sleep(0.5)
        finally:
            await page.close()

        # Record the final turn
        final = await self._get_final_response(page) if page else ""
        if final:
            self.add_turn("assistant", final)

    async def _get_final_response(self, page) -> str:
        try:
            return (await page.locator(SELECTORS["final_response"]).inner_text()).strip()
        except Exception:
            return ""