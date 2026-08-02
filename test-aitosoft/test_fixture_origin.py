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
    BODY_SWALLOWING_SHAPES,
    COLLAPSE_SHAPES,
    CONTENT_MARKER,
    CONTENT_TAIL_MARKER,
    DOWNLOAD_KINDS_THAT_REFUSE_TO_RENDER,
    GUARD_BLIND_SHAPES,
    RECOVERABLE_SHAPES,
    loopback_allowed,
)

#: apteam.fi's fingerprint: 73,970 bytes of HTML, 96 bytes of `cleaned_html`,
#: 1 character of markdown, byte-identical across two visits forty minutes
#: apart. The collapse guard is a **ratio**, so every shape has to be measured
#: at a realistic size — the unpadded route serves 1.5 KB, and a 1.5 KB page
#: that collapses is not a collapse by any threshold worth shipping.
COLLAPSE_BYTES = 73000

# Resolution delays chosen so neither case is a race against the pipeline's own
# overhead. Measured 2026-07-31: everything between `page.goto` returning and
# the capture — consent-popup removal, the settle steps, `delay_before_return_html`
# — costs ~0.5 s even at the shortest wait, so a 0.5 s interstitial resolves
# before a "too early" capture can miss it.
LATE_S = 5.0  # further out than any capture wait: the interstitial is what we get
EARLY_S = 0.5  # inside a 2.0 s capture wait: the content is what we get

SHORT_WAIT = 0.1  # `delay_before_return_html` — capture as soon as possible
MAS_WAIT = 2.0  # what MAS sends in production

