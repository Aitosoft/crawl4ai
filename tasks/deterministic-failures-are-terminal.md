# Deterministic failures should be terminal: 200 with a true class, not a 500 retried four times

**Status:** open, not started. Opened 2026-11-04 by the optimisation-loop session.
**Size:** S. Small changes in our failure taxonomy; the care is in the contract and in not widening
any branch past its evidence.
**Contract:** MAS acked all of it (`tmp/mas-repo-messages/131-from-us-…` §1). Ship in one deploy,
announced, and name the classes in the announcement. It changes what MAS receives: a 500 becomes a
200 with `success: false`, so their client stops retrying.

## Why

MAS's client retries a 500 three times. For a URL that fails the same way every time, that's four
attempts, each a Chrome render plus a Patchright render, for nothing. In August, **152 of the 163
URLs that ever got a 500 got four in a row** (MAS's `49-data/http500-urls.csv`). The five windows on
2026-11-04 put names on most of them (`optimization-experiments.md` lever 9; ledger rows w1–w5):

| shape | seen | today's path | what's true |
|---|---|---|---|
| **Chrome's inline-PDF viewer shell** (356 bytes on Chrome 157, 174 on Chrome 151; 0 visible characters) | w1: koulutustukku.fi ×2 URLs and hoivaelsi.fi `.pdf`, 4 attempts each | tier-3 structural inference says "blocked", there's no 403/503, so `classify_error_text` returns None and `classify_result` falls to `render_error` → 500 | not a page: `unrenderable_content`, like the other download kinds |
| **A JavaScript shell that renders nothing in Chrome and in Patchright** | w1: getbutton.io/ai-chatbot; w5: qaraton.com/team ×2 names | the same inference path → `render_error` → 500 | ours or the site's, but permanent on both tiers; a class of its own, or `render_defect` |
| **`net::ERR_HTTP2_PROTOCOL_ERROR`** | w4: luppoapartments.fi ×2 names, 4 each | not in `_NET_ORIGIN_*`, so "unclassified net error, treated as ours" → `render_error` → 500 | the origin's broken HTTP/2: `origin_unreachable` (add `ERR_HTTP2_` to the prefixes) |
| **A domain resolving to 127.0.0.1** | w5: smcbrandstore.fi ×2 names | the seed SSRF check refuses it → 400 `bad_request` | the origin's broken DNS: 200 `origin_unreachable`, like `OriginUnresolvable` |

Ship with it, same deploy: **the `render_mode` mislabel.** In `api.handle_crawl_request`, the
exception path's `failed_result(...)` omits `render_mode`, which defaults to `"full"`
(`aitosoft_failure_class.failed_result`). So a static-mode request to a dead domain reports `"full"`.
It's one word in a field MAS parses. Find it by name, because line numbers drift. Its sibling,
static-mode failures logging no `failure_class`, isn't worth building: static mode ran 0 times in
186,178 requests.

## Design points

- **The PDF shell.** The trigger has to be the *shape*, not "minimal text". The inference branch
  exists because a JS shell that rendered nothing *this* time may render next time (`norex.com`). So
  key on something only the viewer shell has. Find it in a real capture: production's is
  byte-identical across hosts, so a fixture can copy it (`fixture_origin`'s `/download/pdf-inline`
  is the route). `test_a_download_is_not_a_retryable_server_error[pdf-inline]` is red on real
  Chrome for exactly this, and green on the devcontainer only because its headless shell has no PDF
  viewer (`fixture_origin.DOWNLOAD_KINDS_THAT_REFUSE_TO_RENDER`). The pass condition is green **in
  the built image** (TESTING.md "Inside a built image").
- **The both-tiers-empty shell.** The patchright tier already runs on these (`[patchright] … STILL
  blocked`). If it also comes back with 0 visible characters, a retry from MAS repeats both. Decide
  the class name with MAS before shipping (`render_defect` says "ours, permanent"; a new class may
  be truer). Keep the single-tier case retryable: that's the `norex.com` lesson.
- **`ERR_HTTP2_`.** It's one prefix in `_NET_ORIGIN_UNREACHABLE_PREFIXES`. Check first that no
  `ERR_HTTP2_` code is ours: the egress proxy speaks HTTP/1.1 CONNECT, and h2 runs end-to-end inside
  the tunnel. Optional, separately: one HTTP/1.1 retry would recover the company
  (`--disable-http2` on a second launch). Weigh it against frequency (once in five windows) and
  against the fingerprint cost of a browser that never speaks h2.
- **Loopback DNS.** `validate_url_destination` stays opaque for the other seven endpoints
  (AITOSOFT_FILES §utils.py). On `/crawl` only, beside `_host_has_no_address`, a host whose every
  answer is loopback (or private?) becomes an origin failure. **Security:** this tells a caller
  that a name resolves privately. The caller is MAS, trusted and token-gated, but keep the message
  generic ("DNS points to a non-public address").
- **Where the wire status comes from:** `http_status_for()` alone (CLAUDE.md "Things that will bite
  you"). Add classes to `NON_RETRYABLE_CLASSES`, never a second mapping site.

## How to verify

Offline: the pure tests in `test_failure_classification.py` and `test_mas_contract.py`, plus a
fixture route per shape. In the built image: `pdf-inline` must go green. In production, over the
next windows: the 500s on these shapes go to 0, and MAS's per-URL retries drop.

## What I'm least sure of

1. That the PDF viewer shell has a stable, unique signature across Chrome versions (174 → 356 bytes
   between 151 and 157 already).
2. That every both-tiers-empty JS shell is permanent. A site that blocks headless browsers silently
   would look the same, and maybe a later attempt from another replica's egress would pass
   (`optimization-experiments.md` lever 12).
