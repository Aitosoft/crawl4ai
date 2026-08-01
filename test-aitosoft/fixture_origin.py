"""
A local fixture origin — one HTTP server that serves our failure classes, so a
new failure class costs a route argument instead of a customer's website.

Why this exists
---------------
Every failure class diagnosed since 2026-04 was diagnosed against a live SME
site: 8 hits on maitokolmio.fi for one config matrix, 4 on kiertopakkaus.fi for
one nested `<noscript>`, 3 on konecranes.com for one Varnish 403, and
talgraf.fi permanently Cloudflare-blocked by our own over-scraping. All of it
leaves from one Azure SNAT address that is not contractually ours and that MAS's
production fetches share — so our test hits and their 251-page re-scrape draw on
the same reputation budget, and "this host blocks datacentre IPs" is
indistinguishable from "this host blocked us because of what we did".

Our 130 offline tests cover **pure functions** (`strip_noscript`, `is_blocked`,
`classify_result`) fed synthetic strings. What had no offline instrument at all
was anything involving **time, navigation or the browser** — challenge
resolution, hydration races, `page.content()` against a navigating frame,
redirect chains ending in a block. Those are exactly the classes that cost live
traffic. This module is that instrument. See tasks/done/fixture-origin.md.

Two properties are the point
----------------------------
1. **The real production path.** `ProductionPath.crawl()` goes through
   `aitosoft_entry` (config.yml BrowserConfig defaults + the trusted-client
   boundary relaxations) into `api.handle_crawl_request` and out to a real pool
   browser, so `failure_class`, `render_mode`, the redirect-hop `status_code`
   rewrite, the patchright retry, the render-admission gate and the wall-clock
   fence are all genuinely exercised. A fixture that called `is_blocked` on a
   string would add nothing to what test_antibot_challenge_detection.py already
   does.
2. **Parameterised, not hard-coded.** Delay, body size, visible-text length,
   status code and markup shape are arguments. The next failure class should be
   a new query parameter or one short route — never a new website.

The idiom is upstream's (`tests/async/test_redirect_url_resolution.py`: an
`HTTPServer` on a thread driven by `AsyncWebCrawler`), adopted rather than
reinvented.

The egress seam
---------------
`egress_broker` exists to refuse internal targets and is NOT weakened here. The
loopback allowance is the operator escape hatch that already exists
(`CRAWL4AI_ALLOW_INTERNAL_URLS`), applied as a narrowly-scoped context manager
around each crawl instead of as a process-wide environment variable — so the
default configuration of this process stays production's, and every other suite
in the same pytest session still sees a broker that refuses loopback.
test_fixture_origin.py asserts exactly that, in the same suite.

Routes (every default is a module constant; every one is overridable):

    /ok                                   healthy control page
    /challenge/resolve-after/{s}          interstitial -> content by DOM rewrite
    /challenge/resolve-by-nav/{s}         interstitial -> content by navigation
    /challenge/never                      interstitial, forever
    /block/padded-403                     big body, ~36 chars visible, status 202
    /block/varnish-403                    ~400 B Fastly/Varnish body at 403
    /hydrate-after/{s}                    near-empty body that paints after N s
    /redirect-to/{route}                  301 into any route above
    /collapse/{shape}                     large body carrying one swallowing shape

    ?stall=<s>        server sleeps before responding (wall-clock fence)
    ?status=<n>       override the status code of any route
    ?marker=<name>    which challenge family the interstitial belongs to
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Iterator, List, Optional, Pattern, Tuple
from urllib.parse import parse_qs, urlsplit

import pytest

_DOCKER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
)
if _DOCKER_DIR not in sys.path:
    sys.path.insert(0, _DOCKER_DIR)


# ── page material ────────────────────────────────────────────────────────
# One body of real content, reused by every route that is supposed to end in a
# successful capture, so "did we get the page" is the same assertion everywhere.
# Finnish SME shape (heading + contacts) because that is the corpus MAS crawls.
#
# SIZE IS LOAD-BEARING, and it was wrong until 2026-08-01. This page rendered to
# ~140 markdown characters — *below* MAS's `DEGENERATE_CAPTURE_CHARS = 500`, so
# the control every route uses for "this capture succeeded" was already
# degenerate by the customer's own floor. Harmless while the only question was
# "interstitial or content?"; fatal for tasks/cleaned-html-collapse-guard.md,
# whose entire output is a threshold measured against this page.
#
# It now renders to ~1500 markdown characters over ~1200 characters of visible
# text — comfortably above 500 on both sides of the unit boundary, so a healthy
# control is unambiguously healthy no matter which side you measure from.
# Keep it that way: `test_fixture_origin.py::test_the_healthy_control_is_not_
# degenerate` fails if anyone trims this back.

CONTENT_HTML = (
    "<h1>Yritys Oy</h1>"
    "<p>Puhelin 010 123 4567, sahkoposti info@yritys.fi</p>"
    "<p>Osoite: Esimerkkikatu 1, 00100 Helsinki.</p>"
    "<h2>Yritys</h2>"
    "<p>Yritys Oy on vuonna 1998 perustettu suomalainen perheyritys, joka "
    "toimittaa teollisuuden kunnossapitopalveluita ja projektitoimituksia "
    "koko Suomen alueella. Palveluksessamme on 42 alan ammattilaista, ja "
    "toimipisteemme sijaitsevat Helsingissa, Tampereella ja Oulussa.</p>"
    "<p>Toimintaamme ohjaavat sertifioidut laatu- ja "
    "ymparistojarjestelmat seka pitka kokemus vaativista kohteista. "
    "Liikevaihtomme oli viime tilikaudella 8,4 miljoonaa euroa.</p>"
    "<h2>Palvelut</h2>"
    "<ul>"
    "<li>Ennakoiva kunnossapito ja kuntokartoitukset</li>"
    "<li>Sahko- ja automaatioasennukset</li>"
    "<li>Putkistojen ja sailioiden korjaustyot</li>"
    "<li>Projektinjohto ja valvonta</li>"
    "<li>Varaosapalvelu ja logistiikka</li>"
    "</ul>"
    "<h2>Yhteystiedot</h2>"
    "<p>Myynti: myynti@yritys.fi, puhelin 010 123 4500. "
    "Laskutus: laskutus@yritys.fi. Paivystys arkisin klo 7-21.</p>"
    "<table>"
    "<tr><td>Matti Meikalainen</td><td>toimitusjohtaja</td>"
    "<td>040 123 4501</td></tr>"
    "<tr><td>Liisa Virtanen</td><td>myyntijohtaja</td>"
    "<td>040 123 4502</td></tr>"
    "<tr><td>Pekka Nieminen</td><td>huoltopaallikko</td>"
    "<td>040 123 4503</td></tr>"
    "</table>"
    "<h2>Referenssit</h2>"
    "<p>Olemme toteuttaneet kunnossapitosopimuksia metsateollisuudelle, "
    "elintarviketeollisuudelle ja kunnallisille vesilaitoksille. "
    "Pyydä referenssiluettelo osoitteesta info@yritys.fi.</p>"
)

#: Present in the markdown of every successful capture.
CONTENT_MARKER = "info@yritys.fi"

#: Text that sits at the very END of CONTENT_HTML. A collapse that eats the tail
#: but leaves the heading looks like a success if you only assert the marker.
CONTENT_TAIL_MARKER = "vesilaitoksille"

PAGE = (
    "<!DOCTYPE html><html><head><title>Yritys Oy</title></head>"
    "<body>{body}</body></html>"
)

# Challenge families, keyed by `?marker=`, as (title, body markup). The title is
# part of the family because two of the detector's three challenge patterns key
# on it — an interstitial whose <title> still says "Just a moment" is not an
# unmarked one, which is a mistake this table made until it was measured.
#
#   robot-suspicion  tier 1, the family MAS measured on 371 of 402 stored
#                    challenge pages (2026-07-30) — the default
#   checking-browser challenge tier, interstitial prose at any status
#   none             nothing the detector keys on: the silent interstitial,
#                    for measuring capture timing independently of detection
CHALLENGE_MARKERS: Dict[str, Tuple[str, str]] = {
    "robot-suspicion": (
        "Just a moment...",
        "<h1>One more step</h1><p>Please wait while we verify your browser.</p>"
        '<script src="/assets/robot-suspicion.js"></script>',
    ),
    "checking-browser": (
        "Just a moment...",
        "<h1>Checking your browser before accessing the site</h1>"
        "<p>This process is automatic. Your browser will redirect shortly.</p>",
    ),
    "none": (
        "Yritys Oy",
        "<h1>Odota hetki</h1><p>Sivua valmistellaan, ole hyva ja odota.</p>",
    ),
}

DEFAULT_CHALLENGE_MARKER = "robot-suspicion"

#: The challenge layer serves the interstitial AND the real page under this
#: code — the 2026-07-31 finding that gates tasks/challenge-interstitial-resolve.md.
#: Both `/challenge/*` and `/block/padded-403` default to it for that reason.
CHALLENGE_STATUS = 202

#: Fastly/Varnish error body, the konecranes.com shape (~400 B at 403).
VARNISH_403 = (
    "<!DOCTYPE html><html><head><title>403 Forbidden</title></head><body>"
    "<h1>Error 403 Forbidden</h1><p>Forbidden</p>"
    "<h3>Guru Meditation:</h3><p>XID: 1234567890</p>"
    "<hr><p>Varnish cache server</p></body></html>"
)

#: `/block/padded-403` defaults: a body far past every `len(html)` size gate in
#: antibot_detector (tier 2 at 10 KB, tier 3 at 50 KB) carrying a block notice
#: no longer than a real one. This is the shape behind
#: tasks/detector-round3-evidence-vs-inference.md defect A.
#:
#: **The default shape was wrong until 2026-08-01, on the axis that decides the
#: fix.** It served the notice in a bare `<div>`, which gives the page **zero**
#: content elements — so tier 3's `no_content_elements` signal fired and the
#: page needed only the size gate to move. The page MAS actually measured
#: renders to `# 403 - Forbidden` + `Access to this page is forbidden.`, i.e. an
#: `<h1>` and a `<p>`: **two** content elements, one structural signal, and
#: therefore still undetected after a size-gate change. A fix validated against
#: the old fixture would have looked complete and closed none of the four hosts.
#:
#: Both shapes are kept, because both are real and they exercise the two
#: discriminators of the block-notice tier (heading placement vs. the notice
#: being the whole page). `?shape=heading` (default) | `?shape=bare`.
PADDED_BLOCK_BYTES = 80_000
PADDED_BLOCK_HEADING = "403 - Forbidden"
PADDED_BLOCK_TEXT = "Access to this page is forbidden."

#: The bare-`<div>` variant: no heading, so only "the notice is the whole page"
#: can catch it. Vendors do serve this shape.
PADDED_BLOCK_BARE_TEXT = "Access to this page has been denied."

#: Markup shapes that can make the document swallow its own body. Each is
#: injected ahead of CONTENT_HTML by `/collapse/{shape}`, so "did the page
#: survive this shape" is one assertion for the whole family.
#:
#: The `<noscript>` members come from
#: tasks/done/noscript-collapses-body-to-empty-markdown.md — `nested-noscript`
#: is the shape that ran 3.5 months across 406 pages at success:true. The rest
#: is the enumeration tasks/cleaned-html-collapse-guard.md asks for: every
#: element that cannot nest or is raw-text/RCDATA and therefore swallows the
#: document when left unclosed, the malformed-comment family, libxml2's
#: nesting-depth limit, foreign content, and the structural strays.
#:
#: Enumerate through the BROWSER, not only through libxml2. A shape that is
#: harmless to libxml2 can be fatal after Chromium re-serializes it — that
#: difference is exactly what hid `unclosed-noscript` behind a green
#: test_noscript_body_collapse.py for a month.
_GTM = '<iframe src="about:blank"></iframe>'
COLLAPSE_SHAPES: Dict[str, str] = {
    # -- the <noscript> family --
    "nested-noscript": f"<noscript>{_GTM}<noscript>{_GTM}</noscript>",
    "single-noscript": f"<noscript>{_GTM}</noscript>",
    "unclosed-noscript": f"<noscript>{_GTM}",
    "uppercase-noscript": f"<NOSCRIPT>{_GTM}<NOSCRIPT>{_GTM}</NOSCRIPT>",
    # -- unclosed raw-text / RCDATA elements: same mechanism, other elements --
    "unclosed-title": "<title>Yritys Oy",
    "unclosed-textarea": "<textarea>Kirjoita palautteesi",
    "unclosed-style": "<style>.banner{color:red}",
    "unclosed-script": "<script>var analytics=1;",
    "unclosed-iframe": '<iframe src="about:blank">',
    "unclosed-xmp": "<xmp>esimerkkikoodi",
    "plaintext": "<plaintext>",
    # -- malformed comments --
    "abrupt-comment": "<!-->",
    "unterminated-comment": "<!-- evaste-ilmoitus",
    "dashes-in-comment": "<!-- a -- b -->",
    # -- structural strays --
    "stray-close-html": "</html>",
    "second-body": "<body>",
    "deep-nesting": "<div>" * 512,  # past libxml2's default depth limit
    # -- foreign content --
    "svg-style": "<svg><style>.a{fill:red}</style></svg>",
    "svg-unclosed-foreignobject": "<svg><foreignObject>",
    "mathml-annotation": "<math><annotation-xml encoding='text/html'><div>",
    # -- the control --
    "none": "",
}

#: **Measured 2026-08-01**, every shape above run through `ProductionPath.crawl`
#: at `?bytes=73000` (apteam.fi's size), twice each. These four lose the whole
#: body; the other seventeen come back intact. All four are **deterministic** —
#: byte-identical `html` and `cleaned_html` across two visits — which is the
#: property that told MAS `apteam.fi` and `flvi.fi` were ours and not a timing
#: artefact.
#:
#: This refutes the inference the task file carried until today ("the root cause
#: is probably already found", from `unclosed-noscript` alone). There are three
#: distinct mechanisms here, not one:
#:
#:   unclosed-noscript     Chromium re-serializes the rest of the document
#:   unclosed-script       *inside* the unclosed raw-text element; the
#:                         pre-parse repair then removes element and page alike.
#:   deep-nesting          libxml2's nesting-depth limit — nothing to do with
#:                         raw text at all.
#:   unterminated-comment  `cleaned_html` survives INTACT (74,523 bytes,
#:                         contact details present) and markdown is still empty,
#:                         because the content sits inside the comment.
#:
#: That last one is why the guard measures markdown and not `cleaned_html`: the
#: ratio the task file originally proposed cannot see it at all.
BODY_SWALLOWING_SHAPES = frozenset(
    {
        "unclosed-noscript",
        "unclosed-script",
        "unterminated-comment",
        "deep-nesting",
    }
)

#: Of those, the one the collapse guard cannot see, and this is by design.
#: `unclosed-script` puts the whole document inside a `<script>` element, and
#: the guard's visible-text measure strips script blocks — it must, because real
#: pages carry hundreds of KB of inline JS and counting it would wreck the
#: ratio. So the browser hands us a document with zero visible text, which is
#: indistinguishable from a legitimately empty page. This shape belongs to the
#: pre-parse repair, not to the guard. Pinned rather than forgotten.
GUARD_BLIND_SHAPES = frozenset({"unclosed-script"})


def _padding(nbytes: int) -> str:
    """Filler that adds bytes but neither visible text nor content elements —
    the way a real vendor page pads, with inline CSS. `_visible_text()` strips
    <style> blocks, so this grows `len(html)` without growing what a human sees,
    which is the exact discrepancy the padded-block route exists to expose."""
    if nbytes <= 0:
        return ""
    return "<style>/* %s */</style>" % ("padding " * (nbytes // 8))


# ── the server ───────────────────────────────────────────────────────────


@dataclass
class Reply:
    status: int
    body: str = ""
    content_type: str = "text/html; charset=utf-8"
    headers: Dict[str, str] = field(default_factory=dict)


Handler = Callable[[re.Match, Dict[str, List[str]]], Reply]

_ROUTES: List[Tuple[Pattern[str], Handler]] = []


def _route(pattern: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _ROUTES.append((re.compile(pattern + r"\Z"), fn))
        return fn

    return register


def _one(query: Dict[str, List[str]], key: str, default: Any) -> Any:
    return query.get(key, [default])[0]


def _interstitial(marker: str, resolve_js: str) -> str:
    """An interstitial that runs `resolve_js` on a timer. Everything the
    detector could key on lives in the title and the body, both of which the
    resolution replaces — exactly as a real challenge layer's does."""
    title, markup = CHALLENGE_MARKERS.get(
        marker, CHALLENGE_MARKERS[DEFAULT_CHALLENGE_MARKER]
    )
    return (
        f"<!DOCTYPE html><html><head><title>{title}</title></head><body>"
        f'<div id="challenge">{markup}</div>'
        f"<script>{resolve_js}</script>"
        "</body></html>"
    )


