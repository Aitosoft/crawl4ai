"""
Redirect-chain block detection offline tests — no server, no real browser.

Pins tasks/redirect-status-blinds-block-detection.md: block detection must
judge the response body by the status that produced it (the LAST hop of a
redirect chain), not by CrawlResult.status_code, which deliberately carries
the FIRST hop.  Before the fix, every site that redirects apex -> www and then
serves a 403 block page was reported to MAS as success:true with the block
page as its content (prod evidence: konecranes.com, forensics 2026-07-30 §2b).

Deliberately NOT pinned here: that status_code keeps the first hop. That is
upstream semantics (PR #1435, tests/test_pr_1435_redirected_status_code.py)
and MAS may branch on it — see the regression assertions below, which check it
is unchanged.

    pytest test-aitosoft/test_redirect_block_detection.py -q
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
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig  # noqa: E402
from crawl4ai.antibot_detector import effective_status, is_blocked  # noqa: E402
from crawl4ai.models import AsyncCrawlResponse  # noqa: E402

# The 425-byte Fastly/Varnish body observed from www.konecranes.com, trimmed.
VARNISH_403 = (
    "<!DOCTYPE html><html><head><title>403 Forbidden</title></head><body>"
    "<h1>Error 403 Forbidden</h1><p>Forbidden</p><h3>Error 54113</h3>"
    "<p>Details: cache-ams-eham8680049-AMS</p><hr><p>Varnish cache server</p>"
    "</body></html>"
)

# A benign page: real content elements, enough visible text that the tier-3
# structural check cannot fire.  This is the false-positive tripwire.
BENIGN_PAGE = (
    "<!DOCTYPE html><html><head><title>Yritys Oy</title></head><body>"
    "<h1>Yritys Oy</h1><p>Yhteystiedot: info@yritys.fi</p>"
    "<p>Puhelin 010 123 4567. Osoite: Esimerkkikatu 1, 00100 Helsinki.</p>"
    "<ul><li>Palvelut</li><li>Referenssit</li><li>Yhteystiedot</li></ul>"
    "<p>Yritys Oy on suomalainen palveluyritys joka toimii koko maassa.</p>"
    "</body></html>"
)


class FakeStrategy:
    """Stands in for AsyncPlaywrightCrawlerStrategy — counts page loads."""

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def update_user_agent(self, ua):
        pass

    async def crawl(self, url, config=None, **kwargs):
        self.calls += 1
        return self.response


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _response(html, status_code, redirected_status_code=None, redirected_url=None):
    return AsyncCrawlResponse(
        html=html,
        response_headers={},
        status_code=status_code,
        redirected_status_code=redirected_status_code,
        redirected_url=redirected_url,
    )


async def _crawl(response, url="https://konecranes.com", max_retries=1):
    """Drive arun() with no browser: ready=True skips start(), the fake
    strategy replaces Playwright, and cache_mode defaults to BYPASS so the
    database is never touched."""
    strategy = FakeStrategy(response)
    crawler = AsyncWebCrawler(crawler_strategy=strategy)
    crawler.ready = True
    result = await crawler.arun(url, config=CrawlerRunConfig(max_retries=max_retries))
    return result, strategy


# ---------------------------------------------------------------------------
# effective_status() — the helper the three call sites share
# ---------------------------------------------------------------------------


def test_effective_status_prefers_the_final_hop():
    assert effective_status(301, 403) == 403
    assert effective_status(302, 200) == 200


def test_effective_status_falls_back_when_there_was_no_redirect():
    # Non-HTTP paths (raw:, file://, js_only) leave redirected_status_code None.
    assert effective_status(200, None) == 200
    assert effective_status(None, None) is None
    # A direct request sets both to the same value.
    assert effective_status(403, 403) == 403


# ---------------------------------------------------------------------------
# The defect: a block page behind a redirect
# ---------------------------------------------------------------------------


def test_block_page_behind_redirect_is_marked_failed():
    """301 -> 403 Varnish. The prod defect: this returned success:true."""

    async def main():
        result, _ = await _crawl(
            _response(VARNISH_403, 301, 403, "https://www.konecranes.com/")
        )
        assert result.success is False
        assert result.error_message.startswith("Blocked by anti-bot protection:")
        # The reason must name the status that actually caused the verdict,
        # otherwise the next forensics session re-derives this bug from a 301.
        assert "403" in result.error_message
        # Contract: status_code still carries the FIRST hop (upstream semantics).
        assert result.status_code == 301
        assert result.redirected_status_code == 403

    run(main())


def test_block_page_without_redirect_still_detected():
    """No-redirect 403 — the population that already worked. No regression."""

    async def main():
        result, _ = await _crawl(
            _response(VARNISH_403, 403, 403), url="https://www.konecranes.com"
        )
        assert result.success is False
        assert "Blocked by anti-bot protection:" in result.error_message

    run(main())


def test_benign_redirect_still_succeeds():
    """301 -> 200 with real content. The false-positive tripwire: Finnish
    company sites redirect apex->www almost universally, so a false positive
    here would fail most of the corpus."""

    async def main():
        result, strategy = await _crawl(
            _response(BENIGN_PAGE, 301, 200, "https://www.yritys.fi/"),
            url="http://yritys.fi",
        )
        assert result.success is True
        assert not result.error_message
        assert strategy.calls == 1  # no retry burned on a good page

    run(main())


def test_direct_200_is_a_no_op():
    """No redirect: status_code == redirected_status_code, so the change
    cannot alter the verdict either way."""

    async def main():
        result, strategy = await _crawl(
            _response(BENIGN_PAGE, 200, 200), url="https://www.yritys.fi"
        )
        assert result.success is True
        assert strategy.calls == 1

    run(main())


def test_raw_url_still_skips_block_detection():
    """raw: content is caller-provided, not fetched — anti-bot is N/A."""

    async def main():
        result, _ = await _crawl(
            _response(VARNISH_403, 200, None), url="raw:" + VARNISH_403
        )
        assert result.success is True
        assert not result.error_message

    run(main())


# ---------------------------------------------------------------------------
# Consequences the change has beyond the verdict itself
# ---------------------------------------------------------------------------


def test_blocked_result_costs_one_page_load_per_attempt():
    """Cost guard. A blocked verdict re-enters the attempt loop, so a
    redirect-to-block host now costs 1 + max_retries first-tier renders where
    it used to cost 1. Visible here rather than discovered in prod — see
    tasks/blocked-host-retry-economy.md."""

    async def main():
        for max_retries in (0, 1, 2):
            _, strategy = await _crawl(
                _response(VARNISH_403, 301, 403), max_retries=max_retries
            )
            assert strategy.calls == 1 + max_retries

    run(main())


def test_blocked_result_arms_the_patchright_tier():
    """Handoff guard. Our second tier keys off the error_message marker, so
    the fix is what makes patchright fire for this host class at all."""

    async def main():
        result, _ = await _crawl(_response(VARNISH_403, 301, 403))
        assert pf._is_blocked(result) is True

    run(main())


def test_benign_redirect_does_not_arm_the_patchright_tier():
    async def main():
        result, _ = await _crawl(_response(BENIGN_PAGE, 301, 200))
        assert pf._is_blocked(result) is False

    run(main())


# ---------------------------------------------------------------------------
# What the detector does with a 3xx — updated 2026-08-01
# ---------------------------------------------------------------------------


def test_a_block_body_is_now_caught_even_at_the_wrong_status():
    """This assertion was inverted on 2026-08-01, and the inversion is the fix.

    It used to read `is_blocked(301, VARNISH_403)[0] is False`, pinning that no
    status rule can fire on a 3xx — which is *why* `effective_status` had to
    exist. That is still true of the status rules, but it is no longer true of
    the detector: the block-notice tier added by
    tasks/detector-round3-evidence-vs-inference.md judges the page's own text
    and needs no status at all, so `<h1>Error 403 Forbidden</h1>` is now
    evidence wherever it arrives.

    That makes this case belt-and-braces rather than a single point of failure,
    but it does **not** retire `effective_status`: a block page with no
    recognisable notice — a bare JS shell at 403 — still has nothing but its
    status to give away, and MAS reads `status_code` regardless. Both tests
    below stay.
    """
    blocked, reason = is_blocked(301, VARNISH_403)
    assert blocked, "the body says 403 Forbidden in an <h1>; the status is irrelevant"
    assert "Block notice" in reason

    assert is_blocked(403, VARNISH_403)[0] is True


def test_a_benign_page_is_still_not_blocked_at_any_status():
    """The tripwire for the assertion above: a status-independent tier must not
    become a status-independent false positive."""
    for status in (200, 301, 302, 404):
        blocked, reason = is_blocked(status, BENIGN_PAGE)
        assert not blocked, f"benign page condemned at {status}: {reason}"
