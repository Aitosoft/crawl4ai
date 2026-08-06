# Our consent/overlay scripts delete the page, and two of the three ways are silent

**Status:** DONE — **DEPLOYED 2026-08-06** as `0.9.2-consent-guard`, revision
`--0000037`. Tier 1 4/4, prod smoke green, and **proved in production on
`www.kubler.fi`**: 15 bytes at HTTP 500 before, 55,545 chars of markdown and 5
contact emails after, with `av-cookies-no-cookie-consent` still on `<html>` and
the guard's own line naming it (`node=html structural=True`). MAS's segment 2 is
unblocked.
**Size:** planned M, delivered M. Two JS files, one strategy method, one
classifier branch, two fixture route families, 20 tests.

**Written by the coordinator session that ran the forensics. Argue with it.**
Nine consecutive sessions have found the previous session's file materially
wrong about something load-bearing, and this one already found *itself* wrong
twice while being written (see "Two things I talked myself out of"). You have
the same repo, the same tools and a cleaner context than I had. The measurements
below are all re-runnable in minutes; re-run the ones the fix rests on.

---

## What shipped, and what the implementing session changed (2026-08-06)

**The diagnosis reproduced exactly.** Every shape, every number, and the branch
trace through `guard_result` were re-derived through the browser against
`/consent/{shape}` and matched. That is unusual for this repo and worth saying
plainly. The three changes below are all about *how* to fix it, not *what* is
broken. Full change record: `AITOSOFT_CHANGES.md` 2026-08-06.

| # | change | file |
|---|---|---|
| 1 | Structural guard — `documentElement`/`body`/`head` are never removed, whatever matched, in Phases 3 **and 4** | `remove_consent_popups.js` |
| 2 | The 20 generic selectors **observe instead of removing**, and report | `remove_consent_popups.js` |
| 3 | Phase 5's `document.body.style` accesses null-guarded | `remove_consent_popups.js` |
| 4 | Same structural guard; `backgroundColor.includes("rgba")` → a real alpha test | `remove_overlay_elements.js` |
| 5 | Read the report, log three counters, detect a click-navigation from `page.url` | `async_crawler_strategy.py` |
| 6 | No `<body>` in the capture → `render_defect` at 200 (the sibling task) | `aitosoft_failure_class.py` |
| 7 | `/consent/{shape}`, `/consent/elsewhere`, `consent_reports()` | `fixture_origin.py` |

**1. "Drop the generic selectors" would have deleted the measurement the
plan depends on.** Step 5 of the cross-repo sequence branches on whether the
declined-removal counter fires often or never — and a deleted selector cannot
decline anything. The generics are kept and *evaluated*, removal-free: one
`querySelectorAll` pass we were already doing, logging `chars` (the match) and
`pagechars` (the page). That ratio is the whole question the 7-host corpus could
not settle, and it also answers MAS's third A/B arm from our own logs rather
than from their traffic. This is the one change I would defend hardest.

**2. The structural guard and the generic drop were indistinguishable in
test.** With the generics gone, the Enfold class matches nothing at all — so
every `<html>`/`<body>` fixture would stay green *with the guard reverted*, and
the suite would have been asserting one fix twice. Added `/consent/named-root`
(`<body id="cookie-notice">`, one of the **120 named** selectors), which only
the guard can pass. Generalisable: when two fixes cover the same symptom, at
least one fixture has to be reachable by only one of them.

**3. The overlay fixture had to be small, and the first draft was wrong.** The
file's measurement describes "an absolutely-positioned hero containing the
contacts". A full-width hero is removed by that script's **size** rule, which is
legitimate and survives the fix — so a fixture shaped like the measurement would
have failed for a reason that is not the defect. The route serves a 280×160
opaque box: under every size bound, so only the degenerate `rgba` clause could
ever have removed it.

**4. The counter nearly shipped on a channel that would have mangled it.** The
obvious place to log from a crawl4ai file is `self.logger` — and `AsyncLogger`
renders through a rich console, which (a) prints only when `verbose` is set,
and `verbose` is **client-settable** through `BrowserConfig`; (b) **wraps at the
console width**, so a 190-character counter line becomes two Log Analytics
records and any query touching two fields loses rows; (c) **eats `[`**, because
`_log` escapes the message template but inserts values raw and `[[` is not a
rich escape — `[class*="cookie-notice" i]` rendered as the empty string. All
three found by printing one line and reading it, which took two minutes and
would have cost a segment. The counters now use `logging.getLogger(__name__)`,
the same channel as `COLLAPSE RECOVERED` / `RESULT FAILURE`.