#: What MAS sends in production (CLAUDE.md's per-request customization block).
#: It is not a default — `DEFAULT_CRAWLER_CONFIG` omits it, so upstream uses 0 —
#: and it changes the *error text* a navigation failure produces, not only the
#: cost. Any test that asserts on error text must say which it ran with.
MAS_MAX_RETRIES = 2


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
def test_a_challenge_that_outlasts_the_first_capture_is_rescued_by_the_retry(
    route, fixture_origin, production_path
):
    """PHASE 2, inverted 2026-08-01. This used to assert the opposite.

    It was `test_an_interstitial_captured_too_early_is_the_result_we_keep`, and
    it pinned MAS's observed shape: HTTP 202 with the challenge screen stored as
    the page. A 5 s challenge outlasts a 0.1 s capture wait, the interstitial is
    what we kept, and the patchright retry could not help because it was handed
    the **same** `CrawlerRunConfig` — a different engine on an identical budget.

    tasks/challenge-interstitial-resolve.md phase 2 gives that retry its own,
    longer capture wait (10 s, so `W + 1.22` covers challenges up to 11.2 s).
    The rescue costs zero extra page loads, because the second fetch already
    happened for every detected block.

    Note what the first attempt still has to do: **detect**. The recovery is
    triggered by the detector, so it can only ever reach challenges we already
    call blocked. `/challenge/never?marker=none` is the family this cannot
    touch, and it is pinned separately.
    """
    fixture_origin.reset_hits()
    outcome = production_path.crawl(
        fixture_origin.url(f"/challenge/{route}/{LATE_S}"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert outcome.success, outcome.error_message
    assert outcome.status_code == 202, "202 serves the real page too, not just the wall"
    assert outcome.failure_class == "none"
    assert CONTENT_MARKER in outcome.markdown
    assert "robot-suspicion" not in outcome.html

    # The rescue came from the retry we already pay for, not from a third fetch.
    assert fixture_origin.hits_for(f"/challenge/{route}") == 2


def test_the_retry_leg_costs_the_raised_wait_and_no_more(
    fixture_origin, production_path
):
    """The measurement phase 1's block-B footnote explicitly asked for.

    Phase 1 modelled a wall as `2 x (W + 1.22)` and found one cell that misfits:
    W=10 measured 25.22 s against 22.44 s predicted. That cell is the closest
    analogue to what phase 2 does — raise the wait on the retry — so the leg had
    to be measured directly rather than assumed.

    Measured here: the retry's own fetch takes `retry_wait + 1.22 s`, the same
    constant as any other capture. So the retry leg is NOT where the extra
    2.78 s lives (patchright singleton startup is the remaining candidate, and
    it is a one-off per process, not per request). The bound below is loose on
    purpose — it is a fence check, not a benchmark.
    """
    from aitosoft_patchright_fallback import _retry_capture_wait_s

    retry_wait = _retry_capture_wait_s()
    outcome = production_path.crawl(
        fixture_origin.url("/challenge/never"), delay_before_return_html=SHORT_WAIT
    )

    assert not outcome.success, "a wall stays a wall however long we wait"
    assert outcome.failure_class == "origin_blocked"
    # first capture (~SHORT_WAIT + 1.22) + retry (~retry_wait + 1.22) + startup.
    assert (
        outcome.elapsed_s > retry_wait
    ), f"the retry did not get the longer wait: {outcome.elapsed_s:.1f}s"
    assert outcome.elapsed_s < retry_wait + 15, (
        f"the retry leg cost more than the raised wait explains: "
        f"{outcome.elapsed_s:.1f}s for a {retry_wait}s wait"
    )


def test_the_happy_path_never_pays_for_the_retry(fixture_origin, production_path):
    """The other half of phase 2's cost argument, asserted rather than reasoned.

    A page that captures cleanly must be fetched exactly once and must not wait
    the retry's budget. If this ever fails, the raised wait has leaked onto the
    population it was specifically designed to avoid — which is what makes a
    global `delay_before_return_html: 10.0` cost ~267 render-hours per sweep.
    """
    from aitosoft_patchright_fallback import _retry_capture_wait_s

    fixture_origin.reset_hits()
    outcome = production_path.crawl(
        fixture_origin.url("/ok"), delay_before_return_html=MAS_WAIT
    )

    assert outcome.success
    assert fixture_origin.hits_for("/ok") == 1, "the happy path re-fetched"
    assert (
        outcome.elapsed_s < _retry_capture_wait_s()
    ), f"a clean capture waited the retry's budget: {outcome.elapsed_s:.1f}s"


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
    """The silent case, still pinned as today's behaviour — deliberately.

    Strip the vendor marker and the "Just a moment" title and one sentence of
    Finnish prose is enough to clear every tier: ~50 characters of markdown come
    back at `success: true, failure_class: none`.

    **Re-measured 2026-08-01, and the received diagnosis was incomplete.** The
    story was "tier 3 does not fire because the page has an <h1> and a <p> in
    it, which is all `has content elements` means". True, but it also misses
    `minimal_text` by one character: the visible text is exactly 50 and the
    signal needs `< 50`. So the page scores **zero** signals, not one, and no
    adjustment to the content-element rule alone would have caught it.

    tasks/detector-round3-evidence-vs-inference.md asked for this to be fixed in
    the same pass as the padded block. It is not, and the reason is that same
    task's other half. This page carries **no evidence** — no vendor marker, no
    interstitial prose, no refusal notice, nothing but "Odota hetki" and a
    Finnish sentence. The only rule that could catch it is "a page with very
    little text is a block", which is inference, and this image exists partly to
    stop inference claiming `origin_blocked` — it cost MAS a healthy host
    (`norex.com`). Inventing the rule here would re-create that defect pointed
    at every small real page in a 117,000-page corpus.

    So the honest state is: we cannot detect this family, and we cannot count
    it either. That is the ceiling
    tasks/challenge-interstitial-resolve.md's block C already identified, and
    only MAS's stored corpus can size it. Recorded here rather than papered
    over with a threshold.
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


@pytest.mark.parametrize("shape", ["heading", "bare"])
def test_a_padded_block_page_is_detected(fixture_origin, production_path, shape):
    """DEFECT A, **inverted 2026-08-01**. This asserted today's defect until the
    block-notice tier shipped; it now proves the fix fires.

    Every size gate in antibot_detector used to be on `len(html)` — tier 2 at
    10 KB, tier 3 at 50 KB — and the vendor pads its block page to ~80 KB, so a
    page with 48 characters on it sailed through as content at `success: true`,
    `failure_class: none`. That is the "green counter" failure mode MAS called
    the most expensive thing that happened to them this month, and it happened
    on four of the eight hosts they measured in prod.

    Both shapes are parameterised because they fail differently and only one of
    them is what production served. `heading` is the real page (an `<h1>` and a
    `<p>`, from MAS's stored markdown); `bare` is a `<div>`. Moving the size
    gate alone would have "fixed" `bare` — a bare div has no content elements,
    so tier 3 scores two signals — while leaving `heading`, which scores one,
    exactly as broken. The fixture served `bare` by default until today.

    Note the class: `origin_blocked`, not `render_defect` or `render_error`.
    The origin's own bytes state the refusal, so this is evidence, and evidence
    outranks the inference tiers — which the same image just stopped letting
    claim `origin_blocked` at all. The two halves have to agree here or one of
    them is wrong.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/block/padded-403", shape=shape),
        delay_before_return_html=SHORT_WAIT,
    )

    assert len(outcome.html) > 50_000, "the padding is the mechanism"
    assert len(outcome.markdown.strip()) < 200, "a block notice, not a page"

    assert not outcome.success
    assert outcome.failure_class == "origin_blocked"
    assert outcome.status_code == 202, "the origin's real status rides along"
    assert outcome.http_status == 200, "5xx is reserved for our own faults"


@pytest.mark.parametrize("shape", ["heading", "bare"])
def test_the_padding_is_no_longer_the_difference(
    fixture_origin, production_path, shape
):
    """The same notice with the padding removed must reach the same verdict.

    Before the fix this passed for a different reason than it does now, and the
    difference is the whole of defect B. Unpadded, the `bare` shape was caught
    by **tier 3** — `Structural: minimal_text, no_content_elements` — which is
    us inferring a block from an empty-looking page, not the origin telling us
    anything. This image stops such reasons meaning `origin_blocked`, so if the
    block-notice tier did not catch these first, this assertion would now read
    `render_error`. It passing is the two defects composing correctly.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/block/padded-403", bytes=0, shape=shape),
        delay_before_return_html=SHORT_WAIT,
    )

    assert not outcome.success
    assert outcome.failure_class == "origin_blocked"


def test_a_healthy_page_is_never_a_block_notice(fixture_origin, production_path):
    """The false-positive tripwire for the tier above, through the real path.

    The block-notice tier fires at any status and any size, so the only thing
    keeping it honest is that a real page has text. This is the same page every
    other route uses as its success control.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/ok"), delay_before_return_html=SHORT_WAIT
    )

    assert outcome.success
    assert outcome.failure_class == "none"
    assert CONTENT_MARKER in outcome.markdown


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


def test_a_shell_that_paints_inside_the_retry_budget_is_rescued(
    fixture_origin, production_path
):
    """An unplanned dividend of phase 2, found by this test going green.

    This asserted `not outcome.success`: a shell captured 0.1 s in, before its
    5 s hydration, came back degenerate. Nobody refused us — it is not a block —
    but tier 3 calls a near-empty page blocked, and that verdict is what arms
    the patchright retry. With the retry now waiting 10 s, the page has painted
    by the time it is captured.

    This is **MAS's `revisol.fi` class**: they measured 361,900 / 242 / 1 at
    `delay_before_return_html: 2.0` and 598,937 / 101,091 / 21,921 at 10 — a
    capture-timing failure on their side of the split, which we now absorb
    server-side for the population that already costs two page loads. Their
    half of tasks/cleaned-html-collapse-guard.md gets smaller for free.
    """
    fixture_origin.reset_hits()
    outcome = production_path.crawl(
        fixture_origin.url(f"/hydrate-after/{LATE_S}"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert outcome.success, outcome.error_message
    assert outcome.status_code == 200
    assert CONTENT_MARKER in outcome.markdown
    assert fixture_origin.hits_for("/hydrate-after") == 2, "rescued by the retry"


def test_a_shell_that_never_paints_is_ours_and_retryable(
    fixture_origin, production_path
):
    """The other side, and the cost of defect B stated as an assertion.

    A shell that outlasts the retry's budget too is still degenerate. Its only
    verdict is tier 3's `Structural: minimal_text` — *inference*, not the origin
    refusing us — so this image stops it claiming `origin_blocked` and it lands
    on `render_error`: **HTTP 500, which MAS retries three times.**

    That is a real cost and it is the intended direction: a capture that came
    back with nothing is ours, and it is transient, which is what a retry is
    for. Note what it is not — before this change MAS was told a healthy site
    was blocked, which is the failure mode they called the most expensive thing
    that happened to them this month.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/hydrate-after/60"),
        delay_before_return_html=SHORT_WAIT,
    )

    assert not outcome.success
    assert len(outcome.markdown.strip()) < 500, "MAS's DEGENERATE_CAPTURE_CHARS floor"
    assert CONTENT_MARKER not in outcome.markdown
    assert outcome.failure_class == "render_error", "ours, not the origin's"
    assert outcome.http_status == 500, "retryable, deliberately"


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


def test_the_healthy_control_is_not_degenerate(fixture_origin, production_path):
    """The control every other test leans on has to be a *healthy* page by the
    customer's own definition, and until 2026-08-01 it was not: CONTENT_HTML
    rendered to ~140 markdown characters, below MAS's
    `DEGENERATE_CAPTURE_CHARS = 500`. A capture that succeeds completely while
    tripping their degenerate floor is not a control.

    It matters most here, because this task's entire output is a threshold and
    the guard's visible-text floor is 500 characters. Sized against the old
    control, the guard would have been tuned to fire on healthy small pages.

    Note the unit on each side: 500 is **markdown characters**, and the collapse
    ratio is markdown characters per **visible-text character**. Both are text;
    `len(html)` is bytes and is deliberately absent from both.
    """
    outcome = production_path.crawl(
        fixture_origin.url("/ok"), delay_before_return_html=SHORT_WAIT
    )

    assert outcome.success
    assert len(outcome.markdown) > 500, (
        f"the healthy control renders {len(outcome.markdown)} markdown chars, "
        "which MAS would record as a degenerate capture"
    )
    assert CONTENT_MARKER in outcome.markdown
    assert CONTENT_TAIL_MARKER in outcome.markdown


@pytest.mark.parametrize("shape", sorted(set(COLLAPSE_SHAPES) - BODY_SWALLOWING_SHAPES))
def test_no_markup_shape_swallows_the_body(shape, fixture_origin, production_path):
    """test_noscript_body_collapse.py pins the scraping strategy in isolation;
    this pins the whole path, which is where the loss was actually observed —
    HTTP 200, `success: true`, one character of markdown, for 406 pages across
    70 hosts over 3.5 months.

    Parameterised over the shape family so the next member is a dict entry.
    Served at `apteam.fi`'s size, because a shape that is harmless at 1.5 KB can
    still cross a size-dependent limit at 73 KB — `deep-nesting` does exactly
    that.
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/collapse/{shape}", bytes=COLLAPSE_BYTES),
        delay_before_return_html=SHORT_WAIT,
    )

    assert outcome.success, outcome.error_message
    assert CONTENT_MARKER in outcome.markdown, f"{shape}: body swallowed"
    assert CONTENT_TAIL_MARKER in outcome.markdown, f"{shape}: trailing content lost"


@pytest.mark.parametrize("shape", sorted(RECOVERABLE_SHAPES))
def test_a_swallowed_body_is_recovered(shape, fixture_origin, production_path):
    """The body comes back. This is the only test in the file that returns
    customer data rather than describing its loss.

    Our parse still drops these pages — that root cause is untouched — but the
    guard now takes a second opinion from html2text over the *same* rendered
    HTML, and for these two shapes it returns the content. The capture is served
    as an ordinary success, because MAS's client reads `success` and would
    discard content attached to a failure.

    Asserting the **tail** marker matters as much as the first: a recovery that
    returned the heading and stopped would look identical on `CONTENT_MARKER`
    alone, and that is exactly how the `<noscript>` loss hid for 3.5 months.
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/collapse/{shape}", bytes=COLLAPSE_BYTES),
        delay_before_return_html=SHORT_WAIT,
    )

    assert outcome.success, f"{shape}: {outcome.failure_class} {outcome.error_message}"
    assert outcome.http_status == 200
    assert outcome.failure_class == "none"
    assert CONTENT_MARKER in outcome.markdown, f"{shape}: recovery lost the body"
    assert CONTENT_TAIL_MARKER in outcome.markdown, f"{shape}: recovery lost the tail"
    assert len(outcome.markdown) > 500, (
        f"{shape}: recovered {len(outcome.markdown)} chars, under MAS's "
        "DEGENERATE_CAPTURE_CHARS — it should not have been accepted at all"
    )


@pytest.mark.parametrize(
    "shape", sorted(BODY_SWALLOWING_SHAPES - GUARD_BLIND_SHAPES - RECOVERABLE_SHAPES)
)
def test_an_unrecoverable_collapse_is_reported_as_a_defect(
    shape, fixture_origin, production_path
):
    """The net underneath recovery. THIS TEST WAS INVERTED on 2026-08-01 — it
    used to assert the loss was silent — and **narrowed on 2026-08-02**, when
    recovery took two of its three shapes away.

    What is left is the case where html2text agrees the page is empty. The loss
    is real and permanent, so it is reported: `success: false`,
    `failure_class: render_defect`, content still attached.

    On the wire it is **HTTP 200**, and that is the load-bearing half. MAS's
    retry branch is `retryableStatuses.includes(response.status)`, evaluated
    before the body is parsed (their message 09), so 200 costs zero retries —
    which is right, because all four shapes are deterministic and a second
    render would collapse identically. 500 would have bought three of them.
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/collapse/{shape}", bytes=COLLAPSE_BYTES),
        delay_before_return_html=SHORT_WAIT,
    )

    assert (
        CONTENT_MARKER in outcome.html
    ), f"{shape}: the browser did serve us the content; the loss is downstream"
    assert (
        CONTENT_MARKER not in outcome.markdown
    ), f"{shape}: recovery now reads this shape — move it into RECOVERABLE_SHAPES"

    assert not outcome.success, f"{shape}: the loss is silent again"
    assert outcome.failure_class == "render_defect"
    assert outcome.http_status == 200, "a permanent defect must not be retried"
    assert "collapsed" in outcome.error_message


@pytest.mark.parametrize("shape", sorted(GUARD_BLIND_SHAPES))
def test_a_body_swallowed_into_a_script_is_still_silent(
    shape, fixture_origin, production_path
):
    """TODAY'S BEHAVIOUR, pinned so the blind spot is recorded rather than
    forgotten.

    `unclosed-script` puts the entire document inside a `<script>` element, and
    the guard's visible-text measure strips script blocks — it has to, since
    real pages carry hundreds of KB of inline JS and counting it would collapse
    the ratio that makes the guard safe. So this capture is indistinguishable
    from a legitimately empty page, and comes back green.

    This is the pre-parse repair's job, not the guard's. Invert this test when
    that lands (tasks/cleaned-html-collapse-guard.md part 2).
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/collapse/{shape}", bytes=COLLAPSE_BYTES),
        delay_before_return_html=SHORT_WAIT,
    )

    assert CONTENT_MARKER not in outcome.markdown
    assert outcome.success, "TODAY'S BEHAVIOUR — the guard cannot see this one"
    assert outcome.failure_class == "none"


# ── URLs that are not pages (download-navigation-is-not-a-render-error.md) ──


@pytest.mark.parametrize("kind", sorted(DOWNLOAD_KINDS_THAT_REFUSE_TO_RENDER))
def test_a_download_is_not_a_retryable_server_error(
    kind, fixture_origin, production_path
):
    """A `GetVCard` endpoint produced **every** HTTP 500 of MAS's 2026-08-01
    run: Chromium refuses to commit a navigation to a download, the error text
    matched nothing in the taxonomy, and `render_error` at 500 bought three
    retries of a URL that will do exactly the same thing forever.

    `unrenderable_content` is the honest name — the origin answered correctly
    and we behaved correctly; the response is simply not a page. The wire status
    is the whole contract (MAS's message 09) and 200 is what stops the retries.

    Parameterised over five kinds because the first draft of this fixture
    assumed `Content-Disposition: attachment` was the trigger. It is not: an
    inline `text/vcard`, an inline `application/pdf` and an
    `application/octet-stream` all fail identically. That answers the task
    file's open question — the class is a shape of MAS's corpus, not one URL.

    `max_retries` is MAS's production value on purpose: at the default of 0 the
    error text reads `Unexpected error in _crawl_web …` and at 1 or more it
    reads `All proxies failed: …`. Only `Download is starting` is common to
    both, which is why the pattern matches on that alone.
    """
    outcome = production_path.crawl(
        fixture_origin.url(f"/download/{kind}"),
        delay_before_return_html=SHORT_WAIT,
        max_retries=MAS_MAX_RETRIES,
    )

    assert outcome.http_status == 200, "a permanent failure must not be retried"
    assert not outcome.success
    assert outcome.failure_class == "unrenderable_content", (
        f"{kind}: {outcome.error_message[:200]!r} — if this now succeeds, the "
        "browser build renders it inline and the kind should leave "
        "DOWNLOAD_KINDS_THAT_REFUSE_TO_RENDER"
    )
    assert "Download is starting" in outcome.error_message


def test_a_download_costs_a_page_load_per_retry_round(fixture_origin, production_path):
    """The multiplier, measured rather than inferred.

    The task file priced this at "4 hits = one attempt plus MAS's three
    retries". That undercounts by upstream's own attempt loop: `arun` retries on
    **any** exception, not only on a detected block, so one client request at
    `max_retries: 2` is three navigations. Four client requests were 8-12 page
    loads, not 4 — which makes the fix worth more, not less.

    Pinned here because it is the number that justifies an XS task, and because
    it is checkable with zero live traffic: `crawl_stats.attempts` already ships
    in the envelope MAS stores.
    """
    fixture_origin.reset_hits()
    outcome = production_path.crawl(
        fixture_origin.url("/download/vcard"),
        delay_before_return_html=SHORT_WAIT,
        max_retries=MAS_MAX_RETRIES,
    )

    assert fixture_origin.hits_for("/download/vcard") == MAS_MAX_RETRIES + 1
    assert outcome.result.get("crawl_stats", {}).get("attempts") == MAS_MAX_RETRIES + 1


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


# ── the realistic-page instrument (tasks/pool-residency-unbounded.md) ─────


def test_the_heavy_route_has_the_shape_of_a_real_page(fixture_origin):
    """`/heavy` exists to price a pool browser against a page like the ones we
    actually crawl, because the 139-165 MB per-browser figure — the input to
    the `max_browsers` cap — was measured against `/ok`, which is 1.5 KB of
    markup with no images.

    Pinned because an instrument that drifts silently changes a capacity
    number nobody re-measures. The targets are the median of 62 stored real
    captures under `test-aitosoft/artifacts/`: 236 KB, 17 `<img>`, 876 tags.
    Bands are wide — this asserts "still the right order of magnitude", not a
    byte count.

    The decoded-image term is the part `/ok` cannot show at all: a solid-colour
    PNG costs a few KB on the wire and `w*h*4` bytes in the renderer, and
    `config.yml` sets `text_mode: false` so production really does decode them.
    """
    import re
    import urllib.request

    html = urllib.request.urlopen(fixture_origin.url("/heavy")).read().decode()

    assert 150_000 < len(html) < 400_000, f"heavy page is {len(html)} bytes"
    assert len(re.findall(r"<img", html)) == 17
    assert 600 < len(re.findall(r"<[a-zA-Z]", html)) < 1500

    png = urllib.request.urlopen(fixture_origin.base_url + "/img/1920x1080.png").read()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) < 100_000, "wire bytes must stay small; the decode is the cost"


def test_the_heavy_page_captures_successfully(fixture_origin, production_path):
    """It has to be a *healthy* page, or a memory figure taken against it is a
    figure for a failed capture. Same contract as the `/ok` control."""
    outcome = production_path.crawl(
        fixture_origin.url("/heavy"), delay_before_return_html=SHORT_WAIT
    )

    assert outcome.success, outcome.failure_class
    assert CONTENT_MARKER in outcome.markdown
    assert CONTENT_TAIL_MARKER in outcome.markdown, "the tail was swallowed"
