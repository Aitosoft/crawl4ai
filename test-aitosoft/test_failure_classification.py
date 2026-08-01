"""
Origin-vs-crawler failure classification — OFFLINE, no server, no network.

Pins the transport contract MAS chose on 2026-07-30 (Q2, answer (a)):

    origin-caused  ->  HTTP 200, result success:false, failure_class,
                       status_code = the origin's real FINAL status
    our fault      ->  500 (render_error) / 504 (render_timeout)
    capacity       ->  429 + Retry-After

and the property that makes it usable: `failure_class` is on EVERY result,
successes included, so a missing field means an old build rather than a success.

This is the deploy gate for the redirect fix. Block detection now marks
redirect-then-block hosts as failures, and before this change every full-mode
failure reached MAS as an opaque HTTP 500 with the whole envelope discarded —
so shipping the redirect fix alone would have moved those hosts from a
wrong-but-parseable 200 to an unattributable, retried 500.

    pytest test-aitosoft/test_failure_classification.py -q
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

from aitosoft_failure_class import (  # noqa: E402
    BAD_REQUEST,
    CAPACITY,
    NONE,
    ORIGIN_BLOCKED,
    ORIGIN_CLASSES,
    ORIGIN_HTTP_ERROR,
    ORIGIN_UNREACHABLE,
    RENDER_ERROR,
    RENDER_TIMEOUT,
    classify_exception,
    classify_result,
    effective_status_of,
    envelope_class_for_status,
    failed_result,
    http_status_for,
)

# ── the three incidents this taxonomy was built from ─────────────────────

# anitamakela.com, 2026-07-27: a genuine HTTP 500 with a zero-byte body from
# the site's own Apache. Chromium refuses to render it, upstream re-raises, and
# MAS spent 8 retries in 35 s learning nothing.
ANITAMAKELA = (
    "Failed on navigating ACS-GOTO: Page.goto: "
    "net::ERR_HTTP_RESPONSE_CODE_FAILURE at https://anitamakela.com/"
)

# www.konecranes.com: Fastly/Varnish 403 to every engine we have — httpx, real
# Chrome + stealth, and patchright alike. IP reputation, not fingerprint.
KONECRANES_BLOCK = (
    "Blocked by anti-bot protection: HTTP 403 with HTML content (425 bytes)"
)


def test_origin_http_error_from_navigation_failure():
    assert classify_exception(RuntimeError(ANITAMAKELA)) == ORIGIN_HTTP_ERROR


def test_origin_blocked_from_antibot_message():
    assert (
        classify_result(
            {"success": False, "status_code": 403, "error_message": KONECRANES_BLOCK}
        )
        == ORIGIN_BLOCKED
    )


def test_origin_5xx_is_an_http_error_even_when_the_body_reads_as_blocked():
    """The block detector judges the body, and an empty 5xx body trips its
    structural check — so a site that is simply broken came back labelled
    `origin_blocked`. Both are origin-caused and both map to 200, but only one
    of them is what a residential-egress retry would target."""
    empty_500 = {
        "success": False,
        "status_code": 500,
        "redirected_status_code": 500,
        "error_message": (
            "Blocked by anti-bot protection: Structural: minimal_text, "
            "no_content_elements (39 bytes, 0 chars visible)"
        ),
    }
    assert classify_result(empty_500) == ORIGIN_HTTP_ERROR
    # 503 stays a block — Incapsula and Varnish really do serve blocks with it.
    assert (
        classify_result(
            {**empty_500, "status_code": 503, "redirected_status_code": 503}
        )
        == ORIGIN_BLOCKED
    )
    # 403 is the ordinary block case and must be untouched.
    assert (
        classify_result(
            {**empty_500, "status_code": 403, "redirected_status_code": 403}
        )
        == ORIGIN_BLOCKED
    )


def test_redirect_then_block_is_judged_on_the_final_hop():
    """konecranes.com apex: 301 -> 403. `status_code` holds the 301, the body
    came from the 403. Judging the first hop is what let every redirect-to-block
    host through as success:true with the block page as content."""
    result = {
        "success": False,
        "status_code": 301,
        "redirected_status_code": 403,
        "error_message": KONECRANES_BLOCK,
    }
    assert effective_status_of(result) == 403
    assert classify_result(result) == ORIGIN_BLOCKED
    assert http_status_for([classify_result(result)]) == 200


@pytest.mark.parametrize(
    "net_error,expected",
    [
        ("net::ERR_HTTP_RESPONSE_CODE_FAILURE", ORIGIN_HTTP_ERROR),
        ("net::ERR_EMPTY_RESPONSE", ORIGIN_HTTP_ERROR),
        ("net::ERR_TOO_MANY_REDIRECTS", ORIGIN_HTTP_ERROR),
        ("net::ERR_NAME_NOT_RESOLVED", ORIGIN_UNREACHABLE),
        ("net::ERR_CONNECTION_REFUSED", ORIGIN_UNREACHABLE),
        ("net::ERR_CONNECTION_TIMED_OUT", ORIGIN_UNREACHABLE),
        ("net::ERR_SSL_PROTOCOL_ERROR", ORIGIN_UNREACHABLE),
        ("net::ERR_CERT_DATE_INVALID", ORIGIN_UNREACHABLE),
        ("net::ERR_ADDRESS_UNREACHABLE", ORIGIN_UNREACHABLE),
    ],
)
def test_net_errors_map_to_origin_classes(net_error, expected):
    msg = f"Failed on navigating ACS-GOTO: Page.goto: {net_error} at https://x.fi/"
    assert classify_exception(RuntimeError(msg)) == expected


def test_unknown_net_error_is_blamed_on_us():
    """Deliberate bias. Calling our fault the origin's tells MAS a healthy
    company site is permanently broken, silently — the failure mode they called
    the most expensive thing that happened to them this month. Calling the
    origin's fault ours costs wasted renders and is loud."""
    assert (
        classify_exception(
            RuntimeError("Page.goto: net::ERR_SOMETHING_WE_HAVE_NEVER_SEEN")
        )
        == RENDER_ERROR
    )