**Two smaller things.** `classify_error_text` never sees `html`, so the
root-gone check lives in `classify_result`, **below** both origin branches — a
root that vanished on a page the origin refused is still the origin's verdict to
give. And the click-navigation check is in **Python, not the snippet**: a click
that navigates destroys the JS execution context, so the snippet's own
`location.href` comparison would never run and its return value would never
arrive.

**On the click channel, I took the file's recommendation: log, do not
re-navigate.** Both click surfaces the file reproduced are detected;
`test_a_self_inflicted_click_navigation_is_detected` asserts today's defect on
purpose. 0.046 % of companies does not buy rebuilding navigation state.

**Verified red before green.** With `crawl4ai/js_snippet/` reverted to upstream,
10 of the 12 new browser tests fail; the 2 that pass are the click tests, whose
detection is Python-side and deliberately unchanged by the JS. With
`aitosoft_failure_class.py` reverted, 4 of the classification tests fail. A test
that would have been green anyway proves nothing, and this suite has shipped
one of those before.

**What I did not do, and someone should decide.** The `CONSENT DECLINED` line
fires on any page with a cookie-shaped class the named list misses, which on a
120,000-fetch sweep could be thousands of lines. That is the intended volume —
it is the population we cannot otherwise measure — but if it turns out to be
per-page noise rather than per-finding signal, the fix is a threshold on
`chars`, not a removal of the counter.

---

## The defect in one paragraph

`crawl4ai/js_snippet/remove_consent_popups.js` — which MAS sends on **every**
request (`remove_consent_popups: true`, pinned in `test_mas_contract.py:55`) —
finishes with 20 generic selectors — 18 substring patterns like
`[class*="cookie-consent" i]`, plus `.cc-banner` and `.cc-window` — and calls
`el.remove()` on everything they match, with no guard on *what* they
match. `kubler.fi` runs the Enfold WordPress theme, which writes
`av-cookies-no-cookie-consent` onto `<html>` to mean *"cookie consent is switched
off on this site."* That class contains the substring, so we delete
`document.documentElement`, and `page.content()` returns the serialized doctype
alone — `<!DOCTYPE html>`, 15 bytes. lxml then raises `Document is empty`, and
our own `Crawl4AI Error: This page is not fully supported` placeholder becomes
the page MAS receives. **The selector matched a flag asserting there is no
consent banner, and deleted the site because of it.**

Both JS files are **byte-identical to `upstream/develop`** (checked with
`git diff upstream/develop -- crawl4ai/js_snippet/`). This is an upstream defect
on a theme sold in the hundreds of thousands, not our patch misbehaving. It is a
strong upstream PR — see "When to file it".

---

## The four shapes, and why only two of them are loud

All measured through the real `AsyncWebCrawler` against a local origin, with
MAS's live config (`remove_consent_popups=True`, `wait_until="domcontentloaded"`)
and scored with the real `guard_result` / `classify_result` / `http_status_for`.

| what carries the trigger | what we capture | wire | `failure_class` | contacts |
|---|---|---|---|---|
| `<html>` (Enfold, confirmed on `kubler.fi`) | `<!DOCTYPE html>`, **15 B** | 500 | `render_error` | lost |
| `<body>` | head only — 87 B, or 20,087 B with a padded `<head>` | 500 | `render_error` | lost |
| **an inner element that also contains content** | **99.5 % of the expected markdown** | **200** | **`none`** | **lost** |
| **a Phase-1 click that navigates** | **a different page, in full** | **200** | **`none`** | **lost** |

The bottom two rows are the ones that matter. Numbers from the run, so you can
tell whether you have reproduced the same thing:

- **Inner element.** 28 KB healthy page, contact block inside
  `<footer class="site-footer cookie-notice-footer">`: `success: true`,
  `failure_class: "none"`, HTTP 200, **27,628 chars of markdown against the
  control's 27,727**, collapse guard silent, email and phone gone. Four wrapper
  variants (`footer` by class, `section` by id, `div.cc-window`, `aside`)
  behaved identically. A smaller variant scored 14,427 against a control of
  14,494.
- **Click.** `button[id*="accept" i]` matched an ordinary `accept-terms-btn`;
  the *text-content regex fallback* (`/^got\s*it[!]?$/i`) matched an
  `<a role="button">`. Both navigated, both returned **13,220 chars of the
  destination page** at `success: true` with the wrong document's title.

