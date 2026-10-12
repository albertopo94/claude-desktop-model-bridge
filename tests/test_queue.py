"""Tests for the rate-limit token budget and queue."""

import asyncio
import time

import pytest

from claude_browser_gateway.queue import TokenBudget, RequestQueue


def test_budget_unlimited_when_max_zero():
    b = TokenBudget(max_tokens=0)
    assert b.remaining() > 0
    assert b.consume(1000) is True


def test_budget_exhausts_and_recovers():
    b = TokenBudget(max_tokens=100, window_seconds=3600)
    assert b.consume(60) is True
    assert b.remaining() == 40
    assert b.consume(50) is False  # 60+50 > 100
    # Short window: reset after the window passes
    b.window_start = time.time() - 3601
    assert b.consume(50) is True  # window reset
    assert b.remaining() == 50


def test_budget_retry_after():
    b = TokenBudget(max_tokens=10, window_seconds=60)
    b.consume(10)
    assert b.remaining() == 0
    retry = b.retry_after()
    assert 0 <= retry <= 60


@pytest.mark.asyncio
async def test_queue_single_flight():
    q = RequestQueue()
    calls = []

    async def work(x):
        calls.append(x)
        await asyncio.sleep(0.01)
        return x * 2

    results = await asyncio.gather(
        q.single_flight(lambda: work(1)),
        q.single_flight(lambda: work(2)),
    )
    # Both ran (second waits for first), values correct
    assert sorted(results) == [2, 4]
    assert len(calls) == 2