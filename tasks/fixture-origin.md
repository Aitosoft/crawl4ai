# A local fixture origin, so failure classes stop costing customer-site traffic

**Status:** Open — do this first. Three other open tasks are cheaper and safer
once it exists, and one of them is currently written as "spend six page loads on
hosts that already distrust us".
**Priority:** Highest. It is small, it is reusable, and it removes the standing
reason every diagnosis has ended up hitting a live site.
**Effort:** S. **Risk:** none — test-only code, no production path touched.
**Evidence:** the pattern of the last month, not a single incident. See "Why" below.

## Why

Every failure class we have diagnosed since 2026-04 has been diagnosed against a
customer's website:

| Host | Hits | For |
|---|---:|---|
| `maitokolmio.fi` | 8 | one config matrix |
| `kiertopakkaus.fi` | 4 | one nested `<noscript>` |
| `konecranes.com` | 3 | one Varnish 403 |
| four MAS-nominated challenge hosts | 1 each | one probe |
| `talgraf.fi` | — | **permanently Cloudflare-blocked by our own over-scraping** |

And the traffic all leaves from one address. Three facts compose badly:

1. **MAS's fetches and ours are the same egress.** Every MAS request is served by
   our replicas from our IP. There is no "their side" of the site-safety budget —
   their 251-page-load re-scrape and our test hits draw on one account.
2. **That address is not ours.** The container app environment has no VNet
   integration (`vnetConfiguration: null`, forensics §0), so we egress from
   Azure's shared SNAT pool. We can inherit a stranger's reputation and we cannot
   durably build our own.
3. **We therefore cannot distinguish "this host blocks Azure datacentre IPs" from
   "this host blocked us because of what we did."** That is an epistemics
   problem, not a politeness one, and it silently corrupts every conclusion in
   `residential-egress-retry-path.md`.

The offline suites we already have (130 tests) are excellent at what they cover:
**pure functions** — `strip_noscript`, `is_blocked`, `classify_result` — fed
synthetic HTML strings. What has never had an offline instrument is anything
involving **time, navigation or the browser**: challenge resolution, hydration
races, `page.content()` against a navigating frame, redirect chains ending in a
block. Those are exactly the classes that have cost us live traffic.

## What to build

Upstream already ships the idiom — `tests/async/test_redirect_url_resolution.py`
runs a `http.server.HTTPServer` on a thread and drives it with `AsyncWebCrawler`.
Adopt that rather than inventing a harness; it is one of the cheapest instances
of "use what the crawl4ai team gives us" available.

`test-aitosoft/fixture_origin.py` — a threaded HTTP server with a route per
failure class, and a pytest fixture that starts and stops it. Start with the
classes we have actual evidence for and can name:

| Route | Serves | Which task needs it |
|---|---|---|
| `/challenge/resolve-after/{s}` | interstitial that becomes content after N s (DOM rewrite) | `challenge-interstitial-resolve.md` |
| `/challenge/resolve-by-nav/{s}` | interstitial that top-level-navigates to content | same, and forensics §1's `page.content()` race |
| `/challenge/never` | interstitial, forever | same — the `origin_blocked` control |
| `/block/padded-403` | ~80 KB body, ~50 chars visible text, status **202** | `detector-round3-evidence-vs-inference.md` defect A |
| `/block/varnish-403` | ~425 B Fastly/Varnish body at 403 | `blocked-host-retry-economy.md` |
| `/hydrate-after/{s}` | near-empty body that paints content after N s | MAS's `revisol.fi` class |
| `/redirect-to/{route}` | 301 into any of the above | pins the `effective_status` fix |
| `/collapse/{shape}` | a large body carrying one markup shape from the swallowing family | `cleaned-html-collapse-guard.md` |

Two properties matter more than the route list:

- **Serve the real production path**, not a unit-test shim. The fixtures are only
  worth building if a request goes through `aitosoft_entry` →
  `api.handle_crawl_request` → the pool browser, so that `failure_class`,
  `render_mode` and the wall-clock fence are all exercised. A fixture that tests
  `is_blocked` in isolation adds nothing we do not already have.
- **Parameterised, not hard-coded.** The delay, the body size and the status are
  arguments. Every future failure class should be a new parameter or a short new
  route, never a new site.

`localhost` interacts with `egress_broker`, which exists to refuse internal
targets. Do not weaken it. Find the seam the existing offline suites already use
for this, or run the fixture on a loopback alias the broker is configured to
permit **in test configuration only** — and assert in the same suite that the
production configuration still refuses it. A fixture origin that quietly disables
our SSRF guarantee would be a bad trade for any amount of convenience.

## The rule this establishes

Write it into `TESTING.md` next to the existing site-safety section:

> **Live traffic is the last instrument, not the first.** A new failure class
> gets a fixture route. A live request is justified only when the question is
> about a specific third party's behaviour and cannot be answered any other way —
> and then it is one request, recorded in `TEST_SITES_REGISTRY.md`, with the host
> added to the burned list in the same session.

That is roughly what we have been doing by exception. Making it the default is
the change.

## Verification

- The four `challenge/*` routes reproduce, offline, the shape MAS observed: an
  interstitial captured as content at `domcontentloaded` + 2.0.
- `/block/padded-403` at status 202 is *not* flagged by today's detector (the
  defect) and *is* after `detector-round3-evidence-vs-inference.md` (the fix).
- The suite runs in CI-time — seconds, not minutes. If a route needs a 10 s
  delay to be meaningful, make the delay a parameter and use 1 s in the default
  run.
- `pytest test-aitosoft/` stays green, and the offline count in
  `AITOSOFT_CHANGES.md` is updated.