**The click surface is bigger than the 12 generic click selectors.** Phase 1 has
86 named CMP buttons, 12 generic attribute selectors, a text-content regex
fallback over every button/link on the page, a shadow-DOM pass and an iframe
pass. My fixture tripped two of those five. That is the argument for detecting
the *consequence* (did the URL change?) rather than trying to enumerate the
causes — see "The design space".

### The 15 bytes are diagnostic, and worth knowing by heart

Probed against a local origin: an empty 200 gives **39 B**
(`<html><head></head><body></body></html>`), a body that literally *is*
`<!DOCTYPE html>` gives **54 B**. **Exactly 15 is produced by one thing only** —
`document.documentElement` having been removed, after which Playwright's
`content()` serializes the doctype and nothing else. If you see 15 bytes in a
log, that is this bug and not an empty origin.

### Why the collapse guard cannot help, and must not be extended to try

Branch-traced through the real `guard_result`:

| case | success | visible in | markdown out | which branch ends it |
|---|---|---|---|---|
| control | True | 14,366 | 14,494 | `produced ≥ 500 → None` |
| total loss | False | 0 | 440 | **`gate: successes-only → None`** (line 1) |
| partial loss | True | 14,305 | **14,427** | **`produced ≥ 500 → None`** |

Total loss never reaches the ratio logic at all — `guard_result`'s first line is
`if not result.get("success"): return None`, and the result has already failed.
(MAS's message 19 argued this from the ratio; they were right about the outcome
and wrong about the branch, and we told them so. `tmp/mas-repo-messages/20-…`
§3.) Partial loss dies at the opening screen and **could never fire anyway**:
the deletion happens *before* we capture, so visible-in and markdown-out shrink
together and the ratio stays healthy by construction.

**So do not try to make the guard catch this.** Its inputs are both
post-deletion. The only version that could work is a pre/post DOM snapshot,
which means a second `page.content()` on 100 % of traffic to detect a rare bug —
and it would still not tell you *which selector* fired. A counter at the removal
site is strictly cheaper and strictly more informative.

---

## Both sides are blind, and MAS confirmed it from their end

This is not a prediction any more. From `tmp/mas-repo-messages/21-…` §1: they
check `success`, `status_code` and `redirected_status_code ≥ 400`; all three
pass on a partial loss. *"It reaches us looking like a good page, and nothing in
our client or our agent would flag it… they cannot miss what was never there."*

**And neither archive can size it retrospectively.** Any element matching those
selectors is removed *before* the capture either side stores, so both corpora
are post-deletion by construction. MAS's "0 of 193 pages carry `av-cookies-*`"
is not weak evidence — it is the only possible result. Ours is the same. This is
why the instrument has to be a counter at the point of removal, not a study.

---

## Population, with its limits stated

| signature | hosts | events | window | notes |
|---|---:|---:|---|---|
| `Near-empty content (15 bytes)` — `<html>` gone | **2** | 53 | 30 d | `kubler.fi`, `norex.com` |
| `Structural: no <body> tag` | **11** | 13 | 30 d | 1,791–35,982 B — the `<body>`-deletion shape |
| inner-element silent loss | **unknown** | — | — | unmeasurable from either archive |
| click channel | ≤ 8 companies in 17,439 (**0.046 %**) | — | full MAS archive | MAS's ceiling, `21-…` §2b |

Query both reason strings, not one — `Near-empty content` is gated on HTTP 200,
so the same 15-byte capture at any other status lands under
`Structural: no <body> tag` instead. My first population count said "two hosts"
because I asked the logs one question. `AITOSOFT_CHANGES.md:2090` is where it
was caught: `rederiabeckero.ax`, April, `no <body> tag (15 bytes)`.

**On the 11 `no <body>` hosts.** Chromium always synthesises `<body>` for any
HTML it parses, and `_structural_integrity_check` already excludes XML/JSON, so
a multi-KB capture with no `<body>` means a script removed it after parse. MAS
looked up nine of them (`21-…` §3) and almost all captured *well at company
level* — but they flagged their own evidence as weak for a good reason: one
destroyed page inside a company that stored 92 pages is invisible at company
resolution. **It says the `<body>` channel did not cost whole companies. It says
nothing about pages, and pages are where contacts live.**

**On the click channel.** MAS's two "click-shaped" candidates both have innocent
readings — the Humany widget on `tjareborg.fi` sets its own hash route, and a
decommissioned corporate site redirecting to a group media page is an ordinary
redirect chain. Their 0.046 % ceiling also only detects a click that fires on
*every* page of a company. Treat the channel as small and cheap-to-close rather
than as a live emergency.