def test_timeouts_stay_ours():
    assert classify_exception(asyncio.TimeoutError()) == RENDER_TIMEOUT
    assert (
        classify_exception(RuntimeError("Page.goto: Timeout 30000ms exceeded"))
        == RENDER_TIMEOUT
    )


def test_page_content_race_is_ours_not_the_origins():
    """maitokolmio.fi's `Page.content: Unable to retrieve content because the
    page is navigating` — our render lost a race. Not the site's fault."""
    assert (
        classify_exception(
            RuntimeError(
                "Page.content: Unable to retrieve content because the page is "
                "navigating and changing the content."
            )
        )
        == RENDER_ERROR
    )


# ── failure_class is on every result, successes included ─────────────────


def test_success_carries_none_not_absence():
    assert classify_result({"success": True, "status_code": 200}) == NONE


def test_failure_without_any_signal_is_ours():
    assert classify_result({"success": False}) == RENDER_ERROR


def test_failure_with_only_an_origin_status_is_the_origins():
    assert classify_result({"success": False, "status_code": 404}) == ORIGIN_HTTP_ERROR


# ── transport mapping ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "classes,expected_status",
    [
        ([NONE], 200),
        ([ORIGIN_HTTP_ERROR], 200),
        ([ORIGIN_BLOCKED], 200),
        ([ORIGIN_UNREACHABLE], 200),
        ([RENDER_TIMEOUT], 504),
        ([RENDER_ERROR], 500),
        # Mixed batches cannot happen under the single-URL contract, but the
        # rule must still never hide one of our faults behind a 200.
        ([ORIGIN_BLOCKED, RENDER_ERROR], 500),
        ([ORIGIN_BLOCKED, RENDER_TIMEOUT], 504),
    ],
)
def test_http_status_mapping(classes, expected_status):
    assert http_status_for(classes) == expected_status


def test_five_xx_is_reserved_for_our_own_faults():
    """The whole contract in one assertion."""
    for cls in ORIGIN_CLASSES:
        assert http_status_for([cls]) < 500


