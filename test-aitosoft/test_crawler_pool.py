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


# ── the working-set reading (render-500-window, S2) ──────────────────────
#
# NOTE FOR ANYONE EXTENDING THESE: the dev container's `memory.max` is the
# literal string `max`, so `int()` raises and get_container_memory_percent()
# falls through its bare `except` to psutil. **The cgroup path is not exercised
# locally.** Every test below fakes the file reads; do not replace them with a
# live call and conclude anything from the result.


def _fake_cgroup(monkeypatch, usage, limit, stat_lines):
    """Point utils' cgroup reads at synthetic contents."""
    import utils

    files = {
        "/sys/fs/cgroup/memory.current": str(usage),
        "/sys/fs/cgroup/memory.max": str(limit),
        "/sys/fs/cgroup/memory.stat": stat_lines,
    }

    class _FakePath:
        def __init__(self, p):
            self._p = str(p)

        def exists(self):
            return self._p in files

        def read_text(self):
            if self._p not in files:
                raise FileNotFoundError(self._p)
            return files[self._p]

    monkeypatch.setattr(utils, "Path", _FakePath)
    return utils


def test_the_reading_is_the_working_set_not_raw_usage(monkeypatch):
    """`inactive_file` is page cache the kernel reclaims rather than OOMs on,
    so charging it against the limit charges us for memory we do not hold."""
    utils = _fake_cgroup(
        monkeypatch,
        usage=2_000_000_000,
        limit=4_000_000_000,
        stat_lines="anon 1500000000\nfile 500000000\ninactive_file 400000000\n",
    )
    # 2.0 GB raw = 50.0 %; working set is 1.6 GB = 40.0 %.
    assert abs(utils.get_container_memory_percent() - 40.0) < 0.01


def test_a_missing_stat_file_falls_back_to_raw_usage(monkeypatch):
    """A kernel that exposes memory.current but not memory.stat must still get
    a number — degrading to the previous behaviour, never to an exception."""
    import utils

    class _FakePath:
        _files = {
            "/sys/fs/cgroup/memory.current": "2000000000",
            "/sys/fs/cgroup/memory.max": "4000000000",
        }

        def __init__(self, p):
            self._p = str(p)

        def exists(self):
            return self._p in self._files

        def read_text(self):
            if self._p not in self._files:
                raise FileNotFoundError(self._p)
            return self._files[self._p]

    monkeypatch.setattr(utils, "Path", _FakePath)
    assert abs(utils.get_container_memory_percent() - 50.0) < 0.01


def test_a_nonsense_stat_value_cannot_hide_memory_pressure(monkeypatch):
    """The failure direction that matters. Subtracting a bogus `inactive_file`
    larger than usage would report a comfortable number on a container that is
    about to be OOM-killed, so the subtraction is ignored unless it is sane."""
    utils = _fake_cgroup(
        monkeypatch,
        usage=3_800_000_000,
        limit=4_000_000_000,
        stat_lines="anon 3700000000\nfile 100000000\ninactive_file 99999999999\n",
    )
    assert utils.get_container_memory_percent() > 90.0


def test_cgroup_v1_stat_names_are_understood(monkeypatch):
    """v1 spells it `total_inactive_file`. Azure is v2, but the fallback path
    below it in get_container_memory_percent is v1 and must not go blind."""
    utils = _fake_cgroup(
        monkeypatch,
        usage=2_000_000_000,
        limit=4_000_000_000,
        stat_lines="total_rss 1500000000\ntotal_cache 500000000\n"
        "total_inactive_file 400000000\n",
    )
    assert abs(utils.get_container_memory_percent() - 40.0) < 0.01
    parts = utils.get_memory_breakdown()
    assert parts and abs(parts["anon"] - 1430.5) < 1.0


def test_the_breakdown_is_loggable_and_never_raises(monkeypatch):
    """`memory_breakdown()` runs inside an error path and a janitor loop, so it
    has to answer even when the cgroup is not there at all."""
    import utils

    monkeypatch.setattr(utils, "_read_memory_stat", lambda: {})
    assert "unavailable" in crawler_pool.memory_breakdown()


