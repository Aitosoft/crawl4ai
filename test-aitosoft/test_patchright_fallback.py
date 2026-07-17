"""
Patchright fallback offline tests — no server, no real browsers.

Pins the recycle-race fix (tasks/patchright-fallback-tidy.md #2): the
singleton is dereferenced INSIDE the semaphore with _UNDETECTED_IN_FLIGHT
already raised, and _recycle_undetected only swaps when in_flight == 0 —
so arun can never run on a crawler the recycler just closed.

    pytest test-aitosoft/test_patchright_fallback.py -q
"""

import asyncio
import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
    ),
)

import aitosoft_patchright_fallback as pf  # noqa: E402
from crawl4ai import BrowserConfig  # noqa: E402


class FakeResult:
    def __init__(self, success=True, error_message=""):
        self.success = success
        self.error_message = error_message


def make_blocked():
    return FakeResult(False, "Blocked by anti-bot protection: cloudflare challenge")


class FakeCrawler:
    """Stands in for the patchright AsyncWebCrawler — records misuse."""

    def __init__(self, *args, **kwargs):
        self.closed = False
        self.arun_calls = []
        self.arun_on_closed = 0
        self.arun_gate = None  # set to an asyncio.Event to park arun mid-flight

    async def start(self):
        return self

    async def close(self):
        self.closed = True

    async def arun(self, url=None, config=None):
        if self.closed:
            self.arun_on_closed += 1
            raise RuntimeError("arun on closed crawler")
        if self.arun_gate is not None:
            await self.arun_gate.wait()
        self.arun_calls.append(url)
        return FakeResult(success=True)


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _reset(monkeypatch, crawler=None, uses=0):
    """Clean module state with mocked construction; primitives re-created per
    test because asyncio objects bind to the first loop that uses them."""
    monkeypatch.setattr(pf, "AsyncWebCrawler", FakeCrawler)
    monkeypatch.setattr(pf, "AsyncPlaywrightCrawlerStrategy", lambda **kw: object())
    monkeypatch.setattr(pf, "UndetectedAdapter", lambda: object())
    monkeypatch.setattr(pf, "_UNDETECTED_CRAWLER", crawler)
    monkeypatch.setattr(pf, "_UNDETECTED_LOCK", asyncio.Lock())
    monkeypatch.setattr(
        pf, "_UNDETECTED_SEM", asyncio.Semaphore(pf._UNDETECTED_CONCURRENCY)
    )
    monkeypatch.setattr(pf, "_UNDETECTED_USES", uses)
    monkeypatch.setattr(pf, "_UNDETECTED_IN_FLIGHT", 0)


def test_recycle_before_retry_never_aruns_stale_ref(monkeypatch):
    """The pre-fix race: recycle fires after the (old) early deref point.
    The retry must build a fresh crawler, never arun the closed one."""

    async def main():
        stale = FakeCrawler()
        _reset(monkeypatch, crawler=stale, uses=pf._UNDETECTED_RECYCLE_USES)
        # Idle recycle: closes and nulls the singleton — exactly the state
        # the old code's stale ref pointed at.
        await pf._recycle_undetected()
        assert stale.closed and pf._UNDETECTED_CRAWLER is None

        results = await pf.maybe_retry_blocked(
            results=[make_blocked()],
            urls=["https://example.com"],
            crawler_config=None,
            base_browser_config=BrowserConfig(),
        )
        assert stale.arun_on_closed == 0
        assert stale.arun_calls == []
        fresh = pf._UNDETECTED_CRAWLER
        assert isinstance(fresh, FakeCrawler) and fresh is not stale
        assert fresh.arun_calls == ["https://example.com"]
        assert results[0].success

    run(main())


def test_recycle_skipped_while_retry_in_flight(monkeypatch):
    """A recycle attempt while a caller is mid-arun must be a no-op — this
    is the invariant that closes the deref/close race."""

    async def main():
        crawler = FakeCrawler()
        crawler.arun_gate = asyncio.Event()
        _reset(monkeypatch, crawler=crawler, uses=0)

        task = asyncio.create_task(
            pf.maybe_retry_blocked(
                results=[make_blocked()],
                urls=["https://example.com"],
                crawler_config=None,
                base_browser_config=BrowserConfig(),
            )
        )
        for _ in range(20):
            await asyncio.sleep(0)
            if pf._UNDETECTED_IN_FLIGHT == 1:
                break
        assert pf._UNDETECTED_IN_FLIGHT == 1

        # Force a recycle attempt mid-flight: must skip, not close.
        pf._UNDETECTED_USES = pf._UNDETECTED_RECYCLE_USES
        await pf._recycle_undetected()
        assert crawler.closed is False
        assert pf._UNDETECTED_CRAWLER is crawler

        crawler.arun_gate.set()
        results = await asyncio.wait_for(task, timeout=2.0)
        assert crawler.arun_on_closed == 0
        assert results[0].success
        assert pf._UNDETECTED_IN_FLIGHT == 0

    run(main())


def test_in_flight_resets_after_arun_exception(monkeypatch):
    """A raising arun keeps the original blocked result and never leaves the
    in-flight counter raised (a leak would block all future recycles)."""

    class RaisingCrawler(FakeCrawler):
        async def arun(self, url=None, config=None):
            raise RuntimeError("boom")

    async def main():
        crawler = RaisingCrawler()
        _reset(monkeypatch, crawler=crawler, uses=0)
        original = make_blocked()
        results = await pf.maybe_retry_blocked(
            results=[original],
            urls=["https://example.com"],
            crawler_config=None,
            base_browser_config=BrowserConfig(),
        )
        assert results[0] is original  # first-tier diagnostic preserved
        assert pf._UNDETECTED_IN_FLIGHT == 0

    run(main())


def test_startup_failure_keeps_original_results(monkeypatch):
    """If the singleton can't start, the retry pass degrades gracefully and
    the counter is not leaked by the early return."""

    class FailingStart(FakeCrawler):
        async def start(self):
            raise RuntimeError("no chromium here")

    async def main():
        _reset(monkeypatch, crawler=None, uses=0)
        monkeypatch.setattr(pf, "AsyncWebCrawler", FailingStart)
        original = make_blocked()
        results = await pf.maybe_retry_blocked(
            results=[original],
            urls=["https://example.com"],
            crawler_config=None,
            base_browser_config=BrowserConfig(),
        )
        assert results[0] is original
        assert pf._UNDETECTED_CRAWLER is None
        assert pf._UNDETECTED_IN_FLIGHT == 0

    run(main())
