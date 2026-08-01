"""
The fixture origin, exercised through the real production path — OFFLINE.

No customer site is contacted. Every request in this suite goes to a loopback
HTTP server this process started, through `aitosoft_entry` ->
`api.handle_crawl_request` -> a real pool browser, so `failure_class`,
`render_mode`, the final-hop `status_code` rewrite, the patchright retry and the
wall-clock fence are genuinely exercised rather than simulated.

Three things this suite is for:

  1. Proving the instrument reproduces the shapes we have only ever seen in
     production, so tasks #1-#3 in tasks/README.md cost zero live traffic.
  2. Pinning the current — including currently wrong — behaviour of each shape,
     so the tasks that fix them have a red test to turn green. The padded-block
     test is the clearest case: it asserts today's defect on purpose.
  3. Proving the loopback allowance did not weaken the SSRF guarantee. That
     assertion lives here rather than in a security suite because it is this
     module's convenience that would have paid for it.

    pytest test-aitosoft/test_fixture_origin.py -q     # ~50 s, launches Chromium
"""

import os

import pytest

from fixture_origin import (
    COLLAPSE_SHAPES,
    CONTENT_MARKER,
    PADDED_BLOCK_TEXT,
    loopback_allowed,
)

# Resolution delays chosen so neither case is a race against the pipeline's own
# overhead. Measured 2026-07-31: everything between `page.goto` returning and
# the capture — consent-popup removal, the settle steps, `delay_before_return_html`
# — costs ~0.5 s even at the shortest wait, so a 0.5 s interstitial resolves
# before a "too early" capture can miss it.
LATE_S = 5.0  # further out than any capture wait: the interstitial is what we get
EARLY_S = 0.5  # inside a 2.0 s capture wait: the content is what we get

SHORT_WAIT = 0.1  # `delay_before_return_html` — capture as soon as possible
MAS_WAIT = 2.0  # what MAS sends in production


# ── the egress seam: the guarantee this module could have broken ─────────


def test_production_configuration_refuses_the_fixture_origin(fixture_origin):
    """The broker is unmodified: outside `loopback_allowed()` the fixture's own
    URL is refused, by the same rule and with the same opaque error a real SSRF
    attempt gets."""
    from fastapi import HTTPException

    from egress_broker import EgressBlocked, assert_host_allowed, resolve_and_pin
    from utils import validate_url_destination

    url = fixture_origin.url("/ok")

    with pytest.raises(EgressBlocked) as blocked:
        resolve_and_pin(url)
    assert blocked.value.reason == "URL blocked", "the error must not leak the target"

    with pytest.raises(EgressBlocked):
        assert_host_allowed("localhost", 80)

    with pytest.raises(HTTPException) as refused:
        validate_url_destination(url)
    assert refused.value.status_code == 400


def test_the_loopback_allowance_is_scoped_and_never_process_wide(fixture_origin):
    """`loopback_allowed()` is a block, not a mode.

    If it were the environment variable, every suite sharing this pytest process
    would silently lose its SSRF assertions — test_static_mode.py's per-hop
    redirect checks among them.
    """
    import egress_broker
    import utils

    assert (
        os.environ.get("CRAWL4AI_ALLOW_INTERNAL_URLS", "false").lower() != "true"
    ), "the fixture origin must not enable the operator escape hatch process-wide"
    assert not utils.ALLOW_INTERNAL_URLS
    assert not egress_broker.ALLOW_INTERNAL

    url = fixture_origin.url("/ok")
    with loopback_allowed():
        assert egress_broker.resolve_and_pin(url).ip == "127.0.0.1"
        utils.validate_url_destination(url)

    assert not utils.ALLOW_INTERNAL_URLS
    assert not egress_broker.ALLOW_INTERNAL
    with pytest.raises(egress_broker.EgressBlocked):
        egress_broker.resolve_and_pin(url)


# ── the control ─────────────────────────────────────────────────────────