# ── the permanent browser nobody used (render-500-window, S3) ────────────
#
# `Using permanent browser` fired 0 times in 224 pool gets during MAS's
# 2026-07-31 probe: they always send a per-company `browser_config`, so `_sig`
# never equals DEFAULT_CONFIG_SIG and the boot browser served nothing while
# holding ~139-165 MB for the replica's whole life. This is a saving, not a
# defect fix — it is the most droppable of the three S items.


def test_an_unused_permanent_browser_is_closed(monkeypatch):
    _reset_pool(monkeypatch)

    async def main():
        cfg = BrowserConfig()
        await crawler_pool.init_permanent(cfg)
        permanent = crawler_pool.PERMANENT
        assert permanent is not None

        # Nothing has matched the default sig, and the TTL has passed.
        crawler_pool.LAST_USED[crawler_pool.DEFAULT_CONFIG_SIG] = (
            time.time() - crawler_pool.PERMANENT_UNUSED_TTL_S - 5
        )
        await crawler_pool._close_unused_permanent(time.time())

        assert crawler_pool.PERMANENT is None
        assert permanent.closed

    run(main())


def test_a_used_permanent_browser_is_kept(monkeypatch):
    """The tripwire: one default-config hit and it is earning its memory."""
    _reset_pool(monkeypatch)

    async def main():
        cfg = BrowserConfig()
        await crawler_pool.init_permanent(cfg)
        await crawler_pool.get_crawler(cfg)  # one real hit
        assert crawler_pool.USAGE_COUNT[crawler_pool.DEFAULT_CONFIG_SIG] == 1

        crawler_pool.LAST_USED[crawler_pool.DEFAULT_CONFIG_SIG] = (
            time.time() - crawler_pool.PERMANENT_UNUSED_TTL_S - 5
        )
        await crawler_pool._close_unused_permanent(time.time())

        assert crawler_pool.PERMANENT is not None, "closed a browser in use"

    run(main())


def test_an_unused_permanent_browser_is_kept_until_the_ttl(monkeypatch):
    _reset_pool(monkeypatch)

    async def main():
        await crawler_pool.init_permanent(BrowserConfig())
        await crawler_pool._close_unused_permanent(time.time())
        assert crawler_pool.PERMANENT is not None

    run(main())


def test_closing_the_unused_permanent_browser_does_not_break_re_init(monkeypatch):
    """The whole reason this is safe: `get_crawler` re-creates it lazily, so a
    default-config request that arrives after the close is served normally
    rather than degraded to an overflow cold browser."""
    _reset_pool(monkeypatch)

    async def main():
        cfg = BrowserConfig()
        await crawler_pool.init_permanent(cfg)
        first = crawler_pool.PERMANENT
        crawler_pool.LAST_USED[crawler_pool.DEFAULT_CONFIG_SIG] = (
            time.time() - crawler_pool.PERMANENT_UNUSED_TTL_S - 5
        )
        await crawler_pool._close_unused_permanent(time.time())
        assert crawler_pool.PERMANENT is None

        c = await crawler_pool.get_crawler(cfg)
        assert crawler_pool.PERMANENT is c and c is not first and c.started
        assert not any("_ovf_" in k for k in crawler_pool.COLD_POOL)

    run(main())


def test_the_memory_guard_refuses_with_a_capacity_error(monkeypatch):
    """S1 at the pool's own boundary: the exception type is what api.py maps to
    429, so it is pinned here as well as at the API level."""
    from aitosoft_admission import RenderCapacityExceeded

    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "get_container_memory_percent", lambda: 95.6)
    monkeypatch.setattr(crawler_pool, "MEM_LIMIT", 85.0)

    async def main():
        import pytest as _pytest

        with _pytest.raises(RenderCapacityExceeded) as exc:
            await crawler_pool.get_crawler(BrowserConfig(viewport_width=1234))
        assert "95.6" in str(exc.value)
        assert exc.value.retry_after_s > 0

    run(main())