@_route(r"/ok")
def _ok(_m, query):
    return Reply(200, PAGE.format(body=CONTENT_HTML))


@_route(r"/assets/robot-suspicion\.js")
def _challenge_asset(_m, query):
    # The interstitial references this; serving it keeps the request log
    # readable (a 404 here would look like a fixture bug in a hit census).
    return Reply(200, "/* challenge */", "application/javascript")


@_route(r"/challenge/resolve-after/([0-9.]+)")
def _challenge_resolve_after(m, query):
    """Interstitial that becomes the real page by rewriting the DOM in place —
    no navigation, so `page.content()` sees one document throughout."""
    ms = int(float(m.group(1)) * 1000)
    marker = _one(query, "marker", DEFAULT_CHALLENGE_MARKER)
    js = (
        "setTimeout(function(){"
        "document.title=%s;document.body.innerHTML=%s;},%d);"
        % (json.dumps("Yritys Oy"), json.dumps(CONTENT_HTML), ms)
    )
    return Reply(CHALLENGE_STATUS, _interstitial(marker, js))


@_route(r"/challenge/resolve-by-nav/([0-9.]+)")
def _challenge_resolve_by_nav(m, query):
    """Interstitial that top-level-navigates to the real page. This is the
    `page.content()` race from waa-eval-2026-07-30-forensics.md §1: capture can
    land while the frame's execution context is being replaced."""
    ms = int(float(m.group(1)) * 1000)
    marker = _one(query, "marker", DEFAULT_CHALLENGE_MARKER)
    target = _one(query, "to", "/ok")
    js = "setTimeout(function(){location.replace(%s);},%d);" % (
        json.dumps(target),
        ms,
    )
    return Reply(CHALLENGE_STATUS, _interstitial(marker, js))


