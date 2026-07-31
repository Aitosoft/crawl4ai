# Detector round 3: it misses blocks and it invents them, both measured in prod

**Status:** Open — ready to implement. All eight cases below are MAS's
measurements against `0.9.2-failure-class`, not hypotheses.
**Priority:** High, and it **gates `preflight-batch-endpoint.md`** — a preflight
whose `blocked_suspect` lies is worse than none, and both defects below make it
lie.
**Effort:** S-M. **Risk:** medium — this is block detection, where a false
negative silently poisons MAS's corpus. Fixture-driven only.
**Evidence:** `tmp/mas-repo-messages/07-from-us-243-host-rescrape.md` §4, §5.
Also closes `tasks/antibot-minimal-text-false-positive.md`, whose latent defect
has now been observed live.

## Defect A — an 80 KB body whose entire content is "403 - Forbidden" passes

Four hosts returned an 80,671-byte `html` rendering to a 92-character markdown
body — `# 403 - Forbidden / Access to this page is forbidden.` — with
`success: true`, `failure_class: "none"`, at **origin status 202**. The identical
bytes arrived at status **403** on four other hosts and were correctly classified
`origin_blocked`.

| passed | caught |
|---|---|
| `talpa.fi`, `dining.fi`, `cisa.fi`, `jjsteel.fi` (202) | `savaterra.fi`, `sukittajat.fi`, `inktankmedia.fi`, `pqeurope.com` (403) |

Walk `crawl4ai/antibot_detector.is_blocked` with those inputs and every gate
misses for a different reason:

| gate | why it misses |
|---|---|
| tier 1 | no vendor marker in the body |
| challenge tier | gated on `len(html) < 10000`; the body is 80,671 |
| 403/503 branch | status is 202 |
| tier 2 | requires `status >= 400` |
| tier 3 structural | gated on `len(html) < 50000` |

**Every size gate in the module is on `len(html)`, and this vendor pads its block
page to 80 KB.** That is the generalisable defect, not the missing pattern.
`_visible_text()` already exists in the module and returns ~50 characters for
this page; the challenge tier already uses it as a second gate. Gating the
prose-pattern tiers on **visible text** rather than raw bytes closes the class,
and the four caught hosts prove the pattern side already works.

Judge the direction carefully before widening anything: the module's stated
philosophy is that false positives are cheap and false negatives catastrophic,
but **defect B below is a live false positive that cost MAS a healthy host**, so
that trade is no longer free. State in the code which gate you loosened and which
you tightened, and pin both with fixtures.

MAS notes their own block-page pattern required four digits so `403` slipped past
them too; they have fixed that on their side. Two independent misses of the same
page is the argument for making our gate structural rather than adding one more
string.

## Defect B — four `origin_blocked` verdicts that are not blocks

Of MAS's 33 `origin_blocked` results, four are wrong, and the first one is the
expensive kind:

- **`norex.com`** — body is `Crawl4AI Error: This page is not fully supported…`,
  `html` 15 bytes. That is **our own pipeline's placeholder**, reported to MAS as
  the origin blocking us. `aitosoft_failure_class.py`'s documented bias is that
  unrecognised failures are `render_error` and never an origin class, "precisely
  so that a healthy site is never reported permanently broken". This is that
  guarantee inverted.
- **`snuup.fi`** — an ordinary 404 page, classified `origin_blocked` instead of
  `origin_http_error`.
- **`jarvenkylamaatila.fi`** — a 1-character body.
- **`fodbar.fi`** — 3,962 characters of real Finnish page content at origin 403.
  The most arguable of the four; a 403 that still serves content is genuinely
  ambiguous and it may be correct to leave it.

The mechanism is one line of lost provenance. `is_blocked` returns a verdict
regardless of *what kind of evidence produced it*, and
`classify_error_text`'s `_BLOCKED_RE` then maps every `"Blocked by anti-bot
protection:"` string to `ORIGIN_BLOCKED`. But the two kinds of evidence are not
equivalent:

| evidence | example reason string | what it actually establishes |
|---|---|---|
| the origin said so | `HTTP 403 with HTML content`, tier-1 vendor marker | the origin blocked us |
| we inferred it from shape | `Structural: minimal_text…`, `Near-empty content…` | *we* came back with nothing |

The second kind is exactly `RENDER_ERROR`'s definition. Carrying the tier through
— by reason-string recognition in `aitosoft_failure_class.py`, or by returning a
tier alongside the verdict from `is_blocked` — fixes `norex.com` and
`jarvenkylamaatila.fi` directly, and lets `snuup.fi` fall through to
`classify_result`'s existing `status >= 400 → ORIGIN_HTTP_ERROR` rule.

Prefer the change that keeps all matching in one module. `aitosoft_failure_class`
exists so that no call site matches on error text; adding a second set of string
matches *inside* it is consistent, adding one outside it is not. If `is_blocked`
gains a tier in its return value, that is an upstream-file change and belongs in
the upstream-PR list.

Note the interaction with defect A: loosening the size gate widens the
"origin said so" side, and defect B narrows the "we inferred it" side. They pull
in opposite directions on purpose. Ship them together so the net effect is
measurable in one deploy.

## Also in this change (small, contract-visible, already agreed)

- **Document HTTP 202.** MAS's §5: 36 of 243 responses carried origin status 202,
  100 % from the challenge families, and the same 202 served interstitials, block
  pages, real content and empty bodies. It is an anti-bot layer's code, not a
  page status. It belongs in the documented response shape next to
  `redirected_status_code` with that caveat stated, so neither side branches on
  `status == 200` meaning success. See `tasks/challenge-interstitial-resolve.md`
  for what we think it *is*.
- **Flip envelope `success` to the aggregate.** We asked; MAS answered: flip it,
  **on the condition that the HTTP wire status stays 200** — if the flip ever
  moved the wire status their client would route a permanent origin failure into
  its 5xx retry path. `aitosoft_failure_class.http_status_for` already returns 200
  for all-origin-class failures, so the condition holds by construction today.
  Pin that with a test rather than a comment, because it is the load-bearing half.
  Static mode must get the same treatment so the two render modes still agree.

## Verification

- **No live requests. This task needs none** — an earlier draft proposed fetching
  `talpa.fi` for the real 80,671-byte body, which was fetching a page to test a
  property that can be stated in one line. The defect is that our size gates read
  `len(html)` while the page's *visible text* is ~50 characters, so a **synthetic**
  body — 80 KB of padding, `403 - Forbidden` in a heading, served at status 202 —
  exercises it exactly. Build it as `/block/padded-403` in
  `tasks/fixture-origin.md` so the whole production path is covered, not just
  `is_blocked`.
- The real body would only add *pattern* material for identifying the vendor,
  which is `tasks/challenge-interstitial-resolve.md`'s question and is deferred
  there. If it is ever wanted, ask MAS first — they re-scrape these hosts
  naturally, so a copy may already exist without either side making a request.
- `test_antibot_challenge_detection.py` and `test_failure_classification.py` must
  both grow: A's four passed hosts become blocked, B's cases stop being
  `origin_blocked`, and **every existing case stays as it is**. A regression in
  the challenge tier shipped 2026-07-30 would be the worst outcome of this task.
- Assert the envelope-success flip cannot change the wire status.
- Tier 1 regression 4/4 — none are blocked, so the detector must stay silent on
  all four. That is the false-positive check.
