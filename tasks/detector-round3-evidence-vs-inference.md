# Detector round 3: it misses blocks and it invents them, both measured in prod

**Status: DONE 2026-08-01.** Both defects implemented and shipped in one image
with `cleaned-html-collapse-guard.md`, `challenge-interstitial-resolve.md`
phase 2 and `render-500-window-2026-07-31.md`'s S half.

**Three things this file specified were wrong, and one of them was half the
fix.** Read this section before trusting anything below it.

1. **"The four caught hosts prove the pattern side already works"** — the
   sentence the whole design rested on, and it is false. Measured: **no tier-1,
   tier-2 or challenge pattern matches that body at all.** The four *caught*
   hosts were caught by the 403/503 branch's fallthrough (`HTTP 403 with HTML
   content`), which is a status rule. So "gating the prose-pattern tiers on
   visible text closes the class" closes nothing — there was no pattern to gate.
   The fix needed a **new block-notice tier** as well as the gate change.
2. **Gating on visible text alone re-opens MAS's worst false-positive family.**
   ~15 of their 22 `Access Denied` corpus hits were healthy Shopify storefronts
   with an `/pages/access-denied` menu link, and our fixture for that family has
   **247** characters of visible text — *under* any sane text gate. The tier
   therefore requires the notice to be in a `<title>`/`<h1>`-`<h3>` **or** to
   cover ≥50 % of the page's text. Without that discriminator this task would
   have re-shipped the defect it cites.
3. **Tier 3 must NOT move onto visible text**, which "every size gate in the
   module is on `len(html)`" implies. Tier 3 is the *inference* tier that
   defect B demotes; loosening it would make every padded page with no
   recognisable notice a blocked verdict on shape alone. The evidence gates
   moved; the inference gates deliberately did not.

**And the fixture was unfaithful on the axis that decides the fix.**
`/block/padded-403` served its notice in a bare `<div>` — zero content elements,
so tier 3 scored **two** structural signals and needed only the size gate to
move. The real page has an `<h1>` and a `<p>`: **two** content elements, **one**
signal, still undetected after a gate change. A fix validated against the old
fixture would have looked complete and closed none of the four hosts. Both
shapes are now served (`?shape=heading` default, `?shape=bare`).

**One thing this file asked for is deliberately NOT done: the unmarked
interstitial.** It carries no evidence of any kind, so the only rule that could
catch it is "a page with little text is a block" — inference, i.e. defect B
aimed at every small page in a 117,000-page corpus. The received diagnosis was
also incomplete: the page misses `minimal_text` by one character (50 visible,
signal needs `< 50`), so it scores *zero* signals, not one, and no
content-element adjustment would have caught it either. Pinned as today's
behaviour with the reasoning, in
`test_an_unmarked_interstitial_is_stored_as_content`.

**A second real instance of defect A was found in our own artifacts directory.**
`monidor.com` — a stored capture we have held for weeks, returned to MAS at
`success: true` — is an 11,515-byte interstitial with **58** characters of text
and the title `One moment, please...`, sitting just over the old 10 KB challenge
gate. It is better evidence than the synthetic fixture and it needed two new
patterns, again because the gate change alone catches nothing.

**What shipped**

| | |
|---|---|
| `crawl4ai/antibot_detector.py` | challenge tier's byte gate → visible text; new block-notice tier (any status, any size, two discriminators); two patterns from `monidor.com`; `_prose_snippet` shared by three tiers; an explicit evidence/inference boundary in the module docstring |
| `deploy/docker/aitosoft_failure_class.py` | `_INFERRED_BLOCK_RE` — inference reasons no longer mean `origin_blocked`. Discarding the reason does **not** discard the status: 403/503 still block, other 4xx/5xx → `origin_http_error`, no status → `render_error` |
| `test-aitosoft/fixture_origin.py` | `/block/padded-403?shape=heading\|bare`, faithful to MAS's stored markdown |
| tests | 2 red tests inverted; +9 detector cases, +7 classification cases, incl. a sweep asserting every reason `is_blocked` can produce lands on exactly one side of the evidence line, and a false-positive check over all 58 stored real captures |

**The status-evidence branch was added because an existing test caught its
absence.** The first version of defect B threw the origin's status away along
with the reason, turning an empty-bodied 503 into `origin_http_error`.
`test_origin_5xx_is_an_http_error_even_when_the_body_reads_as_blocked` failed and
was right to.

---

**Original task text follows.** All eight cases below are MAS's measurements
against `0.9.2-failure-class`, not hypotheses.
**Priority:** High, and it **gates `preflight-batch-endpoint.md`** — a preflight
whose `blocked_suspect` lies is worse than none, and both defects below make it
lie.
**Effort:** S-M. **Risk:** medium — this is block detection, where a false
negative silently poisons MAS's corpus. Fixture-driven only.
**Evidence:** `tmp/mas-repo-messages/07-from-us-243-host-rescrape.md` §4, §5.
Also closes `tasks/antibot-minimal-text-false-positive.md`, whose latent defect
has now been observed live.

**Defect A already has a red test, as of 2026-07-31.**
`tasks/done/fixture-origin.md` shipped `/block/padded-403` — ~80 KB body, ~36
characters of visible text, HTTP 202, every parameter overridable
(`?bytes=`, `?text=`, `?status=`). Two tests pin the defect through the real
production path and isolate it to the size gate rather than to the body:

- `test_a_padded_block_page_is_not_detected_today` — asserts today's
  `success: true, failure_class: none`. **Invert it; do not delete it.**
- `test_the_padding_is_the_only_difference` — the same notice at `?bytes=0` *is*
  detected, so the gate is the whole mechanism.

A third test, `test_an_unmarked_interstitial_is_stored_as_content`, is the same
failure reached from the other side: strip the vendor marker and the "Just a
moment" title, and one sentence of Finnish prose (53 characters) clears every
tier — because tier 3 counts an `<h1>` and a `<p>` as "has content elements".
That is worth fixing in the same pass and is why this task is about evidence
rather than about adding patterns.

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
  **Settled 2026-07-31 (MAS message 09 §5): leave the classification alone.**
  They agree we should report the origin's status; overruling a 403 because the
  body looks like content is the same shape as the `norex.com` invention, pointed
  the other way, and they would rather have a conservative class they can
  re-derive than a permissive one they cannot see through. See the next section
  for the small thing they *did* ask for.

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
- ~~**Flip envelope `success` to the aggregate.**~~ **DEFERRED out of this image,
  coordinator decision 2026-08-01.** The collapse-guard session argued against
  bundling it and the argument holds: MAS's message 09 says the envelope's
  `success` **is never read on 2xx** — they take `results[0]` — so the flip buys
  no behaviour, while breaking a pinned contract (`test_static_mode.py:257`) in
  an image that already changes static mode's wire-status mapping. Two contract
  changes in one deploy is how a measurement gets spent for nothing. It stays
  agreed with MAS and stays worth doing; do it in its own change, where a
  surprise is attributable. **Do not implement it here.**
- **A field saying content was present despite the origin's status — KEEP, with
  one condition.** MAS asked for this by name (message 09 §5) and it is the whole
  of what they want out of `fodbar.fi`. It is smaller than a reclassification:
  keep reporting the origin's 403, keep `origin_blocked`, add one field so *they*
  can decide, where 117,000 stored pages are to compare against. The
  collapse-guard session wanted this deferred too, on the grounds that a new
  field should not arrive unannounced — that concern is right and is met by
  **shipping it only if message 10 describes it**. If message 10 has not gone out
  when this image is ready, drop the field rather than delay the image; it is
  additive and can follow. The measurement already exists in
  `aitosoft_collapse_guard` (visible text vs markdown), so this is a naming and
  plumbing job, not a new computation. Name the unit if it is a count — markdown
  characters, not HTML bytes.

## Verification

- **No live requests. This task needs none** — an earlier draft proposed fetching
  `talpa.fi` for the real 80,671-byte body, which was fetching a page to test a
  property that can be stated in one line. The defect is that our size gates read
  `len(html)` while the page's *visible text* is ~50 characters, so a **synthetic**
  body — 80 KB of padding, `403 - Forbidden` in a heading, served at status 202 —
  exercises it exactly. **That fixture is already built** and covers the whole
  production path rather than just `is_blocked`: `/block/padded-403` in
  `test-aitosoft/fixture_origin.py`, shipped with `tasks/done/fixture-origin.md`,
  with `?bytes=`, `?text=` and `?status=` all overridable.
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

## Deploy

**This is the image that ships `cleaned-html-collapse-guard.md` too**, and
possibly the memory-guard fix from `render-500-window-2026-07-31.md`. Land all of
it first, then one deploy:

1. Full offline suite green (`pytest test-aitosoft/`) — **192 tests as of
   2026-08-01**, including the inverted red tests rather than deleted ones.
   **One known flaky test:** `test_fixture_origin.py::test_the_wall_clock_fence_is_a_504_and_ours`
   failed 1 of 3 full runs during the collapse-guard session and passed 192/192
   in the coordinator's check. It is load-sensitive, pre-existing, and untouched
   by that diff. Re-run before believing it, and do **not** treat a single red
   there as this image's regression — but do not wave through a *second* failure
   in the same file either, since that is where the browser-driven coverage is.
2. Tier 1 regression 4/4 — `python test-aitosoft/test_regression.py --tier 1
   --version <label>` — **before** the deploy, not after.
3. `./azure-deployment/deploy-image.sh <tag>`. Never set env vars during a
   deploy; that is how MAS's token has been broken before.
4. Prod smoke, then close `tasks/antibot-minimal-text-false-positive.md`, whose
   latent defect this ships the fix for.

Message 10 to MAS goes out on its own schedule (it needs
`challenge-interstitial-resolve.md` and `render-500-window-2026-07-31.md`, not
this deploy) — but if this ships first, it carries the wire status the collapse
guard is served at, which is one of the four things they are waiting for.
