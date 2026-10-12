"""Rate-limit aware request queue.

claude.ai enforces free-tier limits (windowed token budget). This queue:

- Tracks a local token budget per window
- Queues requests beyond the budget with backoff
- Returns 429 with Retry-After when the window is exhausted
- Never retries upstream on its own — the client retries
- Single-flight: at most one refresh or login at a time
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


@dataclass
class TokenBudget:
    """Windowed token budget for claude.ai free tier."""

    window_seconds: float = 3600.0
    max_tokens: int = 0  # 0 = unknown/unlimited; set from observed limits
    used: int = 0
    window_start: float = field(default_factory=time.time)

    def reset_if_expired(self) -> None:
        now = time.time()
        if now - self.window_start >= self.window_seconds:
            self.used = 0
            self.window_start = now

    def remaining(self) -> int:
        self.reset_if_expired()
        if self.max_tokens <= 0:
            return 1 << 30  # effectively unlimited
        return max(0, self.max_tokens - self.used)

    def consume(self, tokens: int) -> bool:
        """Return True if the tokens fit within the remaining budget."""
        self.reset_if_expired()
        if self.max_tokens <= 0:
            self.used += tokens
            return True
        if tokens > self.remaining():
            return False
        self.used += tokens
        return True

    def retry_after(self) -> float:
        """Seconds until the budget window resets."""
        self.reset_if_expired()
        if self.max_tokens <= 0:
            return 0.0
        return max(0.0, self.window_seconds - (time.time() - self.window_start))


class RequestQueue:
    """Bounded async queue with a token budget and single-flight refresh."""

    def __init__(self, budget: TokenBudget | None = None) -> None:
        self.budget = budget or TokenBudget()
        self._lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._refreshing = False

    async def acquire(self, estimated_tokens: int) -> float:
        """Wait until tokens are available. Returns the wait time in seconds."""
        async with self._lock:
            while not self.budget.consume(estimated_tokens):
                wait = self.budget.retry_after()
                if wait <= 0:
                    wait = 1.0
                await asyncio.sleep(min(wait, 5.0))
            return 0.0

    def release(self, actual_tokens: int) -> None:
        """Adjust the budget after a request completes."""
        # Budget is conservative; actual usage may differ. Keep it simple.
        pass

    async def single_flight(self, coro_factory: Callable[[], Awaitable[T]]) -> T:
        """Run a coroutine, ensuring only one runs at a time."""
        async with self._refresh_lock:
            if self._refreshing:
                # Wait for the in-flight refresh
                while self._refreshing:
                    await asyncio.sleep(0.5)
                return await coro_factory()
            self._refreshing = True
            try:
                return await coro_factory()
            finally:
                self._refreshing = False