def test_envelope_classes_for_resultless_failures():
    assert envelope_class_for_status(429) == CAPACITY
    assert envelope_class_for_status(400) == BAD_REQUEST
    assert envelope_class_for_status(500) == RENDER_ERROR
    assert envelope_class_for_status(504) == RENDER_TIMEOUT
    # Not part of the taxonomy — must stay absent rather than be invented.
    assert envelope_class_for_status(404) is None


def test_failed_result_shape_matches_static_mode():
    """MAS parses full-mode and static-mode failures with one code path."""
    from aitosoft_static_mode import _static_error_result

    ours = failed_result("https://x.fi/", ORIGIN_HTTP_ERROR, "boom")
    theirs = _static_error_result("https://x.fi/", error_message="boom")
    assert set(theirs) <= set(ours)
    for key in (
        "url",
        "success",
        "status_code",
        "error_message",
        "failure_class",
        "render_mode",
        "markdown",
        "links",
    ):
        assert key in ours


# ── end-to-end through api.handle_crawl_request ──────────────────────────

SERVER_CONFIG = {
    "crawler": {
        "base_config": {},
        "memory_threshold_percent": 85.0,
        "rate_limiter": {"enabled": False, "base_delay": [1, 2]},
    },
    "limits": {"wall_clock_s": 180},
}


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_origin_navigation_failure_returns_an_envelope_not_a_500(monkeypatch):
    """anitamakela.com end to end: upstream re-raises the navigation failure,
    and we must answer with a parseable envelope instead of the opaque 500 that
    cost MAS 8 retries in 35 seconds."""
    import api

    class _Crawler:
        async def arun(self, *a, **kw):
            raise RuntimeError(ANITAMAKELA)

    async def _get_crawler(cfg):
        return _Crawler()

    async def _release(c):
        return None

    import crawler_pool

    monkeypatch.setattr(crawler_pool, "get_crawler", _get_crawler)
    monkeypatch.setattr(crawler_pool, "release_crawler", _release)

    out = _run(
        api.handle_crawl_request(
            urls=["https://anitamakela.com/"],
            browser_config={},
            crawler_config={},
            config=SERVER_CONFIG,
        )
    )
    assert isinstance(out, dict), "an HTTPException escaped — MAS gets an opaque 500"
    result = out["results"][0]
    assert result["success"] is False
    assert result["failure_class"] == ORIGIN_HTTP_ERROR
    assert result["error_message"]
    assert http_status_for([result["failure_class"]]) == 200


def _crawler_returning(payload: dict):
    class _Result:
        def model_dump(self):
            return dict(payload)

    class _Crawler:
        async def arun(self, *a, **kw):
            return _Result()

    return _Crawler()


def _patch_pool(monkeypatch, crawler):
    import crawler_pool

    async def _get_crawler(cfg):
        return crawler

    async def _release(c):
        return None

    monkeypatch.setattr(crawler_pool, "get_crawler", _get_crawler)
    monkeypatch.setattr(crawler_pool, "release_crawler", _release)


def test_status_code_reports_the_final_hop_like_static_mode(monkeypatch):
    """MAS asked for `status_code` = the origin's real final status. Static
    mode has always reported the final hop under that name; full mode reported
    the first, so an apex->www redirect to a 403 block page was labelled 301.
    `redirected_status_code` is untouched and is now part of the contract."""
    import api

    _patch_pool(
        monkeypatch,
        _crawler_returning(
            {
                "url": "https://konecranes.com/",
                "success": False,
                "status_code": 301,
                "redirected_status_code": 403,
                "redirected_url": "https://www.konecranes.com/",
                "error_message": KONECRANES_BLOCK,
            }
        ),
    )

    out = _run(
        api.handle_crawl_request(
            urls=["https://konecranes.com/"],
            browser_config={},
            crawler_config={},
            config=SERVER_CONFIG,
        )
    )
    result = out["results"][0]
    assert result["status_code"] == 403
    assert result["redirected_status_code"] == 403
    assert result["failure_class"] == ORIGIN_BLOCKED


