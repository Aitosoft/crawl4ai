"""
RenderGate admission-control tests — OFFLINE, no server, no browser.

Pins the per-replica admission contract introduced after the 2026-07-16
kynnos.fi 504 incident (see tasks/capacity-scaling-redesign.md):

  * at most `render_capacity` concurrent renders admitted;
  * a bounded queue (`admission_queue` waiters, `admission_max_wait_s` max
    wait) absorbs micro-bursts;
  * beyond that RenderCapacityExceeded (-> HTTP 429 in api.py) is raised
    IMMEDIATELY (queue full) or after the bounded wait (timeout) — never a
    silent unbounded wait inside the 180s wall-clock fence;
  * weighted acquire is all-or-nothing and clamped to capacity so a
    multi-URL batch can neither smuggle renders nor deadlock the gate.

    pytest test-aitosoft/test_admission.py -q
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
    ),
)

from aitosoft_admission import (  # noqa: E402
    RenderCapacityExceeded,
    RenderGate,
)


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_admits_up_to_capacity_immediately():
    async def main():
        gate = RenderGate(capacity=2, max_queue=0, max_wait_s=0.1)
        assert await gate.acquire() == 1
        assert await gate.acquire() == 1
        snap = gate.snapshot()
        assert snap["in_use"] == 2 and snap["queued"] == 0

    run(main())


def test_queue_full_rejects_immediately():
    async def main():
        gate = RenderGate(capacity=1, max_queue=0, max_wait_s=5.0)
        await gate.acquire()
        t0 = asyncio.get_event_loop().time()
        with pytest.raises(RenderCapacityExceeded):
            await gate.acquire()
        # Immediate rejection, not a 5s wait.
        assert asyncio.get_event_loop().time() - t0 < 0.5

    run(main())


def test_bounded_wait_then_reject():
    async def main():
        gate = RenderGate(capacity=1, max_queue=2, max_wait_s=0.2)
        await gate.acquire()
        t0 = asyncio.get_event_loop().time()
        with pytest.raises(RenderCapacityExceeded):
            await gate.acquire()
        waited = asyncio.get_event_loop().time() - t0
        assert 0.15 <= waited < 1.0
        # Queue count must be restored after the timeout.
        assert gate.snapshot()["queued"] == 0

    run(main())


def test_release_admits_waiter():
    async def main():
        gate = RenderGate(capacity=1, max_queue=2, max_wait_s=5.0)
        w = await gate.acquire()
        waiter = asyncio.create_task(gate.acquire())
        await asyncio.sleep(0.05)
        assert gate.snapshot()["queued"] == 1
        await gate.release(w)
        assert await asyncio.wait_for(waiter, timeout=1.0) == 1
        assert gate.snapshot()["in_use"] == 1

    run(main())


def test_weight_counts_urls_and_is_clamped():
    async def main():
        gate = RenderGate(capacity=2, max_queue=0, max_wait_s=0.1)
        # A 100-URL batch is still admissible: weight clamps to capacity.
        w = await gate.acquire(weight=100)
        assert w == 2
        # Gate is now full — a single render can't sneak in.
        with pytest.raises(RenderCapacityExceeded):
            await gate.acquire()
        await gate.release(w)
        assert gate.snapshot()["in_use"] == 0

    run(main())


def test_weighted_acquire_is_all_or_nothing():
    async def main():
        gate = RenderGate(capacity=2, max_queue=2, max_wait_s=5.0)
        w1 = await gate.acquire()  # in_use 1
        big = asyncio.create_task(gate.acquire(weight=2))  # needs both slots
        await asyncio.sleep(0.05)
        # Big waiter holds nothing while queued (no partial holds).
        assert gate.snapshot()["in_use"] == 1
        await gate.release(w1)
        assert await asyncio.wait_for(big, timeout=1.0) == 2
        assert gate.snapshot()["in_use"] == 2

    run(main())


def test_cancelled_waiter_leaves_gate_consistent():
    async def main():
        gate = RenderGate(capacity=1, max_queue=2, max_wait_s=10.0)
        w = await gate.acquire()
        waiter = asyncio.create_task(gate.acquire())
        await asyncio.sleep(0.05)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert gate.snapshot()["queued"] == 0
        await gate.release(w)
        # Gate still fully usable.
        assert await gate.acquire() == 1

    run(main())


def test_handle_crawl_request_maps_to_429():
    """api.handle_crawl_request must convert RenderCapacityExceeded into an
    HTTP 429 with a Retry-After header BEFORE any browser work happens."""
    import aitosoft_admission as adm
    from fastapi import HTTPException

    async def main():
        # Import inside the loop-less context; api.py has heavy-but-offline
        # imports (no network, no redis connection at import time).
        import api

        gate = RenderGate(capacity=1, max_queue=0, max_wait_s=0.1)
        await gate.acquire()  # saturate
        adm.set_render_gate(gate)
        try:
            with pytest.raises(HTTPException) as exc_info:
                await api.handle_crawl_request(
                    urls=["https://example.com"],
                    browser_config={},
                    crawler_config={},
                    config={
                        "crawler": {
                            "base_config": {},
                            "memory_threshold_percent": 85.0,
                            "rate_limiter": {"enabled": False, "base_delay": [1, 2]},
                        },
                        "limits": {"wall_clock_s": 180},
                    },
                )
            assert exc_info.value.status_code == 429
            assert "Retry-After" in (exc_info.value.headers or {})
        finally:
            adm.set_render_gate(None)

    run(main())