def test_a_healthy_page_is_a_clean_capture(fixture_origin, production_path):
    """Baseline. If this fails, nothing else in the suite means anything."""
    outcome = production_path.crawl(
        fixture_origin.url("/ok"), delay_before_return_html=SHORT_WAIT
    )

    assert outcome.success
    assert outcome.http_status == 200
    assert outcome.status_code == 200
    assert outcome.failure_class == "none"
    assert outcome.result["render_mode"] == "full"
    assert CONTENT_MARKER in outcome.markdown


# ── challenge interstitials (tasks/challenge-interstitial-resolve.md) ────


@pytest.mark.parametrize("route", ["resolve-after", "resolve-by-nav"])
def test_an_interstitial_captured_too_early_is_the_result_we_keep(
    route, fixture_origin, production_path
):
    """The shape MAS observed: HTTP 202, the challenge screen stored as the page.

    This is the whole of task #1's premise, offline. Note the status: 202 is the
    challenge layer's own code, not an error, so no status branch in the
    detector fires — the interstitial is caught by its vendor marker alone.
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/challenge/{route}/{LATE_S}"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert not outcome.success
    assert outcome.status_code == 202
    assert outcome.failure_class == "origin_blocked"
    assert "robot-suspicion" in outcome.html
    assert CONTENT_MARKER not in outcome.markdown
    # Origin-caused, so MAS must see 200 + success:false and stop retrying.
    assert outcome.http_status == 200


@pytest.mark.parametrize("route", ["resolve-after", "resolve-by-nav"])
def test_an_interstitial_that_resolves_inside_the_wait_gives_the_real_page(
    route, fixture_origin, production_path
):
    """The other half of the experiment: when the capture outlasts the challenge
    we get the content — at the same HTTP 202. `resolve-by-nav` additionally
    covers forensics §1, where the capture lands while the frame's execution
    context is being replaced by a top-level navigation.
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/challenge/{route}/{EARLY_S}"),
        delay_before_return_html=MAS_WAIT,
    )

    assert outcome.success, outcome.error_message
    assert outcome.status_code == 202, "202 serves the real page too, not just the wall"
    assert outcome.failure_class == "none"
    assert CONTENT_MARKER in outcome.markdown
    assert "robot-suspicion" not in outcome.html


def test_an_interstitial_that_never_resolves_stays_blocked(
    fixture_origin, production_path
):
    """The control that keeps the experiment honest: waiting longer must not
    rescue a wall that was never going to lift, or "increase the capture wait"
    would look like a fix for hosts it cannot help."""
    outcome = production_path.crawl(
        fixture_origin.url("/challenge/never"), delay_before_return_html=MAS_WAIT
    )

    assert not outcome.success
    assert outcome.failure_class == "origin_blocked"
    assert CONTENT_MARKER not in outcome.markdown


def test_an_unmarked_interstitial_is_stored_as_content(fixture_origin, production_path):
    """The silent case, pinned as today's behaviour.

    Strip the vendor marker and the "Just a moment" title and one sentence of
    Finnish prose is enough to clear every tier: 53 characters of markdown come
    back at `success: true, failure_class: none`. Tier 3 does not fire because
    the page has an <h1> and a <p> in it, which is all "has content elements"
    means.

    This is why "how many interstitials are we storing as pages?" has never had
    an answer: we can only count the ones we recognise. It is the same failure
    as the padded block below, reached by a different route — and the reason
    tasks/detector-round3-evidence-vs-inference.md is about evidence rather than
    about adding patterns.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/challenge/never", marker="none"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert CONTENT_MARKER not in outcome.markdown, "the page never resolved"
    assert len(outcome.markdown.strip()) < 100
    assert outcome.success, "TODAY'S BEHAVIOUR — an unmarked wall reads as a page"
    assert outcome.failure_class == "none"


# ── padded blocks (tasks/detector-round3-evidence-vs-inference.md) ───────


def test_a_padded_block_page_is_not_detected_today(fixture_origin, production_path):
    """DEFECT A, pinned deliberately.

    Every size gate in antibot_detector is on `len(html)`: tier 2 at 10 KB, tier
    3 at 50 KB. The vendor pads the block page to ~80 KB, so a page with 36
    characters on it sails through as content — at `success: true`,
    `failure_class: none`, which is the "green counter" failure mode MAS called
    the most expensive thing that happened to them this month.

    Four such blocks were missed in the eight hosts MAS measured in prod.
    tasks/detector-round3-evidence-vs-inference.md moves the gates onto visible
    text; when it ships, this test must be inverted, not deleted — its job then
    is to prove the fix fires.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/block/padded-403"), delay_before_return_html=SHORT_WAIT
    )

    assert len(outcome.html) > 50_000, "the padding is the mechanism"
    assert PADDED_BLOCK_TEXT in outcome.markdown
    assert len(outcome.markdown.strip()) < 100, "36 characters of block notice"

    assert outcome.success, "TODAY'S BEHAVIOUR — invert when defect A is fixed"
    assert outcome.failure_class == "none"


