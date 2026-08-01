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
from contextlib import suppress

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


class SlowStartCrawler(FakeCrawler):
    """A browser whose launch takes real time.

    `get_crawler` holds LOCK across `await crawler.start()`, so with an
    instant fake every test is effectively serial and nothing about the
    locking is exercised. Chromium takes 0.5-3 s to launch in production.
    """

    async def start(self):
        await asyncio.sleep(0.02)
        self.started = True
        return self


class HangingCloseCrawler(FakeCrawler):
    """A browser whose close() never returns — a wedged Chromium.

    This is the shape that turns a capped pool into a dead replica if
    eviction closes browsers while holding the pool lock.
    """

    async def close(self):
        await asyncio.Event().wait()  # forever


def run(coro):
    """Run one test coroutine on its own loop, then tear the loop down cleanly.

    Aitosoft 2026-08-02: eviction closes browsers in a DETACHED task on
    purpose (never on the pool lock), so a test that evicts leaves background
    tasks behind. Discarding the loop with those pending printed a wall of
    "Task was destroyed but it is pending!" over a green run — and a suite
    that always prints alarming output is a suite whose real warnings get
    waved through, which is the failure mode CLAUDE.md's secret-check note
    already names. Cancel and reap instead.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


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
    # Aitosoft 2026-08-02: the browser cap. Set high by default so the tests
    # that predate it keep testing what they were written to test; the cap
    # tests lower it themselves. `_CLOSING` holds asyncio Tasks, which bind to
    # the loop that created them — it must be reset per test for the same
    # reason LOCK is.
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 100)
    monkeypatch.setattr(crawler_pool, "_CLOSING", set())


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
# 2026-07-31 probe, while the boot browser held ~139-165 MB for the replica's
# whole life. This is a saving, not a defect fix.
#
# The reason recorded here was wrong (corrected 2026-08-02). It is not that MAS
# always sends a `browser_config` — it is that `server.py` builds the permanent
# browser's config without `enforce_egress`, which every request path applies
# and which flips `ignore_https_errors` True -> False. The two signatures differ
# in a field no client controls, so the permanent browser is unreachable by
# construction and this TTL always fires. See crawler_pool.PERMANENT_UNUSED_TTL_S.


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


# ── the browser cap (tasks/pool-residency-unbounded.md) ──────────────────
#
# Nothing bounded how many browsers the pool held: `render_capacity` bounds
# concurrent renders, `max_pages` bounds pages per browser, and residency was
# governed by idle TTL alone. Measured peak on 2026-07-31: 9-10 per replica.
#
# The invariant every test below defends is not "memory is low" — these
# tests must never assert MB, which are machine- and page-dependent — it is
# **`get_crawler` never waits.** A capped pool that waits for a browser to go
# idle waits for `release_crawler`, which needs the same LOCK the waiter is
# holding, and the replica is dead with no 504, no 429 and no janitor recovery.


def _distinct(i: int) -> BrowserConfig:
    """A config with its own signature, the way MAS's per-company
    `browser_config` produces one."""
    return BrowserConfig(viewport_width=1000 + i)


async def _drain_closes():
    """Wait for the detached eviction closes to finish.

    Eviction deliberately does NOT await `close()` on the admission path, so a
    test that checks `victim.closed` has to wait for the background task. One
    `sleep(0)` is not enough — `_close_detached` schedules a task which then
    awaits `asyncio.wait_for`, so there are several hops.
    """
    for _ in range(50):
        pending = [t for t in crawler_pool._CLOSING if not t.done()]
        if not pending:
            return
        await asyncio.wait(pending, timeout=1)


def test_the_cap_bounds_resident_browsers(monkeypatch):
    """The point of the whole change: N distinct signatures, at most cap live."""
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 4)

    async def main():
        seen_max = 0
        for i in range(12):
            c = await crawler_pool.get_crawler(_distinct(i))
            seen_max = max(seen_max, crawler_pool.resident_browsers())
            await crawler_pool.release_crawler(c)
        assert seen_max <= 4, f"pool grew to {seen_max} against a cap of 4"
        assert crawler_pool.resident_browsers() == 4

    run(main())


def test_eviction_is_least_recently_used(monkeypatch):
    """Not just 'something was evicted' — the OLDEST idle one, so a hot
    signature survives a burst of one-off ones."""
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 3)

    async def main():
        crawlers = []
        for i in range(3):
            c = await crawler_pool.get_crawler(_distinct(i))
            await crawler_pool.release_crawler(c)
            crawlers.append(c)

        # Touch #0 and #2 so #1 is unambiguously the least recently used.
        now = time.time()
        keys = list(crawler_pool.COLD_POOL.keys())
        crawler_pool.LAST_USED[keys[0]] = now
        crawler_pool.LAST_USED[keys[1]] = now - 500
        crawler_pool.LAST_USED[keys[2]] = now

        await crawler_pool.get_crawler(_distinct(99))
        await _drain_closes()

        assert crawlers[1].closed, "LRU victim was not the least recently used"
        assert not crawlers[0].closed and not crawlers[2].closed
        assert keys[1] not in crawler_pool.COLD_POOL
        # Bookkeeping must go with the browser or the next LRU scan is wrong.
        assert keys[1] not in crawler_pool.LAST_USED
        assert keys[1] not in crawler_pool.USAGE_COUNT

    run(main())


def test_a_busy_browser_is_never_evicted(monkeypatch):
    """`active_requests > 0` is an absolute veto. Evicting a browser with pages
    in flight closes Chromium under a live render."""
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 2)

    async def main():
        busy = await crawler_pool.get_crawler(_distinct(0))  # never released
        idle = await crawler_pool.get_crawler(_distinct(1))
        await crawler_pool.release_crawler(idle)

        # Make the BUSY one look like the LRU candidate. The only thing that
        # may save it is the active-requests veto.
        for key in crawler_pool.COLD_POOL:
            if crawler_pool.COLD_POOL[key] is busy:
                crawler_pool.LAST_USED[key] = 0.0

        await crawler_pool.get_crawler(_distinct(2))
        await _drain_closes()

        assert not busy.closed, "evicted a browser with a request in flight"
        assert idle.closed

    run(main())


def test_the_cap_refuses_rather_than_waits_when_nothing_is_idle(monkeypatch):
    """The refusal must be RenderCapacityExceeded specifically.

    api.py maps ONLY that type to 429 + Retry-After; any other exception falls
    into its generic `except Exception` and becomes a 500, which MAS retries
    three times — the exact regression tasks/render-500-window-2026-07-31.md
    was written to remove.
    """
    from aitosoft_admission import RenderCapacityExceeded

    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 2)

    async def main():
        import pytest as _pytest

        await crawler_pool.get_crawler(_distinct(0))  # held
        await crawler_pool.get_crawler(_distinct(1))  # held

        with _pytest.raises(RenderCapacityExceeded) as exc:
            await asyncio.wait_for(crawler_pool.get_crawler(_distinct(2)), timeout=2)
        assert "busy" in str(exc.value)
        assert exc.value.retry_after_s > 0

    run(main())


def test_a_wedged_close_cannot_wedge_the_pool(monkeypatch):
    """The eviction close runs OFF the lock, so a Chromium that never exits
    cannot take the admission path with it.

    If eviction ever goes back to `await victim.close()` inside `async with
    LOCK`, this test hangs and `wait_for` turns that into a failure.
    """
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "AsyncWebCrawler", HangingCloseCrawler)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 2)

    async def main():
        for i in range(2):
            c = await crawler_pool.get_crawler(_distinct(i))
            await crawler_pool.release_crawler(c)

        # This evicts an idle browser whose close() never returns.
        c = await asyncio.wait_for(crawler_pool.get_crawler(_distinct(2)), timeout=5)
        assert c.started
        # ...and the pool is still usable afterwards, which is the real claim.
        await asyncio.wait_for(crawler_pool.release_crawler(c), timeout=5)
        c2 = await asyncio.wait_for(crawler_pool.get_crawler(_distinct(3)), timeout=5)
        assert c2.started
        assert crawler_pool.resident_browsers() <= 2

    run(main())


def test_concurrent_arrivals_over_the_cap_refuse_instead_of_hanging(monkeypatch):
    """The load-bearing test, and it is written to FAIL rather than hang.

    More concurrent arrivals than the cap, distinct signatures, each releasing
    in a `finally` the way api.py does, with a slow browser launch so the lock
    is genuinely contended. The contract under test is NOT "everyone gets a
    browser" — it is:

      * every call TERMINATES (a hang is caught by wait_for and fails),
      * the cap is never breached,
      * every non-success is a typed RenderCapacityExceeded, i.e. a 429,
      * and the pool still works afterwards.

    This is what "never block" buys. The alternative — waiting for a browser
    to go idle — waits on `release_crawler`, which needs the LOCK the waiter
    holds, and produces a replica that answers nothing at all.

    Note the configuration here is deliberately WORSE than production: 6
    concurrent arrivals against a cap of 3. The render gate admits 2, and the
    cap is 6, so this over-subscription is unreachable through /crawl.
    """
    from aitosoft_admission import RenderCapacityExceeded

    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "AsyncWebCrawler", SlowStartCrawler)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 3)

    async def main():
        peak = 0
        outcomes = []

        async def one(i):
            nonlocal peak
            crawler = None
            try:
                crawler = await crawler_pool.get_crawler(_distinct(i))
                peak = max(peak, crawler_pool.resident_browsers())
                await asyncio.sleep(0.01)  # "rendering"
                outcomes.append("ok")
            except RenderCapacityExceeded:
                outcomes.append("429")
            finally:
                if crawler is not None:
                    await crawler_pool.release_crawler(crawler)

        await asyncio.wait_for(asyncio.gather(*[one(i) for i in range(6)]), timeout=20)

        assert len(outcomes) == 6, "a call neither succeeded nor refused"
        assert outcomes.count("ok") >= 3, f"cap under-delivered: {outcomes}"
        assert peak <= 3, f"cap breached under concurrency: {peak}"

        # The pool is still usable — a refusal is not a poisoned pool.
        for c in list(crawler_pool.COLD_POOL.values()):
            await crawler_pool.release_crawler(c)
        again = await asyncio.wait_for(
            crawler_pool.get_crawler(_distinct(0)), timeout=5
        )
        assert again.started

    run(main())


def test_two_concurrent_renders_never_hit_the_cap_refusal(monkeypatch):
    """The production configuration, stated as a test.

    The render gate admits `render_capacity` (2) concurrent renders, each
    holding exactly one pool browser. At max_browsers=6 that leaves >= 3 idle
    eviction candidates at all times, so the refusal branch is unreachable for
    MAS's traffic no matter how many distinct signatures arrive.
    """
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "AsyncWebCrawler", SlowStartCrawler)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 6)
    gate = asyncio.Semaphore(2)  # stands in for RenderGate at render_capacity

    async def main():
        refusals = []

        async def one(i):
            async with gate:
                crawler = None
                try:
                    crawler = await crawler_pool.get_crawler(_distinct(i))
                    await asyncio.sleep(0.005)
                except Exception as exc:  # noqa: BLE001
                    refusals.append(repr(exc))
                finally:
                    if crawler is not None:
                        await crawler_pool.release_crawler(crawler)

        await asyncio.wait_for(asyncio.gather(*[one(i) for i in range(40)]), timeout=30)
        assert refusals == [], f"cap refused a gated render: {refusals}"
        assert crawler_pool.resident_browsers() <= 6

    run(main())


def test_the_permanent_browser_counts_but_is_never_the_victim(monkeypatch):
    """It holds memory, so it counts against the cap. It is not in either pool
    dict, and `_close_unused_permanent` owns its lifecycle — two mechanisms
    closing the same browser is how a double-close race gets written."""
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 3)

    async def main():
        await crawler_pool.init_permanent(BrowserConfig())
        permanent = crawler_pool.PERMANENT
        assert crawler_pool.resident_browsers() == 1

        for i in range(6):
            c = await crawler_pool.get_crawler(_distinct(i))
            await crawler_pool.release_crawler(c)

        assert crawler_pool.resident_browsers() == 3
        assert crawler_pool.PERMANENT is permanent and not permanent.closed
        assert len(crawler_pool.COLD_POOL) + len(crawler_pool.HOT_POOL) == 2

    run(main())


def test_overflow_keys_count_as_residency(monkeypatch):
    """`_ovf_` keys are separate live browsers under one signature. A cap that
    counted signatures instead of pool keys would not bound them at all."""
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "MAX_BROWSERS", 3)
    monkeypatch.setattr(crawler_pool, "MAX_PAGES", 1)

    async def main():
        cfg = _distinct(0)  # ONE signature throughout
        held = [await crawler_pool.get_crawler(cfg) for _ in range(3)]
        assert any("_ovf_" in k for k in crawler_pool.COLD_POOL), "no overflow key"
        assert crawler_pool.resident_browsers() == 3

        for c in held:
            await crawler_pool.release_crawler(c)
        await crawler_pool.get_crawler(cfg)
        assert crawler_pool.resident_browsers() <= 3

    run(main())


def test_memory_pressure_no_longer_collapses_the_idle_ttl(monkeypatch):
    """The thrash engine, removed.

    Above 80 % the janitor used to drop `cold_ttl` to 30 s, closing browsers
    exactly when memory was tight so the next request had to launch a fresh
    one. Regressing MAS's probe gives `mem% = 59.3 + 2.65 * browsers`
    (r^2 = 0.22) — ~59 % of the replica is baseline no eviction can reach, so
    shedding browsers could not relieve the pressure it was reacting to.
    """
    _reset_pool(monkeypatch)
    monkeypatch.setattr(crawler_pool, "BASE_IDLE_TTL", 300)
    # Low while the browser is created (the guard would otherwise refuse it),
    # high once the janitor runs — the pressure the old TTL reacted to.
    pressure = [10.0]
    monkeypatch.setattr(
        crawler_pool, "get_container_memory_percent", lambda: pressure[0]
    )

    async def main():
        c = await crawler_pool.get_crawler(_distinct(0))
        await crawler_pool.release_crawler(c)
        key = next(iter(crawler_pool.COLD_POOL))

        # Idle for 60 s: past the old 30 s pressure TTL, inside the 300 s one.
        crawler_pool.LAST_USED[key] = time.time() - 60
        pressure[0] = 95.0

        task = asyncio.get_event_loop().create_task(crawler_pool.janitor())
        await asyncio.sleep(0.05)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        assert not c.closed, "the memory-adaptive TTL collapse is still there"

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