def test_successful_results_carry_failure_class_none(monkeypatch):
    """A missing field must never need interpretation — it means an old build,
    not a success."""
    import api

    _patch_pool(
        monkeypatch,
        _crawler_returning(
            {
                "url": "https://caverna.fi/",
                "success": True,
                "status_code": 200,
                "redirected_status_code": None,
                "error_message": "",
            }
        ),
    )

    out = _run(
        api.handle_crawl_request(
            urls=["https://caverna.fi/"],
            browser_config={},
            crawler_config={},
            config=SERVER_CONFIG,
        )
    )
    result = out["results"][0]
    assert result["failure_class"] == NONE
    assert result["render_mode"] == "full"
    assert result["status_code"] == 200


def test_our_own_crash_still_raises_500(monkeypatch):
    """The other half of the contract: 5xx must keep meaning 'ours'."""
    import api
    from fastapi import HTTPException

    class _Crawler:
        async def arun(self, *a, **kw):
            raise RuntimeError("browser process died unexpectedly")

    async def _get_crawler(cfg):
        return _Crawler()

    async def _release(c):
        return None

    import crawler_pool

    monkeypatch.setattr(crawler_pool, "get_crawler", _get_crawler)
    monkeypatch.setattr(crawler_pool, "release_crawler", _release)

    with pytest.raises(HTTPException) as exc:
        _run(
            api.handle_crawl_request(
                urls=["https://example.com/"],
                browser_config={},
                crawler_config={},
                config=SERVER_CONFIG,
            )
        )
    assert exc.value.status_code == 500


# ── evidence vs inference (detector round 3, 2026-08-01) ─────────────────
#
# `is_blocked` returns one verdict for two kinds of finding, and this module
# used to map both to ORIGIN_BLOCKED. MAS measured the cost on 2026-07-31: 4 of
# their 33 `origin_blocked` verdicts were not blocks, and the expensive one was
# our own pipeline's placeholder reported to a customer as the origin blocking
# them. See tasks/detector-round3-evidence-vs-inference.md defect B.

#: MAS's four wrong verdicts, verbatim in shape. `fodbar.fi` is settled and
#: stays exactly as it is (their message 09 §5) — the origin said 403, so we
#: report 403, and the decision about whether the body looks like content is
#: theirs to make with 117,000 stored pages to compare against.
MAS_DEFECT_B_CASES = [
    (
        "norex.com — our own 'not fully supported' placeholder, 15 bytes at 200",
        {
            "success": False,
            "status_code": 200,
            "error_message": (
                "Blocked by anti-bot protection: "
                "Near-empty content (15 bytes) with HTTP 200"
            ),
        },
        RENDER_ERROR,
    ),
    (
        "jarvenkylamaatila.fi — a 1-character body",
        {
            "success": False,
            "status_code": 200,
            "error_message": (
                "Blocked by anti-bot protection: "
                "Near-empty content (1 bytes) with HTTP 200"
            ),
        },
        RENDER_ERROR,
    ),
    (
        "snuup.fi — an ordinary 404 page",
        {
            "success": False,
            "status_code": 404,
            "error_message": (
                "Blocked by anti-bot protection: Structural: minimal_text, "
                "no_content_elements (900 bytes, 20 chars visible)"
            ),
        },
        ORIGIN_HTTP_ERROR,
    ),
    (
        "fodbar.fi — real content at origin 403, SETTLED: leave it alone",
        {
            "success": False,
            "status_code": 403,
            "error_message": (
                "Blocked by anti-bot protection: "
                "HTTP 403 with HTML content (3962 bytes)"
            ),
        },
        ORIGIN_BLOCKED,
    ),
]


@pytest.mark.parametrize(
    "label,result,expected",
    MAS_DEFECT_B_CASES,
    ids=[c[0][:24] for c in MAS_DEFECT_B_CASES],
)
def test_mas_measured_misclassifications(label, result, expected):
    assert classify_result(result) == expected, label


def test_an_inferred_block_is_never_an_origin_class():
    """The guarantee this module's docstring already claimed and did not keep:
    an unrecognised failure is ours, never a verdict about the customer's site.
    """
    for _label, result, expected in MAS_DEFECT_B_CASES:
        if (
            "Structural:" in result["error_message"]
            or "Near-empty" in result["error_message"]
        ):
            assert expected is not ORIGIN_BLOCKED