def test_the_padding_is_the_only_difference(fixture_origin, production_path):
    """The same block notice under the 50 KB gate IS detected. Isolates the
    defect to the size gate rather than to anything about the body."""
    outcome = production_path.crawl(
        fixture_origin.url("/block/padded-403", bytes=0),
        delay_before_return_html=SHORT_WAIT,
    )

    assert not outcome.success
    assert outcome.failure_class == "origin_blocked"


# ── edge blocks (tasks/blocked-host-retry-economy.md) ────────────────────


def test_a_varnish_403_is_the_origin_s_failure_not_ours(
    fixture_origin, production_path
):
    """The cheap, unambiguous block. MAS's contract: origin-caused never comes
    back as our 5xx, and the origin's real final status rides along."""
    outcome = production_path.crawl(
        fixture_origin.url("/block/varnish-403"), delay_before_return_html=SHORT_WAIT
    )

    assert not outcome.success
    assert outcome.status_code == 403
    assert outcome.failure_class == "origin_blocked"
    assert outcome.http_status == 200, "5xx is reserved for our own faults"


def test_a_blocked_host_costs_two_page_loads(fixture_origin, production_path):
    """What a block actually costs us, measured rather than reasoned about.

    Two document fetches: the first-tier render plus the patchright retry, which
    runs for every result the detector marks blocked. That is the number
    tasks/blocked-host-retry-economy.md is trying to reduce, and this is now the
    place to measure a change to it — no live blocked host required.
    """
    fixture_origin.reset_hits()
    production_path.crawl(
        fixture_origin.url("/block/varnish-403"), delay_before_return_html=SHORT_WAIT
    )

    assert fixture_origin.hits_for("/block/varnish-403") == 2


# ── hydration races (MAS's revisol.fi class) ─────────────────────────────