**Cost, when it does fire.** Kübler in segment 1: 8 requests, **32 navigations**
(each request is 2 Playwright legs + 2 patchright legs), **266 s = 26.1 % of the
entire run's render seconds** for 1 of 25 companies, on 8 distinct replicas each
cold-booting the patchright singleton.

---

## The design space, and the reasoning I would want back

I am deliberately not giving you an ordered checklist. Here is the shape I
arrived at, why, and where I think it could be wrong.

**A structural guard that needs no threshold.** Refuse to remove
`documentElement`, `body` or `head`, whatever matched. Unconditional, a few
lines, and it covers the named selectors and every generic pattern someone adds
later without reading this file. This is the piece I am most confident in.

**Dropping the generic container selectors.** The census (**corrected on
implementation** — it was 122/18, it is 120/20): 140 container selectors,
**120 named and precise** (`#onetrust-consent-sdk`,
`#CybotCookiebotDialog`, …), **20** generic catch-alls. In our stored
corpus there are **zero captures where a generic catch-all is the only thing
that would match** — the named ones do the work (Cookiebot in 30 files,
Complianz in 11, CookieYes in 4, Cookie Law Info in 1), and `accountor.com`, the
case CLAUDE.md cites as proof the flag earns its place, is Cookiebot. The
failure direction is safe: an unlisted CMP's banner survives and adds a
paragraph of legalese to the markdown. Noise, not loss. **The weakness is that
the corpus is 7 hosts**, which is enough to show the generic selectors are not
carrying the named ones and not enough to prove nobody needs them. MAS's
three-arm A/B (below) is what would settle it, and it needs our image first.

**A URL-change check around the consent pass**, for the click channel. Compare
the page URL before and after; if it changed and no server redirect explains it,
our own click navigated us. Two string reads, and it catches all five click
surfaces including the ones I did not enumerate. What to *do* on detection is
genuinely open — log it and let the counter size it, or re-navigate to the
requested URL and skip the consent pass on the second load. Given the 0.046 %
ceiling I would start with logging and only build the re-navigation if the
counter says it is worth it.

**A counter, and it is not optional.** Every element we decline to remove, and
every URL change we detect, logged with the tag, the text length, and **both the
requested URL and the current URL** (MAS asked for the requested URL beside the
returned one, `21-…` §6 — it is the join key that lets both sides reconcile
without guessing from timestamps). Without this we ship a fix and still cannot
tell MAS how much was being lost, which is exactly where we were with the
`<noscript>` collapse until the `COLLAPSE RECOVERED` / `RENDER DEFECT` split made
it countable for free. Use non-overlapping tokens for the same reason that split
did (`api.py:948` vs `:965`).

**Fixture routes for all four shapes** in `test-aitosoft/fixture_origin.py`,
driven through `production_path`. This is the piece that stops recurrence across
upstream merges, and it is this repo's own standing rule (add a route before you
add a request). It is also the only thing here that will still be paying off in
six months.

### Two things I talked myself out of, and why

**A text-proportion threshold on the generic selectors** — "skip removal if the
element holds ≥ X % of the page's visible text." I was going to recommend it. I
measured what share a *real* CMP container actually holds, and a live Complianz
banner in our own corpus holds **43.3 %** of its page's visible text. So the
threshold fails in both directions: it would not protect a footer holding
contacts (~5 % of a large page) and it would block a legitimate banner removal
at 43 %. **Do not build it.** Caveat on my own measurement: only 2 usable
data points survived, because most stored captures are already post-removal.
If you want to revisit this, that thinness is the first thing to attack — but
note that the structural guard plus dropping the generics needs no threshold at
all, which is a better reason not to build it than any measurement.

**Extending the collapse guard.** Covered above. Its inputs are both
post-deletion; there is no version of it that works without paying a second
capture on every page.

### `remove_overlay_elements` — latent, and worse than it reads

MAS sends `false`, so this is not on the critical path, but it belongs in the
same change and in the same upstream PR. `getComputedStyle(el).backgroundColor`
is `rgba(0, 0, 0, 0)` for **every** element with a transparent background, so
the script's `backgroundColor.includes("rgba")` test is *always true* and the
whole size-and-appearance clause is a no-op. What is left is "visible, and fixed
or absolute". Measured: it deleted an absolutely-positioned hero containing the
contacts and a 40 px fixed nav, at `success: true` with 98 % of the markdown
intact (3,470 chars against a control of 3,542). **Never recommend this flag**,
and if anyone proposes it as a content-quality improvement, this is the
paragraph.

