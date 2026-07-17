"""
crawler_pool offline tests — no server, no real browsers.

Pins the PERMANENT re-init contract (tasks/crawler-pool-cleanup.md #2):
after the stuck-slot janitor force-closes the permanent browser
(_force_close_stuck sets PERMANENT = None), the next default-config
get_crawler() must lazily re-create it instead of degrading all
default-config traffic to overflow cold browsers until container restart.

    pytest test-aitosoft/test_crawler_pool.py -q
"""

import asyncio
import os
import sys
import time

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
    ),
)

import crawler_pool  # noqa: E402
from crawl4ai import BrowserConfig  # noqa: E402


class FakeCrawler:
    """Stands in for AsyncWebCrawler — no Chromium, tracks lifecycle."""

    def __init__(self, config=None, thread_safe=False):
        self.config = config
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True
        return self

    async def close(self):
        self.closed = True


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _reset_pool(monkeypatch):
    """Give each test a clean pool with mocked browser construction.

    LOCK must be re-created per test: asyncio primitives bind to the first
    event loop that acquires them, and run() spins up a fresh loop per test.
    """
    monkeypatch.setattr(crawler_pool, "AsyncWebCrawler", FakeCrawler)
    monkeypatch.setattr(crawler_pool, "get_container_memory_percent", lambda: 10.0)
    monkeypatch.setattr(crawler_pool, "LOCK", asyncio.Lock())
    monkeypatch.setattr(crawler_pool, "PERMANENT", None)
    monkeypatch.setattr(crawler_pool, "DEFAULT_CONFIG_SIG", None)
    monkeypatch.setattr(crawler_pool, "HOT_POOL", {})
    monkeypatch.setattr(crawler_pool, "COLD_POOL", {})
    monkeypatch.setattr(crawler_pool, "LAST_USED", {})
    monkeypatch.setattr(crawler_pool, "USAGE_COUNT", {})
    monkeypatch.setattr(crawler_pool, "BUSY_SINCE", {})
    monkeypatch.setattr(crawler_pool, "OVERFLOW_SEQ", 0)


def test_permanent_reinit_after_stuck_force_close(monkeypatch):
    """Force-close the permanent browser via the real janitor path, then
    assert the next default-config request re-creates it — no overflow."""
    _reset_pool(monkeypatch)

    async def main():
        cfg = BrowserConfig()
        await crawler_pool.init_permanent(cfg)
        first = crawler_pool.PERMANENT
        assert first is not None and first.started

        # Mark it stuck: busy since before the timeout threshold.
        crawler_pool._incr_active(first)
        crawler_pool.BUSY_SINCE[id(first)] = (
            time.time() - crawler_pool.STUCK_BUSY_TIMEOUT_S - 5
        )
        await crawler_pool._force_close_stuck(time.time())
        assert crawler_pool.PERMANENT is None
        assert first.closed

        # Next default-config request: live permanent browser again.
        c = await crawler_pool.get_crawler(cfg)
        assert isinstance(c, FakeCrawler) and c.started and not c.closed
        assert crawler_pool.PERMANENT is c
        assert c is not first
        assert c.active_requests == 1
        # It must NOT have degraded to an overflow cold browser.
        assert not any("_ovf_" in k for k in crawler_pool.COLD_POOL)

    run(main())


def test_reinit_permanent_is_reused_not_rebuilt(monkeypatch):
    """After re-init, subsequent default-config requests reuse the same
    permanent browser instead of constructing again."""
    _reset_pool(monkeypatch)

    async def main():
        cfg = BrowserConfig()
        await crawler_pool.init_permanent(cfg)
        crawler_pool.PERMANENT = None  # simulate force-close outcome

        c1 = await crawler_pool.get_crawler(cfg)
        c2 = await crawler_pool.get_crawler(cfg)
        assert c1 is c2 is crawler_pool.PERMANENT
        assert c2.active_requests == 2

    run(main())


def test_no_permanent_creation_before_first_init(monkeypatch):
    """PERMANENT is None until init_permanent runs; a request must go to the
    cold pool, not spuriously mint a permanent browser."""
    _reset_pool(monkeypatch)

    async def main():
        cfg = BrowserConfig()
        c = await crawler_pool.get_crawler(cfg)
        assert crawler_pool.PERMANENT is None
        assert c in crawler_pool.COLD_POOL.values()

    run(main())


def test_non_default_config_does_not_touch_permanent(monkeypatch):
    """A non-default sig while PERMANENT is None goes to the cold pool and
    leaves the permanent slot alone."""
    _reset_pool(monkeypatch)

    async def main():
        default_cfg = BrowserConfig()
        other_cfg = BrowserConfig(viewport_width=777)
        await crawler_pool.init_permanent(default_cfg)
        crawler_pool.PERMANENT = None  # simulate force-close outcome

        c = await crawler_pool.get_crawler(other_cfg)
        assert crawler_pool.PERMANENT is None
        assert c in crawler_pool.COLD_POOL.values()

    run(main())