@_route(r"/challenge/never")
def _challenge_never(_m, query):
    """The control: an interstitial that never resolves, so a capture-timing
    change cannot be mistaken for a block that was never going to lift."""
    marker = _one(query, "marker", DEFAULT_CHALLENGE_MARKER)
    return Reply(CHALLENGE_STATUS, _interstitial(marker, ""))


@_route(r"/block/padded-403")
def _block_padded(_m, query):
    """A block page padded past every `len(html)` gate in the detector.

    Defaults to HTTP 202 — the status the challenge layer actually uses — so
    none of the status branches fire either. This came back
    `success: true, failure_class: none` until the block-notice tier shipped
    (tasks/detector-round3-evidence-vs-inference.md, 2026-08-01).

    `?shape=heading` (default) reproduces the four hosts MAS measured: the
    notice in an `<h1>` with a `<p>` under it. `?shape=bare` puts the same text
    in a `<div>`, which has no heading for the detector to key on and can only
    be caught by the notice covering the whole page. `?text=` overrides the
    sentence in either shape; `?bytes=` the padding; `?status=` the code.
    """
    nbytes = int(_one(query, "bytes", PADDED_BLOCK_BYTES))
    shape = _one(query, "shape", "heading")
    if shape == "bare":
        body = f"<div>{_one(query, 'text', PADDED_BLOCK_BARE_TEXT)}</div>"
    else:
        heading = _one(query, "heading", PADDED_BLOCK_HEADING)
        body = f"<h1>{heading}</h1><p>{_one(query, 'text', PADDED_BLOCK_TEXT)}</p>"
    return Reply(
        CHALLENGE_STATUS,
        "<!DOCTYPE html><html><head><title>Attention Required</title>"
        f"{_padding(nbytes)}</head><body>{body}</body></html>",
    )