---

## How to re-create the experiments (the scratchpad is gone)

All of these are ~30 lines against a local `http.server` plus the real
`AsyncWebCrawler`; none touches a customer site. The markup is the part worth
keeping:

- **Total loss:** `<html lang='fi' class="html_stretched av-cookies-no-cookie-consent av-no-preview">`
  → expect `len(result.html.strip()) == 15` and `success is False`.
- **Body loss:** `<body class="page cookie-consent-dismissed">` → 87 B, and with
  ~20 KB of inline CSS in `<head>`, 20,087 B. Both `success: False`, the second
  via `Structural: no <body> tag` rather than near-empty.
- **Silent partial loss:** ~120 paragraphs of body text plus the contact block
  inside `<footer class="site-footer cookie-notice-footer">`. Assert the email
  is absent from `markdown.raw_markdown` while `success is True` and
  `classify_result(...) == "none"`.
- **Click:** a large page ending in
  `<button id='accept-terms-btn' onclick="location.href='/other-big'">Accept</button>`,
  and a variant with `<a role='button' href='/other-big'>Got it!</a>`. Assert
  the returned title is the destination's.
- **Byte-signature control:** empty 200 → 39 B, body of `<!DOCTYPE html>` → 54 B,
  `document.documentElement.remove()` → 15 B.

Import the verdict chain from `deploy/docker` (`classify_result`,
`http_status_for`, `guard_result`) so you are scoring what production scores.
**Do not name a scratchpad file `idna.py`, `click.py` or anything else that
shadows a stdlib or site-package module** — I lost two runs to exactly that.

---

## What I am least sure of

- **Whether the inner-element silent channel is common or rare.** The mechanism
  is proven; the frequency is not, and nothing either side holds can measure it.
  The generic substrings are cookie-specific words that mostly appear on genuine
  cookie UI, where removal is *correct*. I may be over-weighting it. The counter
  is what turns this into a number.
- **Whether the 11 `no <body>` hosts are ours.** The byte profile says a script
  removed `<body>`; it does not say whose script. At least one
  (`jarvenkylamaatila.fi`) is a known JS-challenge host, and a `<frameset>`
  document would land there legitimately too.
- **The 7-host corpus behind "the generic selectors do no work."** Directionally
  strong, not conclusive.
- **What to do on a detected click-navigation.** I have argued for logging
  first. If the counter shows it is frequent, re-navigation is the obvious next
  step and I have not thought it through.

---

## Where everything lives

| what | where |
|---|---|
| the exchange that produced this | `tmp/mas-repo-messages/17-…` through `21-…`; ours are `20-…` and `16-…` |
| the confirmed Enfold class, verbatim | `18-…` §1 |
| MAS's click-channel measurement and its ceiling | `21-…` §2 |
| MAS's lookup of the 11 `no <body>` hosts | `21-…` §3 |
| the division of labour both sides agreed | `20-…` §6, accepted in `21-…` §4 |
| the selector lists | `crawl4ai/js_snippet/remove_consent_popups.js` (Phase 1 clicks, Phase 3 containers), `remove_overlay_elements.js` |
| where the scripts run, and that it is before capture | `async_crawler_strategy.py:1134-1139` vs `:1153/:1174` |
| the guard whose branches are traced above | `deploy/docker/aitosoft_collapse_guard.py` |
| MAS's real request shape | `test-aitosoft/test_mas_contract.py:54-55` |
| the counter precedent to copy | `api.py:948` / `:965`, and the reasoning in `aitosoft_collapse_guard.py` |
| the sibling task | `tasks/total-loss-is-permanent-not-transient.md` |

---

## Cross-repo, and when to file upstream

**MAS is holding segment 2 (50 companies) until this image is out.** They are
not gating on a date and have asked for the window rather than a promise.

**Their three-arm A/B is the coverage check this fix needs, and it needs our
image first** — off / on-today / on-with-the-fix. We suggested they wait rather
than run two arms now, because a two-arm result would not change what we build.
If they have already run it, that is fine and the third arm is still the useful
one.

**File the upstream PR after segment 2, not before.** "This deletes documents on
Enfold sites, here are N occurrences in a production sweep" is a far stronger
submission than a synthetic reproduction, and waiting costs nothing. Upstream
`develop` moves slowly (`tasks/file-upstream-prs.md`), so there is no race.
