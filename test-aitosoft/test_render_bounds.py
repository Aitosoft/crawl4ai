"""
Render-bound offline tests — no server, no real browser.

Pins tasks/render-retry-unbounded-hang.md.

Root cause (measured 2026-07-30, reproduced locally against a fixture server):
Playwright's page.content() and page.evaluate() are sent to the driver with no
`timeout` field, so the driver arms no timer at all — they can only end when
they get a reply or the target closes.  What they wait on is the frame's
execution-context promise, and every navigation replaces that promise with a
fresh unresolved one.  A page that keeps committing navigations therefore
wedges them forever: page_timeout does not cover it (that only reaches
page.goto and the wait_* family), and because the call sites wrap them in
swallow-all try/except, nothing is logged either.  In prod that burned the
whole 180 s wall-clock fence and returned a 504 with no diagnostic.

Three bounds are pinned here, outermost last:
  1. bounded_evaluate     — every adapter-mediated page.evaluate
  2. _capture_html        — page.content(), with settle-and-retry
  3. total_timeout        — one budget shared by every attempt in arun()

    pytest test-aitosoft/test_render_bounds.py -q
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

import pytest  # noqa: E402
from playwright.async_api import Error as PlaywrightError  # noqa: E402
from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig  # noqa: E402
from crawl4ai import async_crawler_strategy as acs  # noqa: E402
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy  # noqa: E402
from crawl4ai.browser_adapter import (  # noqa: E402
    EVALUATE_TIMEOUT_S,
    PlaywrightAdapter,
    bounded_evaluate,
)
from crawl4ai.models import AsyncCrawlResponse  # noqa: E402

# The exact message Playwright raises when the context dies mid-capture.
NAVIGATING = (
    "Page.content: Unable to retrieve content because the page is navigating "
    "and changing the content."
)

# Enough real content that antibot_detector's tier-3 structural check cannot
# fire — these tests are about bounds, not about block detection.
PAGE_HTML = (
    "<!DOCTYPE html><html><head><title>Yritys Oy</title></head><body>"
    "<h1>Yritys Oy</h1><p>Yhteystiedot: info@yritys.fi</p>"
    "<p>Puhelin 010 123 4567. Osoite: Esimerkkikatu 1, 00100 Helsinki.</p>"
    "<ul><li>Palvelut</li><li>Referenssit</li><li>Yhteystiedot</li></ul>"
    "<p>Yritys Oy on suomalainen palveluyritys joka toimii koko maassa.</p>"
    "</body></html>"
)


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


async def _never():
    """An awaitable that models an untimed protocol call on a wedged page."""
    await asyncio.Event().wait()


class _Logger:
    def debug(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass

    def error(self, *a, **kw):
        pass


class FakePage:
    """Minimal stand-in for a Playwright Page for _capture_html."""

    def __init__(self, content_behaviour, settle_ok=True):
        # content_behaviour: list of "hang" | "navigating" | html string
        self.behaviour = list(content_behaviour)
        self.settle_ok = settle_ok
        self.content_calls = 0
        self.settle_calls = 0

    async def content(self):
        self.content_calls += 1
        step = self.behaviour.pop(0) if self.behaviour else PAGE_HTML
        if step == "hang":
            await _never()
        if step == "navigating":
            raise PlaywrightError(NAVIGATING)
        return step

    async def wait_for_load_state(self, state, timeout=None):
        self.settle_calls += 1
        if not self.settle_ok:
            raise PlaywrightTimeoutError(f"Timeout {timeout}ms exceeded")


def _strategy():
    """_capture_html needs only .logger — build the object without __init__ so
    the test never touches BrowserManager or Playwright."""
    s = AsyncPlaywrightCrawlerStrategy.__new__(AsyncPlaywrightCrawlerStrategy)
    s.logger = _Logger()
    return s


# ---------------------------------------------------------------------------
# 1. bounded_evaluate — the adapter funnel
# ---------------------------------------------------------------------------


def test_bounded_evaluate_returns_the_value():
    async def main():
        async def ok():
            return {"width": 100}

        assert await bounded_evaluate(ok(), 5) == {"width": 100}

    run(main())


def test_bounded_evaluate_raises_instead_of_hanging():
    async def main():
        t0 = time.perf_counter()
        with pytest.raises(PlaywrightTimeoutError) as exc:
            await bounded_evaluate(_never(), 0.2)
        elapsed = time.perf_counter() - t0
        assert elapsed < 3, f"took {elapsed:.2f}s — the bound did not fire"
        # The message has to say why, or the next incident is undiagnosable.
        assert "navigating" in str(exc.value)

    run(main())


def test_bounded_evaluate_error_is_catchable_by_existing_handlers():
    """Call sites wrap evaluate in `except Exception` / `except Error`. The
    bound must not escape either, or it turns a cosmetic skip into a failure."""

    async def main():
        try:
            await bounded_evaluate(_never(), 0.1)
        except Exception as e:
            assert isinstance(e, PlaywrightError)
            return
        raise AssertionError("no exception raised")

    run(main())


def test_adapter_evaluate_honours_an_explicit_timeout():
    """Optional cosmetic DOM steps pass a tighter ceiling than the default."""

    class HangingPage:
        async def evaluate(self, expression, *a, **kw):
            await _never()

    async def main():
        t0 = time.perf_counter()
        with pytest.raises(PlaywrightTimeoutError):
            await PlaywrightAdapter().evaluate(HangingPage(), "1+1", timeout=0.2)
        assert time.perf_counter() - t0 < 3

    run(main())


def test_adapter_default_timeout_is_finite():
    assert 0 < EVALUATE_TIMEOUT_S < 120
    assert 0 < acs.OPTIONAL_DOM_STEP_TIMEOUT_S <= EVALUATE_TIMEOUT_S


# ---------------------------------------------------------------------------
# 2. _capture_html — page.content() with settle-and-retry
# ---------------------------------------------------------------------------


def test_capture_succeeds_first_try():
    async def main():
        page = FakePage([PAGE_HTML])
        assert await _strategy()._capture_html(page) == PAGE_HTML
        assert page.content_calls == 1
        assert page.settle_calls == 0

    run(main())


def test_capture_retries_after_the_navigation_race_and_succeeds():
    """The maitokolmio.fi failure mode: the capture raced a committing
    navigation. Static mode proved the content was right there, so the whole
    crawl must not be thrown away — wait for the new document and re-capture."""

    async def main():
        page = FakePage(["navigating", PAGE_HTML])
        assert await _strategy()._capture_html(page) == PAGE_HTML
        assert page.content_calls == 2
        assert page.settle_calls == 1

    run(main())


def test_capture_gives_up_after_the_configured_attempts():
    async def main():
        page = FakePage(["navigating"] * 10)
        with pytest.raises(PlaywrightError) as exc:
            await _strategy()._capture_html(page)
        assert page.content_calls == acs.HTML_CAPTURE_ATTEMPTS
        assert "navigating" in str(exc.value)

    run(main())


def test_capture_bails_out_when_the_page_cannot_settle(monkeypatch):
    """If the page cannot even reach domcontentloaded it is stuck, not between
    documents. Another attempt would only buy another full timeout."""

    async def main():
        page = FakePage(["navigating"] * 10, settle_ok=False)
        with pytest.raises(PlaywrightError):
            await _strategy()._capture_html(page)
        assert page.content_calls == 1

    run(main())


def test_capture_bounds_a_hanging_content_call(monkeypatch):
    """The silent failure mode: content() never returns at all."""
    monkeypatch.setattr(acs, "HTML_CAPTURE_TIMEOUT_S", 0.2)
    monkeypatch.setattr(acs, "HTML_CAPTURE_TOTAL_TIMEOUT_S", 0.5)
    monkeypatch.setattr(acs, "HTML_CAPTURE_SETTLE_TIMEOUT_S", 0.1)

    async def main():
        page = FakePage(["hang"] * 10)
        t0 = time.perf_counter()
        with pytest.raises(PlaywrightTimeoutError):
            await _strategy()._capture_html(page)
        elapsed = time.perf_counter() - t0
        # Bounded by the GROUP budget, not attempts x per-call timeout.
        assert elapsed < 2.0, f"took {elapsed:.2f}s"

    run(main())


def test_capture_constants_leave_room_inside_the_fence():
    """Sanity: the whole capture path must be small next to wall_clock_s=180."""
    assert acs.HTML_CAPTURE_TOTAL_TIMEOUT_S <= 60
    assert acs.HTML_CAPTURE_TIMEOUT_S <= acs.HTML_CAPTURE_TOTAL_TIMEOUT_S
    assert acs.PAGE_CLOSE_TIMEOUT_S <= 30


# ---------------------------------------------------------------------------
# 3. total_timeout — one budget across every attempt of an arun()
# ---------------------------------------------------------------------------


class SlowStrategy:
    def __init__(self, delay):
        self.delay = delay
        self.calls = 0

    def update_user_agent(self, ua):
        pass

    async def crawl(self, url, config=None, **kwargs):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return AsyncCrawlResponse(
            html=PAGE_HTML,
            response_headers={},
            status_code=200,
            redirected_status_code=200,
        )


async def _arun(strategy, **cfg):
    crawler = AsyncWebCrawler(crawler_strategy=strategy)
    crawler.ready = True
    return await crawler.arun("https://example.fi", config=CrawlerRunConfig(**cfg))


def test_total_timeout_bounds_a_slow_attempt():
    async def main():
        strategy = SlowStrategy(delay=5)
        t0 = time.perf_counter()
        result = await _arun(strategy, max_retries=1, total_timeout=400)
        elapsed = time.perf_counter() - t0
        assert elapsed < 3, f"took {elapsed:.2f}s — total_timeout did not bound it"
        assert result.success is False
        # Attributable: the message must name the budget, not just say "failed".
        assert "400 ms" in result.error_message

    run(main())


def test_total_timeout_is_shared_across_attempts_not_per_attempt():
    """Two attempts must not each get the full budget, or max_retries silently
    multiplies the caller's deadline."""

    async def main():
        strategy = SlowStrategy(delay=5)
        t0 = time.perf_counter()
        await _arun(strategy, max_retries=3, total_timeout=400)
        elapsed = time.perf_counter() - t0
        assert elapsed < 3, f"4 attempts took {elapsed:.2f}s on a 0.4s budget"
        # Later attempts are skipped once the budget is gone, not re-run.
        assert strategy.calls <= 2

    run(main())