@_route(r"/block/varnish-403")
def _block_varnish(_m, query):
    """Small edge-served error body at 403 — the cheap, unambiguous block, and
    the cost unit for tasks/blocked-host-retry-economy.md."""
    return Reply(403, VARNISH_403)


@_route(r"/hydrate-after/([0-9.]+)")
def _hydrate_after(m, query):
    """Near-empty shell that paints content on a timer — MAS's revisol.fi class.
    Captured too early it is a degenerate capture, not a block, and the two must
    stay distinguishable."""
    ms = int(float(m.group(1)) * 1000)
    js = "setTimeout(function(){document.getElementById('root').innerHTML=%s;},%d);" % (
        json.dumps(CONTENT_HTML),
        ms,
    )
    return Reply(
        200,
        "<!DOCTYPE html><html><head><title>Yritys Oy</title></head><body>"
        f'<div id="root"></div><script>{js}</script></body></html>',
    )


@_route(r"/redirect-to(/.*)")
def _redirect_to(m, query):
    """301 into any other route. Pins the `effective_status` fix: the body comes
    from the last hop, so that is what `status_code` and block detection must
    judge (the 301-judged-instead bug, 2026-07-30)."""
    status = int(_one(query, "redirect_status", 301))
    location = m.group(1)
    passthrough = "&".join(
        f"{k}={v[0]}" for k, v in query.items() if k != "redirect_status"
    )
    if passthrough:
        location += "?" + passthrough
    return Reply(status, "", headers={"Location": location})