def test_evidence_reasons_still_classify_as_origin_blocked():
    """The other direction. Loosening the detector's size gates widens the
    "origin said so" side; narrowing inference must not narrow this one too.
    Every reason below is the origin's own bytes saying it refused us."""
    evidence = [
        "Cloudflare firewall block",
        "Akamai block (Reference #)",
        "Unidentified challenge (robot-suspicion asset)",
        "Challenge interstitial (One moment, please) "
        "(HTTP 200, 11515 bytes, 58 chars visible)",
        "Block notice is the page: HTTP refusal status "
        "(in the page heading, 48 chars visible): 403 - Forbidden "
        "(HTTP 202, 80671 bytes)",
        "HTTP 403 with HTML content (80671 bytes)",
        "HTTP 429 Too Many Requests",
    ]
    for reason in evidence:
        result = {
            "success": False,
            "status_code": 202,
            "error_message": f"Blocked by anti-bot protection: {reason}",
        }
        assert classify_result(result) == ORIGIN_BLOCKED, reason


def test_every_reason_the_detector_can_produce_lands_on_one_side():
    """The seam is a reason-string prefix, so it has to be swept, not trusted.

    This drives `is_blocked` with a body for every tier and asserts that each
    verdict it returns is classified as *either* the origin's or ours — never
    left to whichever branch happens to catch it. A new tier whose reason
    matches neither convention fails here rather than silently telling MAS a
    healthy host is permanently blocked, which is how defect B shipped.
    """
    from crawl4ai.antibot_detector import is_blocked

    # (label, status, html, is this the origin telling us, or us inferring?)
    corpus = [
        (
            "tier 1 vendor marker",
            200,
            '<html><body><span class="cf-error-code">1020</span></body></html>',
            True,
        ),
        (
            "challenge interstitial",
            200,
            "<html><head><title>Just a moment...</title></head><body>"
            "<h1>Checking your browser</h1></body></html>",
            True,
        ),
        (
            "challenge, padded past the old byte gate",
            200,
            "<html><head><title>One moment, please...</title>"
            "<style>" + "a{color:red}" * 1200 + "</style></head>"
            "<body><p>Please wait while your request is being verified...</p>"
            "</body></html>",
            True,
        ),
        (
            "HTTP 403 with a body",
            403,
            "<html><body><h1>Forbidden</h1><p>No.</p></body></html>",
            True,
        ),
        (
            "block notice at a non-error status",
            202,
            "<html><head><title>Attention</title>"
            "<style>" + "a{color:red}" * 6000 + "</style></head>"
            "<body><h1>403 - Forbidden</h1>"
            "<p>Access to this page is forbidden.</p></body></html>",
            True,
        ),
        ("HTTP 429", 429, "<html><body>slow down</body></html>", True),
        ("near-empty at 200", 200, "<html></html>", False),
        (
            "tier 3 structural",
            200,
            "<html><body><div></div><script>var a=1;</script></body></html>",
            False,
        ),
    ]

    for label, status, html, origin_said_so in corpus:
        blocked, reason = is_blocked(status, html)
        assert blocked, f"{label}: expected a verdict, got none"
        verdict = classify_result(
            {
                "success": False,
                "status_code": status,
                "error_message": f"Blocked by anti-bot protection: {reason}",
            }
        )
        if origin_said_so:
            assert verdict == ORIGIN_BLOCKED, f"{label}: {reason} -> {verdict}"
        else:
            assert verdict not in ORIGIN_CLASSES, (
                f"{label}: inference reported as the origin's fault "
                f"({reason} -> {verdict})"
            )


def test_the_wire_status_follows_the_reclassification():
    """What MAS actually branches on. An inferred block moves from a terminal
    200 to a retryable 500 — we are asking for the retry back, deliberately —
    while a real block stays terminal."""
    assert http_status_for([RENDER_ERROR]) == 500
    assert http_status_for([ORIGIN_BLOCKED]) == 200
    assert http_status_for([ORIGIN_HTTP_ERROR]) == 200