def test_total_timeout_absent_by_default_leaves_behaviour_unchanged():
    async def main():
        assert CrawlerRunConfig().total_timeout is None
        strategy = SlowStrategy(delay=0.2)
        result = await _arun(strategy, max_retries=0)
        assert result.success is True
        assert strategy.calls == 1

    run(main())


def test_total_timeout_survives_clone_and_to_dict():
    """api.py applies config.yml's crawler.base_config by setattr, and the
    patchright tier clones the config — the field has to survive both."""
    cfg = CrawlerRunConfig(total_timeout=100000)
    assert cfg.to_dict()["total_timeout"] == 100000
    assert cfg.clone().total_timeout == 100000
    assert CrawlerRunConfig.from_kwargs({"total_timeout": 123}).total_timeout == 123


def test_total_timeout_is_not_client_settable():
    """It is a server-side deadline. A client-sent value must be dropped, not
    honoured, or a caller could disable its own fence."""
    from crawl4ai.async_configs import UNTRUSTED_FIELD_ALLOWLIST

    assert "total_timeout" not in UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"]


def test_deployed_config_keeps_total_timeout_inside_the_fence():
    """config.yml must stay consistent with limits.wall_clock_s: the first
    tier plus the patchright tier both run inside one fence."""
    import yaml  # type: ignore[import]

    here = os.path.dirname(os.path.abspath(__file__))
    with open(
        os.path.join(os.path.dirname(here), "deploy", "docker", "config.yml")
    ) as f:
        cfg = yaml.safe_load(f)

    total_timeout_s = cfg["crawler"]["base_config"]["total_timeout"] / 1000.0
    wall_clock_s = cfg["limits"]["wall_clock_s"]
    assert total_timeout_s < wall_clock_s, "a single arun() may not span the fence"
    # Above the largest page_timeout a client may send, so one slow navigation
    # still fits inside a single attempt.
    assert total_timeout_s >= 90