@_route(r"/collapse/([a-z-]+)")
def _collapse(m, query):
    """A large page carrying one markup shape from the swallowing family, with
    real content after it. If the shape swallows the body, the capture comes
    back at HTTP 200 / success:true with ~nothing in it — the silent whole-body
    loss that ran 3.5 months. See tasks/cleaned-html-collapse-guard.md."""
    shape = COLLAPSE_SHAPES.get(m.group(1), "")
    nbytes = int(_one(query, "bytes", 0))
    return Reply(
        200,
        PAGE.format(body=f"{shape}{_padding(nbytes)}{CONTENT_HTML}"),
    )


class _RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, so Chromium reuses the socket

    # Silence the default stderr access log; the origin records hits itself.
    def log_message(self, *_args):
        pass

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler's name)
        split = urlsplit(self.path)
        query = parse_qs(split.query)
        self.server.origin.record(split.path)  # type: ignore[attr-defined]

        stall = float(_one(query, "stall", 0))
        if stall:
            time.sleep(stall)

        for pattern, handler in _ROUTES:
            match = pattern.match(split.path)
            if match:
                reply = handler(match, query)
                break
        else:
            reply = Reply(
                404, "<!DOCTYPE html><html><body><p>no such route</p>" "</body></html>"
            )

        # `?status=` overrides whatever the route chose, so any body shape can
        # be served under any code without a new route.
        reply.status = int(_one(query, "status", reply.status))
        self._send(reply)

    def _send(self, reply: Reply):
        raw = reply.body.encode("utf-8")
        self.send_response(reply.status)
        self.send_header("Content-Type", reply.content_type)
        self.send_header("Content-Length", str(len(raw)))
        for key, value in reply.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class FixtureOrigin:
    """A threaded HTTP origin on an ephemeral loopback port.

    Records every path served, so a test can assert what a failure class costs
    in page loads — the measurement tasks/blocked-host-retry-economy.md needs
    and has so far only been able to get from production logs.
    """

    def __init__(self, host: str = "127.0.0.1"):
        self._host = host
        self._server: Optional[_Server] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._hits: List[str] = []

    # -- lifecycle --
    def start(self) -> "FixtureOrigin":
        self._server = _Server((self._host, 0), _RequestHandler)
        self._server.origin = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="fixture-origin", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "FixtureOrigin":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    # -- addressing --
    @property
    def port(self) -> int:
        assert self._server is not None, "origin not started"
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self.port}"

    def url(self, route: str, **params: Any) -> str:
        """`origin.url("/challenge/resolve-after/1", marker="none", status=200)`."""
        url = self.base_url + route
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        return url

    # -- request log --
    def record(self, path: str) -> None:
        with self._lock:
            self._hits.append(path)

    @property
    def hits(self) -> List[str]:
        with self._lock:
            return list(self._hits)

    def hits_for(self, prefix: str) -> int:
        return sum(1 for p in self.hits if p.startswith(prefix))

    def reset_hits(self) -> None:
        with self._lock:
            self._hits.clear()


