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
RENDER_DEFECT = "render_defect"  # our parse lost the body — ours and PERMANENT

# Normally envelope-level (no result exists to carry them).
CAPACITY = "capacity"  # render gate rejected -> 429
AUTH = "auth"  # 401/403 from us, not the origin
BAD_REQUEST = "bad_request"  # malformed request -> 400
# ...except BAD_REQUEST, which static mode also attaches to a *result* when a
# redirect hop is refused by the egress broker. That result must never be
# retried, so it has to be in NON_RETRYABLE_CLASSES below — routing static mode
# through `http_status_for` without it turns an SSRF refusal into a 500 and buys
# MAS three more attempts at a URL our own policy has already declined.

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
NON_RETRYABLE_CLASSES = ORIGIN_CLASSES | {RENDER_DEFECT, BAD_REQUEST}

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

# Playwright's own per-operation timeouts, and our fence. Both are ours: we ran
# out of time, which is a thing MAS should retry.
_TIMEOUT_RE = re.compile(
    r"Timeout\s+\d+(?:\.\d+)?\s*ms exceeded"
    r"|exceeded the time limit"
    r"|wall[- ]clock"
    r"|TimeoutError",
    re.IGNORECASE,
)


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

    if _BLOCKED_RE.search(text):
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
    result. This is the ACS-GOTO path: upstream re-raises a navigation failure
    when there is a single proxy and ``max_retries <= 1``, so the origin's own
    5xx arrives here rather than as a failed result."""
    import asyncio

    if isinstance(exc, asyncio.TimeoutError):
        return RENDER_TIMEOUT
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

    # No error text, no origin status: we came back with nothing and cannot say
    # why. That is ours until proven otherwise.
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