def test_a_shell_captured_before_it_paints_is_a_degenerate_capture(
    fixture_origin, production_path
):
    """Not a block — nobody refused us — but indistinguishable from one in the
    result today. Keeping the two classes separable is why this route exists."""
    outcome = production_path.crawl(
        fixture_origin.url(f"/hydrate-after/{LATE_S}"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert not outcome.success
    assert outcome.status_code == 200
    assert len(outcome.markdown.strip()) < 500, "MAS's DEGENERATE_CAPTURE_CHARS floor"
    assert CONTENT_MARKER not in outcome.markdown


def test_a_shell_captured_after_it_paints_is_the_real_page(
    fixture_origin, production_path
):
    outcome = production_path.crawl(
        fixture_origin.url(f"/hydrate-after/{EARLY_S}"),
        delay_before_return_html=MAS_WAIT,
    )

    assert outcome.success, outcome.error_message
    assert CONTENT_MARKER in outcome.markdown


# ── redirect chains (the effective_status fix) ───────────────────────────


def test_a_redirect_into_a_block_is_judged_on_the_final_hop(
    fixture_origin, production_path
):
    """Judging the 301 is what let every redirect-to-block host through as a
    success until 2026-07-30. The body comes from the last hop, so that is what
    `status_code` reports and what block detection sees."""
    outcome = production_path.crawl(
        fixture_origin.url("/redirect-to/block/varnish-403"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert outcome.status_code == 403, "the 301 must not be reported as the status"
    assert outcome.result["redirected_status_code"] == 403
    assert not outcome.success
    assert outcome.failure_class == "origin_blocked"


def test_a_benign_redirect_stays_a_success(fixture_origin, production_path):
    """The other direction, which the fix must not have cost us: apex -> www
    into a healthy page is still a plain success."""
    outcome = production_path.crawl(
        fixture_origin.url("/redirect-to/ok"), delay_before_return_html=SHORT_WAIT
    )

    assert outcome.success
    assert outcome.status_code == 200
    assert CONTENT_MARKER in outcome.markdown


# ── body-swallowing markup (tasks/cleaned-html-collapse-guard.md) ────────


@pytest.mark.parametrize("shape", sorted(set(COLLAPSE_SHAPES) - {"unclosed-noscript"}))
def test_no_markup_shape_swallows_the_body(shape, fixture_origin, production_path):
    """test_noscript_body_collapse.py pins the scraping strategy in isolation;
    this pins the whole path, which is where the loss was actually observed —
    HTTP 200, `success: true`, one character of markdown, for 406 pages across
    70 hosts over 3.5 months.

    Parameterised over the shape family so the next member is a dict entry.
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/collapse/{shape}"), delay_before_return_html=SHORT_WAIT
    )

    assert outcome.success, outcome.error_message
    assert CONTENT_MARKER in outcome.markdown, f"{shape}: body swallowed"
    assert "Referenssit" in outcome.markdown, f"{shape}: trailing content lost"


def test_an_unclosed_noscript_still_swallows_the_body(fixture_origin, production_path):
    """FOUND BY THIS FIXTURE, 2026-07-31. Pinned as today's behaviour.

    `strip_noscript()` fixed the *nested* shape, and
    test_noscript_body_collapse.py reports the unclosed shape fixed too — but
    that suite feeds the raw string to libxml2, which auto-closes the element,
    so the body survives and the test passes. Chromium does the opposite: an
    unclosed `<noscript>` puts the parser into raw-text mode, so the rest of the
    document — `</body></html>` included — is serialized *inside* the element.
    `strip_noscript()` then correctly removes the element and takes the page
    with it.

    Result: the body in, `<html><head><title>…</title></head></html>` out, one
    newline of markdown, at HTTP 200 `success: true`. The same silent whole-body
    loss that ran 3.5 months, surviving its own fix through a parser difference
    that only a browser in the loop can show.

    This route serves ~309 bytes by default — the *shape*, not the size. Pass
    `?bytes=73000` to reproduce `apteam.fi`'s 73,970-byte fingerprint; the
    collapse guard's thresholds are ratios and must be sized against the padded
    form, never against this one.

    This belongs to tasks/cleaned-html-collapse-guard.md (#2), which is gated on
    this fixture precisely so it can be worked offline. Invert this test when
    the guard ships.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/collapse/unclosed-noscript"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert (
        "<noscript>" in outcome.html and CONTENT_MARKER in outcome.html
    ), "the browser did serve us the content; the loss is downstream"
    assert CONTENT_MARKER not in outcome.markdown
    assert outcome.markdown.strip() == "", "TODAY'S BEHAVIOUR — whole body lost"
    assert outcome.success, "and silently: HTTP 200, success:true, no error"
    assert outcome.failure_class == "none"


# ── our own faults (the wall-clock fence) ────────────────────────────────
# Last in the file: the fence cancels an in-flight render, and there is no
# reason to make every other test depend on how cleanly that unwinds.


def test_the_wall_clock_fence_is_a_504_and_ours(fixture_origin, production_path):
    """A stalled origin must hit the fence and be reported as our timeout, not
    as the origin's failure — `render_timeout` is one of the two classes that
    keeps a 5xx, because MAS should retry it.

    `?stall=` is a server-side sleep, so this is the only knob needed to
    reproduce any future timeout class; no route change required.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/ok", stall=3),
        wall_clock_s=1,
        delay_before_return_html=SHORT_WAIT,
    )

    assert outcome.http_status == 504
    assert outcome.envelope is None
    assert outcome.elapsed_s < 3, "the fence must fire before the origin answers"