# ── the egress seam ──────────────────────────────────────────────────────


@contextlib.contextmanager
def loopback_allowed():
    """Permit loopback targets for the duration of the block, and only that.

    This flips the two module flags that `CRAWL4AI_ALLOW_INTERNAL_URLS` sets at
    import — `utils.ALLOW_INTERNAL_URLS` (the crawl seed check) and
    `egress_broker.ALLOW_INTERNAL` (resolve-and-pin, used by static mode's
    per-hop redirect validation and by the pinning proxy). It does NOT set the
    environment variable, so nothing outside this block — including other suites
    sharing the pytest process — sees anything but the production configuration.

    Deliberately not a weakening of egress_broker: the rule, the pinning and the
    opaque error are all untouched. test_fixture_origin.py asserts that the
    production configuration still refuses the fixture's own URL.
    """
    import egress_broker
    import utils

    previous = (utils.ALLOW_INTERNAL_URLS, egress_broker.ALLOW_INTERNAL)
    utils.ALLOW_INTERNAL_URLS = True
    egress_broker.ALLOW_INTERNAL = True
    try:
        yield
    finally:
        utils.ALLOW_INTERNAL_URLS, egress_broker.ALLOW_INTERNAL = previous


# ── the production path ──────────────────────────────────────────────────

#: MAS's `optimal` config (TESTING.md), with the page timeout shortened because
#: nothing on loopback is slow. `delay_before_return_html` is the capture wait —
#: the parameter tasks/challenge-interstitial-resolve.md is about — and MAS
#: sends 2.0 in production.
DEFAULT_CRAWLER_CONFIG: Dict[str, Any] = {
    "wait_until": "domcontentloaded",
    "scan_full_page": False,
    "remove_overlay_elements": False,
    "remove_consent_popups": True,
    "page_timeout": 15000,
    "delay_before_return_html": 2.0,
    "cache_mode": "bypass",
}

