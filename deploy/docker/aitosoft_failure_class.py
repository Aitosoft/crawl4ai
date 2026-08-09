"""
Aitosoft: origin-vs-crawler failure classification (``failure_class``).

Why this exists
---------------
Under the single-URL contract, *every* full-mode failure used to reach MAS as
an opaque HTTP 500:

    server.py  if all(not r["success"] …): raise HTTPException(500, …)
    server.py  if exc.status_code == 500: -> {"error": "Internal server error"}

A 403 block page, a wedged render and an origin's own 5xx were byte-identical
on the wire — `status_code`, `redirected_status_code`, `error_message` and
`crawl_stats` were all discarded. MAS treats 500 as retryable (3 retries), so a
permanently broken customer site cost four browser renders to learn nothing and
was recorded as *our* fault (`anitamakela.com`: 8 retries in 35 s, 2026-07-27).

Contract (MAS answered Q2 (a) unreservedly, 2026-07-30):

    Anything the origin caused  =>  HTTP 200, result `success: false`,
                                    `failure_class`, `status_code` = the
                                    origin's real *final* status.
    Only our own faults keep 5xx:   render_error -> 500, render_timeout -> 504.
    Capacity keeps                  429 + Retry-After.

The axis turned out to be **permanence, not ownership** (2026-08-01), so there
is a third bucket the original contract had no room for: failures that are not
the origin's and still must not be retried. `render_defect` (our parse lost the
body) and `unrenderable_content` (the URL is a download, which is nobody's
fault) both live there, both at 200. `NON_RETRYABLE_CLASSES` is that bucket
plus the origin's; `ORIGIN_CLASSES` stays the answer to "whose fault", which is
a separate question and must not decide a status. Conflating the two is the
original defect, and it re-appeared in `api.py`'s exception gate as late as
2026-08-02.

`failure_class` is present on **every** result including successes (as
``"none"``), so a missing field never needs interpretation — it means an old
build, not a success. Request-scoped failures that have no result to attach to
(capacity, auth, malformed request) carry `failure_class` at envelope level
instead; that division of labour is MAS's, not duplication.

Static mode (``aitosoft_static_mode.py``) has always had this shape — network
failures never raise, they become ``success=false`` inside a 200 — and is the
reference implementation this module brings full mode in line with.

Classification bias
-------------------
Unrecognised failures classify as ``render_error`` (ours, 500, retryable), not
as an origin class. Getting it wrong in that direction costs wasted renders and
is loud. Getting it wrong the other way tells MAS a healthy company site is
permanently broken, silently — the "green counter" failure mode they called the
most expensive thing that happened to them this month.

See tasks/origin-vs-crawler-failure-classification.md and
tasks/waa-eval-2026-07-30-forensics.md §2a, §3.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# ── the vocabulary ───────────────────────────────────────────────────────
# Result-level.
NONE = "none"
ORIGIN_HTTP_ERROR = "origin_http_error"  # origin answered 4xx/5xx
ORIGIN_BLOCKED = "origin_blocked"  # anti-bot / WAF / edge block
ORIGIN_UNREACHABLE = "origin_unreachable"  # DNS / TCP / TLS never got there
RENDER_TIMEOUT = "render_timeout"  # our wall-clock fence fired
RENDER_ERROR = "render_error"  # our browser/pipeline broke, transiently
# Ours and PERMANENT. Originally "our parse lost the body"; widened 2026-08-06
# to "the body is gone and we are the reason", which also covers our own
# injected JS having removed the document root. Keyed on the shape of the
# damage, not on the mechanism, so the next mechanism lands here too.
RENDER_DEFECT = "render_defect"
UNRENDERABLE_CONTENT = "unrenderable_content"  # served fine; it is not a page

# Normally envelope-level (no result exists to carry them).
CAPACITY = "capacity"  # render gate rejected -> 429
AUTH = "auth"  # 401/403 from us, not the origin
BAD_REQUEST = "bad_request"  # malformed request -> 400
# ...except BAD_REQUEST, which static mode also attaches to a *result* when a
# redirect hop is refused by the egress broker. That result must never be
# retried, so it has to be in NON_RETRYABLE_CLASSES below — routing static mode
# through `http_status_for` without it turns an SSRF refusal into a 500 and buys
# MAS three more attempts at a URL our own policy has already declined.


class OriginUnresolvable(Exception):
    """A seed URL's hostname resolved to no address at all (NXDOMAIN/SERVFAIL).

    The SSRF seed check (`utils.validate_url_destination`) deliberately
    collapses "no such name" and "resolved, but policy refused it" into one
    opaque HTTP 400 — right for a policy verdict, wrong for a lapsed domain,
    which is an ORIGIN failure and owes MAS a `failure_class`. A
    company-registry sweep is mostly lapsed domains, so without this every one
    of them reached MAS as `URL blocked (SSRF protection)`: our own policy
    string blaming a customer's domain, with no class attached. That is the
    `norex.com` inversion again, on a population that is certainly non-zero.

    Raised by `api._normalize_and_validate_seeds`; `classify_exception` maps it
    to ORIGIN_UNREACHABLE, whose own comment above has always claimed DNS.
    """


#: Classes the origin is responsible for. These must never be reported as 5xx.
ORIGIN_CLASSES = frozenset({ORIGIN_HTTP_ERROR, ORIGIN_BLOCKED, ORIGIN_UNREACHABLE})

#: Everything that must NOT come back as a retryable 5xx, whoever caused it.
#:
#: The distinction the taxonomy was missing is **permanence, not ownership**.
#: `render_defect` is entirely our fault, and retrying it is still pointless:
#: the same markup will collapse the same way on every attempt (all four
#: reproducible shapes return byte-identical HTML across visits). MAS's retry
#: branch keys on the wire status alone — `failure_class` is received, logged
#: and unread (their message 09) — so serving this at 500 would buy three more
#: renders of a page we already know we cannot parse, and 500 is exactly where
#: `render_error` sits.
#:
#: Ownership still lives in the class *name*, which is what we debug from and
#: what they may eventually branch on. It just no longer decides the status.
#:
#: `UNRENDERABLE_CONTENT` is the third thing that is neither: nobody's fault at
#: all. The origin answered correctly with a file, we behaved correctly, and a
#: browser will refuse that navigation on every future attempt.
NON_RETRYABLE_CLASSES = ORIGIN_CLASSES | {
    RENDER_DEFECT,
    BAD_REQUEST,
    UNRENDERABLE_CONTENT,
}

# ── error-text signals ───────────────────────────────────────────────────
# All string matching against crawler/browser error text lives here. Do not
# scatter it: every call site that needs a verdict calls classify_error_text().

_NET_ERR_RE = re.compile(r"\bnet::(ERR_[A-Z0-9_]+)")

# The origin answered, but with something Chromium refuses to render.
_NET_ORIGIN_HTTP_ERRORS = frozenset(
    {
        # Non-2xx whose body Chromium will not commit — this is anitamakela.com's
        # genuine Apache 500 with a zero-byte body.
        "ERR_HTTP_RESPONSE_CODE_FAILURE",
        "ERR_INVALID_HTTP_RESPONSE",
        "ERR_EMPTY_RESPONSE",
        "ERR_RESPONSE_HEADERS_TRUNCATED",
        "ERR_CONTENT_LENGTH_MISMATCH",
        "ERR_INCOMPLETE_CHUNKED_ENCODING",
        "ERR_TOO_MANY_REDIRECTS",
    }
)

# We never got a usable connection to the origin.
_NET_ORIGIN_UNREACHABLE_ERRORS = frozenset(
    {
        "ERR_INTERNET_DISCONNECTED",
        "ERR_NETWORK_CHANGED",
        "ERR_TIMED_OUT",
    }
)

# Prefix families, so an unlisted member of a known family still classifies.
_NET_ORIGIN_UNREACHABLE_PREFIXES = (
    "ERR_NAME_",  # NAME_NOT_RESOLVED, NAME_RESOLUTION_FAILED
    "ERR_CONNECTION_",  # REFUSED, RESET, CLOSED, TIMED_OUT, FAILED, ABORTED
    "ERR_ADDRESS_",  # UNREACHABLE, INVALID
    "ERR_SOCKET_",  # NOT_CONNECTED
    "ERR_SSL_",  # every TLS handshake failure
    "ERR_CERT_",  # every certificate failure
    "ERR_BAD_SSL_",
    "ERR_TUNNEL_",
    "ERR_PROXY_",
)

_BLOCKED_RE = re.compile(
    r"Blocked by anti-bot protection|\[patchright\] STILL blocked", re.IGNORECASE
)

# Aitosoft 2026-08-01 — the evidence/inference split.
#
# `is_blocked` returns one verdict for two different kinds of finding, and
# `_BLOCKED_RE` above used to map both to ORIGIN_BLOCKED:
#
#   the origin said so       a vendor marker, an interstitial, a refusal notice,
#                            HTTP 403 with an HTML body   -> the origin blocked us
#   we inferred it from shape "Structural: minimal_text…", "Near-empty content…"
#                            -> *we* came back with nothing
#
# The second is RENDER_ERROR's definition, not ORIGIN_BLOCKED's. MAS measured
# the consequence on 2026-07-31: 4 of their 33 `origin_blocked` verdicts were
# this, and the expensive one was `norex.com`.
#
# `norex.com` is worth stating precisely, because the loose phrasing that used to
# be here ("our own placeholder in 15 bytes of HTML") conflates TWO FIELDS and
# cost four sessions, each of which went looking at the anti-bot tier when the
# cause was our own DOM handling:
#   * `html` was **15 bytes** — a bare `<!DOCTYPE html>`, because a script had
#     removed `documentElement`. That is the *input*.
#   * `Crawl4AI Error: This page is not fully supported` is what our **scraper
#     generated from** those 15 bytes, once lxml raised `Document is empty`.
#     That is the *output*, and it is not in the 15 bytes.
# Both statements were individually true; read as one they describe a page that
# never existed. The 2026-08-06 consent-guard work found the actual cause — our
# own `remove_consent_popups.js` deleting the root (`tasks/done/
# consent-scripts-delete-the-page.md`). Whatever the input, the outcome was our
# pipeline's failure reported to the customer as the origin blocking them.
#
# This module's documented bias (see "Classification bias" above) is that
# an unrecognised failure is ours and never an origin class, "precisely so that
# a healthy site is never reported permanently broken". This was that guarantee
# running backwards.
#
# Matching reason text is done HERE rather than at the call site because that is
# this module's whole job — no other file matches on crawler error strings. The
# seam is the reason *prefix*, which antibot_detector's inference tiers are
# required to keep; `test_failure_classification.py` walks every reason
# `is_blocked` can produce and fails if one lands on neither side of this line.
#
# What this changes for MAS, stated plainly because it is not free: these
# results move from `origin_blocked` (HTTP 200, terminal) to `render_error`
# (HTTP 500, retried 3x), so we buy back three renders per occurrence. That is
# the correct direction — a transient failure of ours is exactly what a retry
# is for — but it is a cost, and `snuup.fi`'s ordinary 404 is the case that
# gets strictly cheaper: it falls through to ORIGIN_HTTP_ERROR, still 200.
_INFERRED_BLOCK_RE = re.compile(
    r"Blocked by anti-bot protection:\s*(?:Structural:|Near-empty content)",
    re.IGNORECASE,
)

# The URL is a download, not a page. Chromium will not commit a navigation to a
# response it is going to save to disk, so `page.goto` raises before anything is
# rendered — and the text carries no `net::ERR_*`, no status and no block marker,
# so it used to fall through to RENDER_ERROR at 500 and buy MAS three retries of
# a URL that will do exactly the same thing forever. One `GetVCard` endpoint
# produced every 500 of the 2026-08-01 run, four renders for one URL.
#
# This is NOT a weakening of the documented classification bias below. That bias
# is about the *unrecognised* set, and "Download is starting" has left it: it is
# a complete, unambiguous statement of what the URL is. The axis is the one the
# taxonomy learned on 2026-08-01 — **permanence, not ownership**. Nobody is at
# fault here; the origin served a file correctly and we behaved correctly.
#
# Matched on the Playwright phrase alone, not on the surrounding wrapper, because
# the wrapper differs: the fixture reproduction arrives as "Unexpected error in
# _crawl_web … Failed on navigating ACS-GOTO: Page.goto: Download is starting"
# and production's proxied path as "All proxies failed: Failed on navigating
# ACS-GOTO: Page.goto: Download is starting". Both are failed *results*, not
# escaped exceptions — see the note in `classify_exception`.
#
# The header is NOT the trigger — that was the first guess and it was wrong.
# `Content-Disposition: attachment`, an inline `text/vcard` and an
# `application/octet-stream` all produce the byte-identical failure, measured
# through the browser against `fixture_origin` `/download/{kind}` on 2026-08-02.
# The rule is "Chromium will not render this inline", so this class is a shape of
# MAS's corpus (contact and people pages are where vCard exports and PDF
# brochures live) and not one odd URL.
#
# CORRECTION 2026-08-09: an inline `application/pdf` is the ONE exception, and
# this comment claimed the opposite for a week. The 2026-08-02 measurement ran
# on Playwright's bundled headless shell, which has no PDF viewer;
# `browser_manager.py:1123-1128` silently drops `channel="chromium"`, so the test
# arm and production's real Chrome are different binaries. Re-measured on both
# arms 2026-08-09: 4 of the 5 download kinds are identical, `pdf-inline` alone
# diverges — real Chrome RENDERS it into a 174-byte viewer shell at HTTP 200,
# which never reaches this function at all. It is classified by the tier-3
# structural inference as a block, i.e. `render_error` at 500. Consequence:
# `unrenderable_content` has fired ZERO times in production since it shipped
# (30-day query 2026-08-09; the 16 `Download is starting` lines in the archive
# are all from 2026-08-01, the day before the class existed). The class is
# correct for the four kinds it does cover; it simply does not cover PDFs.
# Anchored to Playwright's own `Page.goto:` prefix, which is present in all three
# wrappers and in the verbatim production line, and which costs nothing. The one
# way page text could ever reach this function is upstream's `Code context:`
# splice, which pastes OUR OWN source lines into `error_message` — so a comment
# or a test fixture containing the bare phrase is a real, if remote, channel.
# Nothing else can: antibot reasons are fixed labels plus byte counts, and every
# block branch returns before reaching here.
_DOWNLOAD_RE = re.compile(r"Page\.goto:\s*Download is starting", re.IGNORECASE)

# Playwright's own per-operation timeouts, and our fence. Both are ours: we ran
# out of time, which is a thing MAS should retry.
_TIMEOUT_RE = re.compile(
    r"Timeout\s+\d+(?:\.\d+)?\s*ms exceeded"
    r"|exceeded the time limit"
    r"|wall[- ]clock"
    r"|TimeoutError",
    re.IGNORECASE,
)

# A capture that has no <body> element at all.
#
# Chromium synthesises <body> for every HTML document it parses — there is no
# markup, however malformed, that renders without one. So a non-empty capture
# with no <body> means a script *removed* it after parse, and the only script
# on that page we control is our own consent/overlay cleanup. That is
# permanent: the same markup produces the same deletion on every attempt.
_BODY_TAG_RE = re.compile(r"<body\b", re.IGNORECASE)


def _document_root_is_gone(result: dict) -> bool:
    """True when the capture we are holding has lost its document root.

    Two production signatures, and they are the same fact at different depths:

        <!DOCTYPE html>                     15 bytes — <html> itself removed,
                                            after which Playwright's `content()`
                                            serializes the doctype and nothing
                                            else
        <!DOCTYPE html><html><head>…</head> head only — <body> removed; 87 bytes
        </html>                             bare, 20,087 with a padded <head>

    Both come back with no ``<body>``, which is the test. **The byte count is
    not the test**, though 15 is diagnostic on its own: an empty 200 serializes
    to 39 bytes (``<html><head></head><body></body></html>``) and a body that
    literally *is* the string ``<!DOCTYPE html>`` to 54, so nothing but a
    removed ``documentElement`` produces exactly 15.

    An empty or absent ``html`` field is deliberately NOT root-gone. A crawl
    that never obtained a document is a different failure, and it is the one
    that genuinely might work on a retry.
    """
    html = result.get("html")
    if not isinstance(html, str) or not html.strip():
        return False
    return not _BODY_TAG_RE.search(html)


def classify_error_text(
    error_message: Optional[str],
    status: Optional[int] = None,
) -> Optional[str]:
    """Verdict from crawler/browser error text, or None if it says nothing.

    ``status`` is the origin's *effective* (final-hop) status when known; it is
    only consulted to break ties, never to override an explicit signal.
    """
    text = (error_message or "").strip()
    if not text:
        return None

    _says_blocked = bool(_BLOCKED_RE.search(text))
    _inferred = _says_blocked and bool(_INFERRED_BLOCK_RE.search(text))

    if _says_blocked and not _inferred:
        # The block detector judges the *body*, and a 5xx body with nothing in
        # it trips its structural check — so an origin's own broken 500 came
        # back labelled "blocked". Both verdicts are origin-caused and both map
        # to HTTP 200, but they are not the same fact: `origin_blocked` is what
        # a residential-egress retry would target, and a site returning 500 is
        # simply broken. 503 stays a block: Incapsula and Varnish really do
        # serve blocks with it.
        if status and status >= 500 and status != 503:
            return ORIGIN_HTTP_ERROR
        return ORIGIN_BLOCKED

    if _inferred:
        # Discarding the *reason* must not discard the *status*. The reason is
        # ours — we observed an empty-looking page — but the origin may have
        # said something anyway, and 403/503 are block statuses in their own
        # right (`is_blocked`'s own status branch treats them that way, and
        # Incapsula and Varnish really do serve blocks with 503). Judge on what
        # is left rather than on what we just threw away:
        #
        #   403 / 503        the origin refused          -> ORIGIN_BLOCKED
        #   any other 4xx/5xx  the origin errored        -> ORIGIN_HTTP_ERROR
        #                      (`snuup.fi`'s ordinary 404 lands here)
        #   no origin status   nothing but our own shape -> None, and
        #                      `classify_result` calls it RENDER_ERROR
        #                      (`norex.com`, `jarvenkylamaatila.fi`)
        if status in (403, 503):
            return ORIGIN_BLOCKED
        if status and status >= 400:
            return ORIGIN_HTTP_ERROR
        return None

    if _DOWNLOAD_RE.search(text):
        # Checked before the `net::` table on purpose: Chromium also reports
        # ERR_ABORTED for some download navigations, and "we aborted because it
        # was a download" is a far more useful verdict than an unclassified
        # net:: code blamed on us.
        return UNRENDERABLE_CONTENT

    net = _NET_ERR_RE.search(text)
    if net:
        code = net.group(1)
        if code in _NET_ORIGIN_HTTP_ERRORS:
            return ORIGIN_HTTP_ERROR
        if code in _NET_ORIGIN_UNREACHABLE_ERRORS or code.startswith(
            _NET_ORIGIN_UNREACHABLE_PREFIXES
        ):
            return ORIGIN_UNREACHABLE
        # A net:: error we have not seen. Blame ourselves (loud, retryable)
        # rather than silently condemning a host, and leave a breadcrumb so the
        # table can grow from evidence.
        logger.info("[failure-class] unclassified net error, treated as ours: %s", code)
        return RENDER_ERROR

    if _TIMEOUT_RE.search(text):
        return RENDER_TIMEOUT

    # An origin status we already hold is better evidence than unparsed prose.
    if status and status >= 400:
        return ORIGIN_HTTP_ERROR

    return None


def classify_exception(exc: BaseException) -> str:
    """Verdict for an exception that escaped the crawl instead of producing a
    result — pool acquisition, browser launch, serialization.

    **CORRECTED 2026-08-02, because this docstring was wrong and two task files
    inherited it.** It used to say "this is the ACS-GOTO path: upstream re-raises
    a navigation failure when there is a single proxy and ``max_retries <= 1``".
    Measured: ``arun`` wraps its entire body in ``try:``
    (``async_webcrawler.py:256``) and returns a failed ``CrawlResult`` at
    ``:742`` instead of re-raising, so **the whole ACS-GOTO family reaches
    ``classify_result``, not this function** — including the
    ``net::ERR_HTTP_RESPONSE_CODE_FAILURE`` case this docstring was written for.

    The verdict is identical either way (both funnel through
    ``classify_error_text``, which is why the mistake was invisible for weeks),
    so the pattern table remains the single place to add a signal. What is *not*
    identical is the status mapping: ``api.py``'s exception handler decides
    200-vs-500 for this function's output, while ``server._crawl_response``
    decides it for ``classify_result``'s. If you are reasoning about which status
    a class produces, establish which of the two paths the failure actually takes
    before anything else.
    See ``tasks/done/download-navigation-is-not-a-render-error.md``.
    """
    import asyncio

    if isinstance(exc, asyncio.TimeoutError):
        return RENDER_TIMEOUT
    if isinstance(exc, OriginUnresolvable):
        return ORIGIN_UNREACHABLE
    return classify_error_text(str(exc)) or RENDER_ERROR


def classify_result(result: dict) -> str:
    """Verdict for one result dict from ``handle_crawl_request``.

    Successes are ``"none"`` rather than absent — MAS asked for a field that
    never needs interpretation.
    """
    if result.get("success"):
        return NONE

    status = effective_status_of(result)
    verdict = classify_error_text(result.get("error_message"), status)
    if verdict:
        return verdict

    if status and status >= 400:
        return ORIGIN_HTTP_ERROR

    # A capture with no document root left. Ours, and PERMANENT — which is the
    # axis, not ownership. `render_error` at 500 buys MAS three more attempts at
    # a page that will lose its root identically every time: Kübler paid 32
    # navigations and 266 s of render time for two URLs in segment 1, 26% of the
    # entire run for one company of 25.
    #
    # This sits BELOW the origin branches on purpose. If the origin said 403 or
    # served a 500, that is evidence about the origin and it outranks a verdict
    # we derived from the shape of what came back — the same ordering
    # `classify_error_text`'s inference branch already uses. What reaches here is
    # a document that arrived fine and then lost its root, which since 2026-08-06
    # we know is usually *our own* consent cleanup deleting it
    # (tasks/done/consent-scripts-delete-the-page.md).
    #
    # `render_defect`'s name says "our parse lost the body" and the mechanism
    # here is our injected JS rather than our parser. The name is still right —
    # both are ours, both are permanent, and permanence is what the status keys
    # on — but the class is now wider than its original sentence, deliberately:
    # it keys on the SHAPE OF THE DAMAGE, which is what makes it survive the
    # next mechanism. This is the third distinct thing to produce a body-shaped
    # hole (the <noscript> family, the four markup shapes in
    # cleaned-html-collapse-guard.md, and now our own JS).
    if _document_root_is_gone(result):
        return RENDER_DEFECT

    # No error text, no origin status, a document that still has a root: we came
    # back with nothing and cannot say why. That is ours, and it is the case a
    # retry can genuinely clear — a JS shell that rendered nothing this time may
    # render next time. Keeping it apart from the branch above is what stops the
    # `norex.com` inversion re-opening from the other side.
    return RENDER_ERROR


def effective_status_of(result: dict) -> Optional[int]:
    """The status that actually produced the body we are holding.

    ``status_code`` carries the **first** hop of a redirect chain; the body
    always comes from the **last**, kept as ``redirected_status_code``. Judging
    the 301 is what let every redirect-to-block host through as a success
    (forensics §2b).
    """
    return result.get("redirected_status_code") or result.get("status_code")


def http_status_for(failure_classes: Iterable[Optional[str]]) -> int:
    """Request-level HTTP status for a crawl whose results all failed.

    200 when retrying cannot help — the origin owns it, or we do but permanently.
    MAS's retry policy then treats it as terminal, which is correct. 5xx stays
    reserved for failures another attempt might actually clear.

    **This is the single place the mapping happens, and both render modes go
    through it.** They did not always: static mode returned its results inside an
    unconditional 200 while full mode ran the same classes through here, so
    `render_error` meant "retry me 3x" or "give up" depending on which
    `render_mode` the client happened to ask for — same class, opposite
    behaviour, documented nowhere. MAS found it (their message 09). Do not
    reintroduce a second mapping site; add to the vocabulary instead.
    """
    classes = [c for c in failure_classes if c and c != NONE]
    if not classes:
        return 200
    if all(c in NON_RETRYABLE_CLASSES for c in classes):
        return 200
    if any(c == RENDER_TIMEOUT for c in classes):
        return 504
    return 500


def failed_result(
    url: str,
    failure_class: str,
    error_message: str,
    *,
    status_code: int = 0,
    render_mode: str = "full",
) -> dict:
    """A result dict for a failure that produced no ``CrawlResult`` at all.

    Deliberately the same shape as ``aitosoft_static_mode._static_error_result``
    so MAS parses full-mode and static-mode failures with one code path.
    ``status_code: 0`` means "no HTTP status was obtained" — Chromium's
    ``ERR_HTTP_RESPONSE_CODE_FAILURE`` does not carry the origin's code, so we
    can say the origin errored but not with what.
    """
    return {
        "url": url,
        "success": False,
        "status_code": status_code,
        "redirected_status_code": None,
        "error_message": error_message,
        "failure_class": failure_class,
        "render_mode": render_mode,
        "markdown": {"raw_markdown": "", "fit_markdown": ""},
        "links": {"internal": [], "external": []},
    }


#: Envelope-level `failure_class` for statuses raised without a result.
_STATUS_TO_ENVELOPE_CLASS = {
    400: BAD_REQUEST,
    401: AUTH,
    403: AUTH,
    429: CAPACITY,
    500: RENDER_ERROR,
    503: CAPACITY,
    504: RENDER_TIMEOUT,
}


def envelope_class_for_status(status_code: int) -> Optional[str]:
    """`failure_class` for an error envelope that carries no result, or None
    when the status is not part of the taxonomy (404, 405, …)."""
    return _STATUS_TO_ENVELOPE_CLASS.get(status_code)