#: Shrunk from config.yml's 180 s / 100 s so a fence test costs seconds. Both
#: are `config` arguments to `handle_crawl_request`, i.e. real knobs, not a
#: test-only code path.
DEFAULT_WALL_CLOCK_S = 30
DEFAULT_TOTAL_TIMEOUT_MS = 20000


@dataclass
class Outcome:
    """What the client would have received, envelope and wire status both."""

    url: str
    http_status: int
    envelope: Optional[dict] = None
    detail: Any = None
    elapsed_s: float = 0.0

    @property
    def result(self) -> dict:
        """The single result (the MAS contract is one URL per request)."""
        assert self.envelope, f"no envelope: HTTP {self.http_status} {self.detail!r}"
        return self.envelope["results"][0]

    @property
    def success(self) -> bool:
        return bool(self.envelope) and bool(self.result.get("success"))

    @property
    def failure_class(self) -> Optional[str]:
        return self.result.get("failure_class") if self.envelope else None

    @property
    def status_code(self) -> Optional[int]:
        return self.result.get("status_code") if self.envelope else None

    @property
    def html(self) -> str:
        return self.result.get("html") or ""

    @property
    def markdown(self) -> str:
        md = self.result.get("markdown")
        if isinstance(md, dict):
            return md.get("raw_markdown") or ""
        return md or ""

    @property
    def error_message(self) -> str:
        return (self.result.get("error_message") or "") if self.envelope else ""


def _resolve_channel() -> Optional[str]:
    """Which Chrome the fixture crawls with.

    config.yml pins `chrome_channel: chrome` because the deployed amd64 image
    installs real Google Chrome; no such build exists for the arm64 devcontainer
    (TESTING.md), where launching that channel fails outright. Fall back to
    bundled Chromium there rather than making a developer edit config.yml —
    that edit has been committed by accident before. Override with
    CRAWL4AI_FIXTURE_CHANNEL.

    Returned as `"chromium"` rather than None because browser_manager passes
    `chrome_channel` straight to Playwright unless it is exactly that string.
    """
    override = os.environ.get("CRAWL4AI_FIXTURE_CHANNEL")
    if override:
        return override
    for binary in ("google-chrome", "google-chrome-stable", "chrome"):
        if shutil.which(binary):
            return "chrome"
    return "chromium"


class ProductionPath:
    """Drives `api.handle_crawl_request` the way the deployed server does.

    Importing `aitosoft_entry` is what makes this the production path and not an
    approximation: it applies config.yml's BrowserConfig defaults (stealth, UA,
    viewport) to every request and installs the trusted-client relaxations of
    the untrusted-config boundary, then imports upstream's `server`. Requests
    then run through the same admission gate, browser pool, patchright retry,
    `failure_class` tagging and wall-clock fence as production.

    One event loop is used for the whole session because the pooled browser is
    bound to the loop that created it.
    """

    def __init__(self):
        import asyncio

        os.environ.setdefault("CRAWL4AI_API_TOKEN", "fixture-origin-local")

        import aitosoft_entry  # noqa: F401  (side effects ARE the point)
        from crawl4ai import BrowserConfig

        self._browser_config_cls = BrowserConfig
        self._saved_defaults = BrowserConfig.get_defaults()
        channel = _resolve_channel()
        BrowserConfig.set_defaults(chrome_channel=channel, channel=channel)
        self.channel = channel

        self._loop = asyncio.new_event_loop()

    # -- config --
    def server_config(
        self,
        wall_clock_s: float = DEFAULT_WALL_CLOCK_S,
        total_timeout_ms: int = DEFAULT_TOTAL_TIMEOUT_MS,
    ) -> dict:
        """config.yml as the server loads it, with the two budgets shortened."""
        import copy

        from utils import load_config

        config = copy.deepcopy(load_config())
        config["limits"]["wall_clock_s"] = wall_clock_s
        config["crawler"]["base_config"]["total_timeout"] = total_timeout_ms
        return config

    # -- the call --
    def crawl(
        self,
        url: str,
        *,
        crawler_config: Optional[dict] = None,
        browser_config: Optional[dict] = None,
        render_mode: str = "full",
        wall_clock_s: float = DEFAULT_WALL_CLOCK_S,
        total_timeout_ms: int = DEFAULT_TOTAL_TIMEOUT_MS,
        **overrides: Any,
    ) -> Outcome:
        """One crawl, returned as the client would see it.

        `**overrides` are merged into the crawler config, so the common case
        reads `path.crawl(url, delay_before_return_html=0.2)`.
        """
        from fastapi import HTTPException

        import api
        from aitosoft_failure_class import http_status_for

        config = dict(DEFAULT_CRAWLER_CONFIG)
        config.update(crawler_config or {})
        config.update(overrides)

        async def run() -> Outcome:
            started = time.time()
            try:
                with loopback_allowed():
                    envelope = await api.handle_crawl_request(
                        urls=[url],
                        browser_config=browser_config or {},
                        crawler_config=config,
                        config=self.server_config(wall_clock_s, total_timeout_ms),
                        render_mode=render_mode,
                    )
            except HTTPException as exc:
                return Outcome(
                    url, exc.status_code, None, exc.detail, time.time() - started
                )

            # Mirrors server.py's /crawl status mapping (server.py:960-983):
            # the envelope is what MAS parses, the wire status is what its retry
            # policy keys on, and the whole point of `failure_class` is that
            # those two can disagree. Same `http_status_for` the server calls.
            results = envelope["results"]
            status = 200
            if all(not r.get("success") for r in results):
                status = http_status_for(r.get("failure_class") for r in results)
            return Outcome(url, status, envelope, None, time.time() - started)

        return self._loop.run_until_complete(run())

    # -- teardown --
    def close(self) -> None:
        """Shut down in the same order server.py's lifespan does, so a pytest
        run leaves no browser behind — the patchright singleton in particular is
        started lazily by the first blocked result and would otherwise outlive
        the session."""
        from aitosoft_patchright_fallback import close_patchright_crawler
        from aitosoft_static_mode import close_static_http_client
        from crawler_pool import close_all

        async def shutdown():
            for closer in (
                close_static_http_client,
                close_patchright_crawler,
                close_all,
            ):
                try:
                    await closer()
                except Exception:  # teardown must not mask a test failure
                    pass

        try:
            self._loop.run_until_complete(shutdown())
        finally:
            self._loop.close()
            self._browser_config_cls.reset_defaults()
            self._browser_config_cls.set_defaults(**self._saved_defaults)


# ── pytest fixtures ──────────────────────────────────────────────────────
# Registered for the whole directory by test-aitosoft/conftest.py.


@pytest.fixture(scope="session")
def fixture_origin() -> Iterator[FixtureOrigin]:
    """The local origin. Session-scoped: one port, one thread, for the run."""
    origin = FixtureOrigin()
    origin.start()
    try:
        yield origin
    finally:
        origin.stop()


@pytest.fixture(scope="session")
def production_path() -> Iterator[ProductionPath]:
    """The real crawl path. Session-scoped: the pool browser launches once."""
    path = ProductionPath()
    try:
        yield path
    finally:
        path.close()
