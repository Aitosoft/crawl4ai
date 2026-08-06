# Segment 2: the consent counter read, and three things it found

**Status:** DONE — this is step 5 of `tasks/README.md` "The plan across both repos".
**Size:** the reading was S. Two of the findings below are new task-shaped work.
**Window:** 2026-08-06 13:38–14:36 UTC, 58 min. Image `0.9.2-consent-guard`,
revision `--0000037`. Watched live from a monitoring session; **zero live crawl
requests of our own** — everything here is Log Analytics over MAS's traffic.

Re-run any figure with `az monitor log-analytics query -w "$LAW_ID"` and
`ContainerAppConsoleLogs_CL | where TimeGenerated between
(datetime(2026-08-06T13:38:00Z) .. datetime(2026-08-06T14:40:00Z))
| where ContainerAppName_s == 'crawl4ai-service'`. The tick script used is
disposable; the queries in it are the ones below.

---

> **CORRECTED 2026-08-06, after MAS's `27-…` arrived and the two repos were
> reconciled request-by-request.** Three figures in the first draft of this file
> were wrong, all in the same direction — **I counted the `RESULT FAILURE` token
> instead of the `failure_class=` field, and missed the entire exception path.**
> The corrections are inline below and summarised in §7. The consent findings
> were unaffected and are now confirmed independently at the byte level.
>
> **The two repos now reconcile exactly**, in both directions:
> 274 ingress `/crawl` requests = MAS's 264 terminal outcomes + 9 retries of the
> 3 `render_error` outcomes + 1 retry of the 429. 21 `origin_unreachable`
> attempts on 13 companies, both sides. 27 declined root removals on 3 companies,
> both sides. And MAS's `27-…` §5c quotes the four correlation ids
> `c6d1302332b8`, `9865eee62afc`, `8b93430bcee5`, `b05f029a8cbd` for the
> `turkusteve.com` PDF — **byte-identical to our own four `server error 500`
> lines.** Both instruments are sound.

## The shape of the run

| | |
|---|---|
| HTTP `/crawl` requests at the ingress | **274** — the only complete count |
| Render admissions | **261** (274 − 12 pre-admission DNS refusals − 1 × 429) |
| Companies / prospects | **50** (MAS). Pages stored: **209** |
| Distinct domains we were asked to render | **61**, and the excess over 50 is **MAS-side and expected**: their agent follows links onto sibling and parent domains — `posti.fi`+`posti.com`, `molnlycke.com`+`molnlycke.fi`, `scandichotels.com`+`scandichotelsgroup.com`, and seven Kesko/S-group brands. The known parent/subsidiary ambiguity, not a defect |
| **Denominator warning** | **A domain is not a company and neither is a page.** The first draft of this file quoted "3 of 61 domains (4.9 %)" for the consent finding. The company figure is **3 of 50 (6 %)**; MAS's page figure is **27 of 209 stored (12.9 %)**. Three units, three numbers, and only the first two are comparable to anything MAS reports |
| `[COMPLETE]` lines | 289 — exceeds admits because a patchright retry emits a second `[COMPLETE]` with no second `ADMIT` (already recorded in `tasks/README.md`) |
| Wire statuses | **261 × 200, 12 × 500, 1 × 429** |
| Latency, **successful renders only** | p50 **4.49 s**, p90 **6.27 s**, p99 9.66 s, max 16.19 s |
| RenderGate rejects | **1**, at ramp-up. Queue wait was 0 for the rest of the run |
| Fence-504 / janitor force-close / memory refusal | **0 / 0 / 0** |
| `COLLAPSE RECOVERED` / `RENDER DEFECT` tokens | **0 / 0** |
| Pool memory | peak **63.8 %** against the 85 % guard; pool `hot` never exceeded 2 |
| Anti-bot retry legs | 72 |

**Read the latency line carefully, because the naive query lies.** Over *all*
`[COMPLETE]` lines p90 is 22.4 s, which looks like a 3.5× regression against
segment 1's 6.32 s. Filtered to successful renders it is 6.27 s — statistically
the same run. The entire tail is failing hosts burning retry legs. A p90 over a
population that includes four-navigation failures is not a latency measurement.

**The capacity and memory families stayed at zero for the fourth consecutive
workload.** Nothing in that family needs building; this is now a very
well-supported claim rather than a hopeful one.

---

## 1. The counter fired, and the loud channel is larger than any prior estimate

| | |
|---|---|
| `CONSENT DECLINED` | **27 lines / 27 distinct URLs / 3 domains of 61 (4.9 %)** |
| Per domain | `turkusteve.com` 11, `neelevat.fi` 9, `autokari.fi` 7 |
| Node | **`node=html structural=True` on all 27** |
| `structural=False` (the silent inner-element channel) | **0** |
| `CONSENT STRUCTURAL` (a *named* selector hitting a root) | **0** |

Every one of the 27 is the `kubler.fi` shape: a generic substring selector
matching `<html>` on the Enfold WordPress theme, declined by the structural
guard. **27 of 261 renders (10.3 %)** would have been 15-byte captures on
`--0000036`. `kubler.fi` was not a one-off; it is a theme-wide pattern, and
shipping the guard *before* this segment rather than after was the right call.

**Exclude `raw://` from this population.** MAS ran a synthetic consent probe at
13:27–13:28 (their A/B arm check, so message `24-…` landed). Those two lines are
the only `node=div structural=False` hits in the window and they are **not
customer traffic**. A query without `| where Log_s !contains 'raw://'` reports a
silent-channel hit that does not exist. This is the first thing that will trip
whoever re-runs this.

**Which branch this takes** (`tasks/README.md` "What step 5 branches on"): the
*loud* channel was the whole thing on this cohort.

### MAS closed the silent channel properly, and it is a stronger result than our zero

Our counter can only say "the guard declined 27 root removals and no non-root
ones". That bounds the silent channel below ~1.1 % of renders and no further —
**a counter at the point of removal cannot say what was in the thing it did not
remove.** MAS could, because the fix means those elements now survive into
storage, and they read them (`27-…` §2):

> **95 matched containers** (18 at outermost grain). **0 of them contain contact
> information** — no email, no phone, no postal address, across **34,533
> characters** of visible text.

And they checked it was *absence* rather than *non-detection*: any `@` anywhere,
any run of 3+ digits, Finnish and English phone/mail/address prose cues, Finnish
numeral words. **All zero.** They also ran a control — `cookieconsent`
unhyphenated, in neither of our lists — which stayed flat (16.9 % → 15.8 %) while
the signal went 0 % → 12.9 %, so the two arms carry comparable consent markup and
the change is our fix rather than the cohort.

**The element counts cross-validate to the root.** Our `n=` fields sum to 115
matched elements (turkusteve 11 pages × 9, neelevat 9 × 1, autokari 7 × 1) against
their 122; the 7-element gap is the other selectors and script/style nodes. But
**both sides independently count 27 roots on 3 companies**, and ours are all
`node=html`. That is the load-bearing number and it agrees exactly.

**So the honest statement is stronger than "no evidence":** on this population the
generic selectors removed **no** contact data even when they matched, *and* their
banner-removal value was **zero** — the only harm they ever did was the root
collision. That is the upstream PR argument, and it does not depend on either
side's private data: `av-cookies-no-cookie-consent` versus
`[class*="cookie-consent" i]` is a collision any maintainer can verify against the
Enfold theme in a minute.

**One thing MAS asked for that we should not skip.** They can see the *match* but
not our removal code, so the step "pre-fix we therefore deleted the document" is
an **inference** on their side, and they say so — their circumstantial support (0
of 29 pre-fix companies ran Enfold vs 3 of 28 post-fix) is only ~4 % against
chance. They explicitly asked us to prove or disprove it, and offered the method:
a `raw://` Enfold-shaped document against retained revision `--0000036`, zero
egress. **We already hold the direct proof** —
`done/consent-scripts-delete-the-page.md` reproduced all four shapes through the
browser, and `kubler.fi` went 15 bytes → 55,545 chars across the fix. Send them
that. The `raw://` A/B is still worth ~11 minutes as a clean artefact for the PR,
because it demonstrates the mechanism without citing anyone's corpus.

**The named list holds.** Zero `CONSENT STRUCTURAL` means no *named* vendor
selector matched a root element, so the census behind "120 named and precise"
survives its first real test. That was the open worry when the guard shipped.

---

## 2. `CONSENT NAVIGATION` fires **3** times, and all three are one false positive

**3 lines** — an earlier draft of this file said 4, from a query run mid-ingestion
before all rows had landed; the count was re-verified programmatically at
`frag_only=True` for each. All three are `www.se.com` product-range pages, and in
every case `before` and `after` differ **only by a fragment** (`#products`) — same
document, no navigation. The detector compares `page.url` before and after the
consent pass, so a same-page anchor click reads as a self-inflicted navigation.

**Fix: strip the fragment before comparing.** `normalize_url` already drops
fragments before dedup (recorded in `tasks/README.md`), so this is the same
family and the repo already holds the opinion.

One of the four also has `requested` ≠ `before`: se.com redirected
`…62049-vamp-valokaarisuojausjärjestelmät/` → `…62049-powerlogic-a5-…`. That is
the *origin's* redirect, and the counter correctly does not treat it as ours —
worth noting because the three-field line makes it visible, which was the point
of MAS's `21-…` §6 ask.

**Genuine click-navigations in 261 renders: zero.** Consistent with MAS's
measured 0.046 % ceiling. The prior — "below some rate, logging is the whole
answer" — stands, and re-navigation should still not be built.

---

## 3. Every 500 in the sweep came from two URLs, and neither is a render error

**12 `render_error` events on 2 domains = 100 % of the sweep's 500s.**
`render_error` is ours ⇒ 500 ⇒ MAS retries 3×, and we add an internal patchright
leg on top of each.

| URL | events | detector verdict |
|---|---|---|
| `turkusteve.com/wp-content/uploads/Turku-Stevedoring-Oy_-ASIAKASTIEDOTE.pdf` | 4 | `Structural: minimal_text, no_content_elements (174 bytes, 0 chars visible)` |
| `nieminen.lol` (both host-forms) | 8 | `Near-empty content (83 bytes) with HTTP 200` |

Neither is a render failure:

- **The PDF is a gap in the 2026-08-02 fix.** `unrenderable_content` catches PDFs
  that trip Chromium's *download refusal*. This one Chromium **renders**, in its
  internal viewer — 174 bytes, zero visible characters — so it falls straight
  through to the tier-3 inference gate instead. The download path was never
  reached. Same family as the vCard finding, reached by a different route, and
  it reproduces that finding's headline exactly: one URL produced every 500 of
  the run.
- **`nieminen.lol`'s 83 bytes is the origin's own content.** 83 B is none of the
  diagnostic shapes this repo has established — 15 B is a deleted root, 39 B an
  empty 200, 54 B a body that *is* `<!DOCTYPE html>`. It is a real, tiny
  document, almost certainly a parked or holding page. We charged it to
  ourselves.

Cost: 12 × ~30 s ≈ **6 minutes of render slots**, ×3 MAS retries on top, for two
URLs that can never succeed.

**This is the `norex.com` inversion from a third angle:** the inference tier
calling the origin's own non-page *our* render error. The lever is the one
`aitosoft_failure_class.py` already documents — **permanence, not ownership**.
The fix is that this outcome must not be a retryable 500; it is *not* "delete or
loosen the inference tier", whose byte bounds are deliberate and whose job here
is genuinely ambiguous input. Do not re-litigate the tier.

---

## 4. `delotec.fi`'s `render_defect` is not our JS, and the patchright leg cannot rescue it

The step-5 branch "`render_defect` fires at all after the JS fix → something we
have not identified is still deleting documents" was hit. What it found:

- **Zero `CONSENT` lines on the host**, so our consent snippet did not touch it.
- `Structural: no <body> tag (2015 bytes)`, and **two engines agree** — the
  patchright leg dies on
  `Page.wait_for_selector: Timeout 30000ms exceeded … waiting for locator("body")`.
- That wait is **upstream's** `async_crawler_strategy.py:898`
  (`wait_for_selector("body", state="attached", timeout=30000)`). On the first
  tier the timeout is swallowed by the `except Error` branch
  (`ignore_body_visibility`) and capture proceeds; on the patchright leg it
  raises. So a no-`<body>` capture **guarantees** a 30 s patchright timeout that
  cannot possibly succeed: it waits for exactly the element that is missing.
- **`_is_blocked` gates that retry on the block-marker *string***
  (`aitosoft_patchright_fallback.py:163`), not on classified permanence.
  `render_defect` is in `NON_RETRYABLE_CLASSES`, but that set governs the wire
  status and MAS's retries — **not our own internal tier.** We retry a class we
  have formally declared terminal.
- Cost: 4 navigations, ~127 s of a render slot per URL, × 2 URL forms.
- The wire contract **held**: terminal at 200, and MAS did not retry.

**The root cause of the missing `<body>` is unknown and I did not determine it.**
Frameset and XML-parsed-document are the candidates (both produce a document with
no `<body>` element that `locator("body")` can never resolve). I deliberately did
not crawl the host — golden rule 0, and MAS was mid-sweep on it. **MAS stores
`html` on every page since 2026-08-04, so they hold those 2015 bytes**; asking
them is the cheap instrument and the correct division of labour.

---

## 4b. The failure tally, corrected — and why the first one was wrong

| class | attempts (corrected) | companies | first draft said |
|---|---:|---:|---|
| `origin_unreachable` | **21** | **13** | 9 events / 6 domains ❌ |
| `origin_blocked` | 11 | 5 | 11 / 5 ✅ |
| `origin_http_error` | 5 | 2 | 5 / 4 host-forms ✅ |
| `render_error` | 12 requests → **3 terminal** | 2 | 12 events ✅ (unit unstated) |
| `render_defect` | 2 | 1 | 2 / 1 ✅ |

**The `origin_unreachable` error was mine and the cause is a document.**
`OVERNIGHT_PLAYBOOK.md` said *"`RESULT FAILURE` is the row to count from, and
ORIGIN-FAIL is not — `arun` almost never raises."* True for every class **except
this one**: `_normalize_and_validate_seeds` (`api.py:760`) runs **before** render
admission, so a dead domain raises `OriginUnresolvable` (`api.py:698`) and emits
**`ORIGIN FAILURE`**, never `RESULT FAILURE`. 12 of the 21 — **57 %** — arrived
that way, on 7 companies my query could not see: `yxgroup.fi`, `chembiz.eu`,
`lacapitale.fi`, `aviapoint.fi`, `aluttinum.fi`, `neele-vatlogistics.fi`,
`macrent.fi`. Playbook corrected; the rule is now **key on `failure_class=`,
never on the token.**

**Nothing was broken — the wire behaviour was right throughout.** All 12 returned
**HTTP 200** with `failure_class=origin_unreachable`, cost **no render slot and no
browser** (the gate is acquired at `api.py:832`, long after the seed check), and
MAS's agent filed them as "this company has no website". The `16-…` §0 contract
is holding in production. This was purely a hole in *our own measurement*, which
is the more insidious kind: the fix worked and the counter could not see it.

**A second-instrument check that costs nothing and would have caught it:**
ingress `/crawl` requests − `RenderGate ADMIT` lines = pre-admission refusals +
429s. 274 − 261 = 13 = 12 + 1. Exact. Use it on every future segment.

**Two log holes remain, both found while chasing this one:**
- **`render_mode: "static"` failed fetches emit no `failure_class` at all** —
  `[static] request error:` / `[static] timeout after` at INFO
  (`aitosoft_static_mode.py:301,307`), while `_static_error_result` defaults the
  class to `origin_unreachable` (`:164-179`). **No `failure_class` query can ever
  count these**, and it matters precisely because MAS pivots a host to static
  *after* it has already misbehaved. ~6 lines to fix.
- **`api.py:1198` calls `failed_result(...)` without `render_mode`**, which
  defaults to `"full"` (`aitosoft_failure_class.py:507`). Because the seed check
  precedes the static short-circuit (`api.py:764`), a **static** request to a dead
  domain is reported to MAS as `render_mode: "full"`. One word, and it is in a
  field they parse.

## 4c. MAS's §5 classifier claims, verified in source — one is a misreading, one is not a defect

Both were checked against the code and against this run's own log lines rather
than adopted. Neither requires a code change.

**§5a — "identical 404s land in two classes, and the split follows the host" is
PARTLY TRUE: the observation is right, the diagnosis is wrong.** The
discriminator is not the host and it *is* on the wire they already receive — it is
**`success`**. `classify_result` returns `NONE` for any successful result
(`aitosoft_failure_class.py:421-422`); nothing keys on 404 at all.

- The **13 `none` 404s** are content-bearing 404 pages. They *rendered*, so
  `success=True` (`async_webcrawler.py:531`), and `status_code: 404` is present
  and correct on every one. This is the mechanism MAS already accepted and
  withdrew a complaint on (`18-…` §3).
- The **3 `hinauspalvelu.com` 404s** are a **thin** 404 — our production log reads
  `Structural: minimal_text on small page (148 bytes, 23 chars visible)`. That
  trips `is_blocked` (`antibot_detector.py:627-630`), so `success=False`, and the
  inference branch keeps the status and maps 404 → `origin_http_error`. Pinned by
  `test_failure_classification.py:567-578`.

So it is one mechanism producing two classes because the two events genuinely
differ: *"we rendered the origin's 404 page"* vs *"the origin's 404 gave us
nothing usable"*. **The ask back is small: store `success` and `error_message`
beside `class`** — that closes this permanently on their side. "Under-applied" is
also the wrong frame: there is no 404 class, and `none` means "did not fail".

**§5b — "a proxy failure was classed `origin_http_error`" is FALSE as diagnosed.**
That result carries `status_code=None` (`async_webcrawler.py:692`), so **no
status-based branch can fire** — `classify_result:429`'s `status >= 400` and the
`:376` fallthrough are both unreachable. The class came from `_NET_ERR_RE`'s
closed 7-member table of *origin-side* codes (`:142-154`). Proxy faults are **not**
folded in: `ERR_TUNNEL_` and `ERR_PROXY_` are in
`_NET_ORIGIN_UNREACHABLE_PREFIXES` (`:174-175`).

Also worth relaying: **`ACS-GOTO` and `All proxies failed` are upstream's own
labels, not proxy diagnostics** — `ACS-GOTO` marks the `page.goto` step
(`async_crawler_strategy.py:864`) and `All proxies failed` is upstream's wrapper
when its rotation loop exhausts, which with our single pinning proxy just means
"the attempt failed". And no patchright leg ran, because that gate needs the
block marker this text lacks (`aitosoft_patchright_fallback.py:163-175`).

**The one token that decides it was elided from their report: the actual
`net::ERR_*`.** Ask for it. If it turns out to be `ERR_EMPTY_RESPONSE`, then on
plain `http://` our own egress proxy closing without replying is the proximate
actor — deliberate, measured, and recorded in
`done/egress-proxy-blocks-the-event-loop.md:163-166` as strictly better than the
alternative. Even then the origin *family* is right and the wire behaviour is
identical (both classes are 200 + terminal), so "over-applied" overstates it.

**Two real test gaps this surfaced**, neither named in their report: nothing pins
the `status_code` *shape* a failed result carries (the exception path emits `0`,
the result path emits `null` — same class, two shapes, and this already cost MAS
two rows in `18-…`), and nothing walks the 404 fork end to end. A `fixture_origin`
404 route at two body sizes would pin the actual mechanism at zero live traffic.

## 5. `origin_blocked` is not IP-reputation decay

11 events / 5 domains. **Every one is a genuine origin 403 with its own distinct
block page**: `gatelesis.com` 117 B, `realservice.fi` 320 B, `amaaranen.fi`
357 B, `kea.fi` 1201 B, `k-rauta.fi` Cloudflare JS challenge.

Three things rule out decay, and it is worth recording *why* rather than just the
verdict, because this is the signal that would stop a sweep:

1. **Five distinct block-page shapes, not one shape spreading.** Reputation decay
   against our shared SNAT address would show the same interstitial recurring.
2. **The rate is flat** at 1–2 domains per 10-minute bin, and **zero in the final
   25 minutes**. Decay is monotonic.
3. **No host that succeeded earlier began failing.**

All 11 carry `status=403`, so none came from our inference tier — the "a block
verdict must carry *why*" separation is holding in production.

### MAS split it further, and their split needs one correction: `kea.fi` is not blocking us

`27-…` §6 re-requested each host from their own container (a different egress IP)
and concluded **"2 of 50 block you specifically"** — `gatelesis.com` and `kea.fi`.
**`kea.fi` does not.** Per-URL outcomes from our own logs:

| URL | our outcome |
|---|---|
| `http://kea.fi` | **SUCCESS** |
| `http://www.kea.fi` | **SUCCESS** |
| `http://www.kea.fi/butiker` | **SUCCESS** |
| `http://www.kea.fi/sv` | **SUCCESS** |
| `http://www.kea.fi/kontakt` | 403, 1201 B |
| `https://kea.fi`, `https://www.kea.fi` | `origin_unreachable` — **the site has no HTTPS** |

**We were served four pages by `kea.fi` over plain HTTP and 403'd on exactly one
path — `/kontakt`.** Their test almost certainly hit the homepage, which returns
200 to us too, so it compared their homepage against our contact page. A WAF rule
on a contact form is common and applies to everyone. The `https://` failures are a
third thing again, and their own table already records them separately under
`origin_unreachable`.

**So the corrected split is 1 of 50 (2 %), not 2 of 50 and not 5 of 50:**

| host | reading |
|---|---|
| `k-rauta.fi`, `amaaranen.fi` | 403 to both of us — **refuses everyone** |
| `realservice.fi` | 403 to us, no response to them — host-side, unresolved |
| **`gatelesis.com`** | 403 to us on all 3 URLs, 200 to them — **genuinely us** |
| ~~`kea.fi`~~ | **not blocked** — one path, plus no HTTPS |

**This matters operationally**, which is why it goes back promptly: MAS
**pre-registered** a stop rule — *"if segment 3 comes back at or above 2 in 50, we
stop the sweep"*. Pre-registering was exactly the right instinct, but the
threshold is built on a count that includes a host which serves us fine. Re-derive
it at **1 in 50** before segment 3, or the sweep stops on an artefact.

**And it is probably not a fingerprint.** For both `gatelesis.com` and
`kea.fi/kontakt` the **patchright leg ran and got the identical 403** — a
different engine with a different `navigator`/TLS fingerprint, from the same
egress IP. Same IP + different fingerprint → same answer points at **IP or path**,
not fingerprint. For `kea.fi` the four sibling successes from that same IP settle
it as *path*. For `gatelesis.com`, IP is the live hypothesis and
`residential-egress-retry-path.md` is the file that already prices the answer —
population floor 6 / ceiling 29, now measured at **1 in 50**.

**Segment-2 baseline for comparison against segment 3:** 11 events / 5 domains
gross, **1 domain us-specific (2 %)**, 2 refuse-everyone, 1 unresolved. Segment 1
was 0 of 25 by both instruments (re-derived from the same surface at MAS's
suggestion — their run log has zero 403 lines). The gross rise is real; the
us-specific part is where the decision lives.

---

## 5b. The click channel CAN be sized retrospectively — there was an upstream counter all along

`tasks/README.md` says neither repo can size the consent channels retrospectively,
because the element is deleted before either side's capture. **That is true of the
removal channels and false of the click channel**, and the instrument is upstream's
own log line, present in every image we have ever run:

```
Failed to remove consent popups: Page.evaluate: Execution context was destroyed,
most likely because of a navigation.
```

A Phase-1 click that navigates destroys the JS execution context, which is exactly
what that message reports. Counted over 30 days:

| date | revision | events |
|---|---|---:|
| 2026-07-16 | `--0000025` | 5 |
| 2026-07-17 | `--0000029` | 24 |
| 2026-07-29 / 30 | `--0000030` | 7 / 6 |
| 2026-07-31 | `--0000031` | 27 |
| 2026-08-05 | `--0000034` / `--0000036` | 1 / 5 |
| **2026-08-06 (segment 2)** | `--0000037` | **0** |

**75 events in 30 days**, and the 2026-08-05 five are traceable to hosts —
`st1ranua.fi` (4 URLs) and `energyplaza.vattenfall.fi` (1) — in segment 1's window.
**Those are pages MAS may have stored from the wrong URL**, and they can check:
they hold the capture and the requested URL. Worth asking, because it is the only
retrospective handle on this channel that exists.

**Do not over-read it.** The message also fires for an origin-initiated navigation
(meta-refresh, JS redirect), so 75 is a **ceiling** on our self-inflicted clicks,
not a count. And segment 2's zero is best read as *no destructive navigation on
this cohort*, **not** as an effect of the fix — the fix did not touch Phase 1.

**Our new counter is not blind here, and that was deliberate.** `url_before` is
captured outside the `try` and `_report_consent_pass` was moved out of it
(`async_crawler_strategy.py:1667-1681, 1711-1714`), precisely so `page.url` still
reports the navigation when the evaluate raises. So the two tokens are
complements: the upstream line says *the pass blew up*, ours says *the URL moved*.
Segment 2: 0 and 3 respectively, the 3 all fragment-only. **Count both.**

## 5c. The `<noscript>` collapse family looks genuinely fixed, and the arithmetic is now strong

`COLLAPSE RECOVERED` and `RENDER DEFECT` are both **0 across segment 1 (147) and
segment 2 (261) = 408 successful renders.** Against the 2026-08-01 measured rate of
9/328 = 2.74 %, P(0 in 408) ≈ **1.4 × 10⁻⁵**. That is no longer a "keep watching"
result — it is evidence the rate on current traffic is *not* 2.74 %.

The likeliest reason is the good one: `strip_noscript()` plus html2text recovery
removed the cause, so the guard correctly never fires. **Stop quoting 2.74 % as
the prior.** But keep running the two-token query per segment — it is one query and
it is the only tracking this family gets.

### The channel neither the guard nor the consent counter can see, and it is the one to close before scaling

The collapse guard compares **visible text in** against **markdown out**. A page
that renders with near-zero *visible text* — JS that never ran, an SPA that never
painted — produces near-zero of both, so the ratio looks healthy and **the guard
correctly does not fire while MAS receives an almost empty page at 200
`success:true`.** We log nothing about markdown length on success, so **from our
side this population is invisible by construction.**

MAS's own corpus says it is real and not small: of 41 companies whose stored pages
are all byte-identical, **26 have every page at 1 character** (`21-…` §2b, across
17,439 companies), and `27-…` §3 names `kiertopakkaus.fi` — reproduced 3½ months
apart, and **confirmed not Enfold**, so root-deletion does not explain it.

Their segment-2 size table (`27-…` §4) gives `markdown_raw` median 11 KB / p90
38 KB / max 73 KB — **but no minimum and no near-empty count.** That single number
is the most valuable thing to ask for before scaling, and the sharper request is:
**re-fetch a sample of the 36 known-empty companies on this image and report how
many are still empty.** Their corpus predates every fix we shipped; the delta is
the attribution, and it costs them one small run.

## 6. A correction to my own monitoring, because the artefact is reusable

Across two consecutive ticks I reported pool memory "creeping": window maximum
57.8 % → 60.3 % → 63.8 %. **That was an instrument artefact.** Window maxima over
overlapping windows is not a trend — a longer window can only ever contain a
larger maximum.

The 10-minute binned view shows it oscillating with load and falling as traffic
drained: 26.5 → 57.8 → 48.5 → 60.3 → 63.8 → 52.8 → 25.3 %. Peak 63.8 % against
an 85 % guard, pool `hot` never above 2, and browsers reaped cleanly to 0
replicas after the last render. **Nothing was leaking.**

Same lesson this repo already records for the browsers→memory regression: choose
the instrument before reading the trend. Two ticks of a wrong instrument produced
a "number moving in the wrong direction" that did not exist.

---

## What I am least sure of

- **Whether 4.9 % of domains generalises.** Three domains is a small numerator,
  and Finnish SME sites are Enfold-heavy in a way another cohort may not be.
- **It sits awkwardly against "2 hosts in 30 days"** (13 after that file's own
  undercount correction). Three Enfold domains in one 58-minute segment against
  13 hosts in 30 days is a tension I did **not** reconcile, and the two
  instruments measure at different points (removal vs outcome). Someone should
  count it twice before this 4.9 % is quoted anywhere load-bearing.
- **`nieminen.lol`'s 83 bytes being a parked page is an inference** from the byte
  count and the TLD. I did not fetch it.
- **The `delotec.fi` mechanism, entirely.**
- ~~I did not reconcile the two repos' accounting.~~ **Done, and it closes to the
  request** — see the correction banner at the top. Both instruments are sound;
  the one error was mine and it was a token/field confusion, not a measurement.
- **Whether `gatelesis.com` is IP or fingerprint.** The patchright leg getting the
  identical 403 from the same egress points at IP, but that is an inference from
  one host. A single request from the dev container's residential address would
  settle it — and `PRIVATE.md` is explicit that burning that address burns the
  owner's home connection, so it is one request, logged, or nothing.
- **Whether segment 2's zero destructive navigations means anything.** The fix did
  not touch Phase 1, so I read it as cohort. 75 events in 30 days says the channel
  is not dormant.
- **Whether the near-empty-success population (§5c) overlaps the `<noscript>`
  family or is a distinct mechanism.** `kiertopakkaus.fi` not being Enfold rules
  out one cause, not the others.

---

## 8. Are we ready to scale? Yes — and the reason is structural, not a hope

**The premise both repos were carrying was wrong, and correcting it is what makes
this answerable.** `27-…` §8: MAS's `--concurrency 2` limits **companies**, not
render requests. Each company's agent fetches pages **in parallel** — up to 4 at
once, and **37 of 50 companies (74 %) issued ≥2 simultaneous fetches**. Peak in
flight was **7** (segment 1: 6). Our own 429 confirms it to the request: at
13:47:16.289Z their trace shows 7 in flight; 465 ms later we answered
`2/2 rendering, 4 queued` and rejected one. **6 at the replica + 1 rejected = 7.**
Our documents said a 429 was impossible at concurrency 2; one cold replica is
2 slots + 4 queue = 6, and they can present 7.

**The consequence is the good news: the in-flight ceiling is set by their
concurrency flag times per-company fan-out (~2 × 4 = 8) and does NOT grow with
cohort size.** 50 companies or 15,000, at `--concurrency 2` the peak stays ~8.
Scaling the cohort buys duration, not concurrency.

| | |
|---|---|
| Peak concurrent renders observed | **7** |
| One cold replica absorbs | 2 rendering + 4 queued = **6** |
| Fleet capacity | `render_capacity: 2` × `maxReplicas: 30` = **60 concurrent** |
| **Headroom on their concurrency flag** | **~7–8×** — they could run ~15 companies at once before approaching 60 |
| Hard wall | `maxReplicas: 30`, then 429s that are real |

**The one 429 is a cold-start artefact and MAS proved it with a within-run
control**: they crossed 5 concurrent **ten** times; the **three inside the first
minute** produced the single 429, the **seven after we had scaled** produced none.
Same process, same flag, same fan-out — the only variable is replica warmth. They
explicitly are not asking us to widen anything. If a segment-start 429 ever becomes
unwelcome, the lever is `minReplicas: 1` for the sweep window — a scale setting,
**not** `--set-env-vars`, so it carries no token risk.

**Nothing lost data in this run.** 209 pages stored, the rejected page succeeded
19.3 s later, every failure class landed on the correct wire status, and the two
repos reconcile request-by-request. The capacity and memory families are now at
**zero across four consecutive workloads**.

**What scaling multiplies, from this run's measured rates** (×300 for a
15,000-company sweep):

| | this run | ×300 | costs what |
|---|---|---|---|
| Dead domains (`origin_unreachable`) | 13 of 50 companies | ~3,900 companies | **~nothing** — no render slot, no browser, 200 |
| `origin_blocked` gross | 5 of 50 | ~1,500 | mostly the origin's choice |
| **`origin_blocked`, us-specific** | **1 of 50 (2 %)** | **~300 companies** | genuinely lost pages |
| **`render_error` 500s** | **12 of 274 requests (4.4 %)** | ~3,600 requests | **~30 render-hours, and it is 3 URLs' worth of terminal outcomes inflated 4× by retries** |
| `render_defect` | 2 of 274 | ~600 requests | ~21 render-hours, ~half of it a guaranteed-fail 30 s wait |

**So the honest verdict: scale now, and do items 6 and 7 first because they are
small, not because they block.** Together they remove **~3.3 % of total request
volume** (9 of 274 requests here were retries of 3 permanently-failing outcomes)
and ~40 render-hours per 15,000 companies. Neither loses data; both are cost
hygiene that gets 300× more expensive if deferred.

**The only genuine unknown before a large sweep is §5c's near-empty-success
population**, and it is *measurable on MAS's side today* — one number (the minimum
and near-empty count of `markdown_raw`) plus one small re-fetch of their 36
known-empty companies. That is worth having before 15,000 companies, and it does
not gate 500.

### The number that will actually bind, and the cheap lever nobody has priced

Segment 2 did 50 companies in 49m49s at `--concurrency 2` ≈ **1 company/minute**.
Straight-lined, **15,000 companies is ~249 hours — 10.4 days.** MAS will therefore
want to raise the flag, and that is the axis where our ceiling lives:

| their `--concurrency` | peak concurrent renders (≈ flag × 4) | replicas needed (÷2) | vs `maxReplicas: 30` | sweep duration |
|---:|---:|---:|---|---:|
| 2 | ~8 | 4 | fine | ~10 days |
| **15** | **~60** | **30** | **exactly at the wall** | ~1.7 days |
| 25 | ~100 | 50 | **sustained 429s** | ~20 h |

Verified against Azure, not docs: `minReplicas: 0`, `maxReplicas: 30`, scale rule
`http-renders` at `concurrentRequests: 2`, matching `render_capacity: 2`. Fleet
ceiling **60 concurrent renders**. The 2-rendering-plus-4-queued arithmetic behind
the cold-start 429 is confirmed by MAS quoting our own 429 body.

**So: `--concurrency` up to ~15 is free. Above that, the lever is `maxReplicas`,
and it is cheap in a way nothing has checked.** Raising it is a **scale setting**,
not `--set-env-vars`, so it carries no token risk; and with `minReplicas: 0` a
higher cap **costs nothing while idle** — this environment already scales to zero
between segments. Consumption environments allow far more than 30, so this is
plausibly a one-command change that unlocks a sub-day sweep.

**Do not build anything for this. Check the cheap lever first** — one
`az containerapp update --max-replicas <n>` and one look at whether it is accepted,
exactly as `CLAUDE.md` principle 7 demands after the `--memory 8.0Gi` note turned
out never to have been a valid command. **Verify it before quoting it.**

## 9. The consent history, dug out because "have we solved this before?" was worth asking

Asked by the owner, who remembered extensive Cookiebot experimentation on
`accountor.com` months ago and wanted to know whether it had regressed and
whether we had been reinventing upstream. Both halves have answers, and one of
them **falsified a row in CLAUDE.md that had stood for six months.**

**Nothing regressed. Accountor has passed Tier 1 4/4 on every run since
2026-04-11**, last verified 2026-08-06 07:37 pre-deploy: 8,802 tokens, 35,208
chars, 1/1 contacts, `failure_class: "none"`. Token history is monotonic-ish and
boring, which is the good outcome: 31 (Jan, broken) → 8,149 (Apr) → 8,802 (today).

**But the January diagnosis was wrong, and the record carried it forward.** The
symptom — 31 tokens, `html` 99,649 B → `cleaned_html` 230 B — was attributed to
Cookiebot. The stored January captures in `test-aitosoft/artifacts/` say otherwise:

- The surviving 7,805 B body carries
  `style="margin-right: 0px; padding-right: 0px; overflow: auto;"` — **the exact
  triple `remove_overlay_elements.js:150-153` writes at the end of its run, and
  nothing else in the codebase writes it.**
- Surviving tags: `{iframe: 3, noscript: 1, script: 75, ul: 1, img: 1}` — **zero
  content elements.** A cookie wall overlays a page; it does not delete every
  `<div>`.
- `heavy` used `networkidle`, so timing is excluded — same 7,805 B either way.

**Why it went unnoticed for six months: the control shared the suspected cause.**
All five January presets set `remove_overlay_elements: True` — *including
`minimal`, the control*. No arm of the harness could have revealed the flag. So a
workaround ("turn it off") got recorded as a diagnosis, and the actual mechanism —
`getComputedStyle().backgroundColor` being the literal string `rgba(0, 0, 0, 0)`,
making `.includes("rgba")` always true and degenerating the rule to *remove every
visible fixed-or-absolute element* — was only named on **2026-08-06, 6.5 months
later**. This is the third instance of the same failure this repo has recorded
(`/block/padded-403`, the 280×160 overlay fixture) and the first where it hit the
**control**: *a control that shares the suspected cause is not a control.*

**Did we reinvent upstream's work? Three instances, and the honest reading is not
the obvious one.**

1. On 2026-01-24 we hand-wrote four Cookiebot/OneTrust/Cookieyes clickers.
   Upstream shipped `remove_consent_popups` **18 days later** (`3fc7730`,
   2026-02-11, first released in v0.8.5) containing **all four of our selectors
   verbatim** among its 86. But the flag did not exist when we wrote ours — so
   this is "we solved it three weeks early and then correctly threw ours away",
   not avoidable duplication.
2. `magic`'s worst mechanism — `mouse.down()/up()` at fixed coords (100,100) plus
   `keyboard.press("ArrowDown")` on *every* page — was **an upstream bug upstream
   fixed for us** on 2026-02-19 (`c854e2b`), for precisely our reason. We filed
   nothing; it arrived in the v0.8.6 merge.
3. **The real lesson runs the other way.** Having adopted the upstream flag, we
   then inherited **140 unaudited selectors**, one of which deleted whole documents
   for months. "Check whether upstream already solved it" is right; **"and then
   read what you adopted" is the half we skipped**, and it cost more than the
   duplication would have.

**The load-bearing correction: `remove_consent_popups` is not what fixed
accountor, and may do no work there at all.** No `CybotCookiebotDialog`
*element* exists in any successful accountor capture (the 1,112 string hits in
April are Cookiebot's own script/CSS text); `evästeet` appears 0 times in today's
markdown; the pre-deploy readout recorded **zero generic matches** on it; and the
2026-01-24 run that unblocked the site (14,492 tokens) predates the flag entirely.
What fixed accountor was turning **`magic` and `remove_overlay_elements` off**.
**One request with `remove_consent_popups: false` settles it** — Tier 1 host, not
burned, and it is the cheapest open question we have.

**Four documentation claims about `magic` were false and dangerous in the
permissive direction.** CLAUDE.md, `TESTING.md:25-26,215`,
`TEST_SITES_REGISTRY.md:74` and `test_site.py:46-48` all said the server rejects
`magic`. **It does not** — our own `aitosoft_trust.py:44-49` un-forbids `magic`,
`simulate_user` and `override_navigator`, and `:51-63` drops falsy forbidden
fields rather than rejecting them. Verified 2026-08-06 by *executing*
`apply_trust_relaxations()` and printing the sets, not by reading. A session could
have sent `magic: true` trusting the boundary to stop it; January is what that
does to a page. **Fixed in CLAUDE.md, TESTING.md and TEST_SITES_REGISTRY.md**;
`test_site.py:46-48` is left for whoever next touches that file, with this as the
reason. Related stale claims found in the same sweep: `AITOSOFT_CHANGES.md:463`
says "122 named" selectors against `:438`'s corrected 120, and `TESTING.md:222`
still describes dead domains as an SSRF 400.

**Relay gap worth telling Tero: `tmp/mas-repo-messages/` has no 25 or 26.**
`27-…` cites both (§5c and §8). We have 07–24 and 27. Given this repo's history —
message 14 sat unread for two days over a numbering mismatch — this should be
chased rather than assumed benign.

## Follow-ups this created

### Code, ours — do before a large sweep because they are small, not because they block

1. **`render_error` must not be a retryable 500 when the origin served a
   non-page.** 100 % of this sweep's 500s; removes ~3.3 % of total request volume
   and ~30 render-hours per 15,000 companies. Two shapes: a PDF Chromium renders
   in its own viewer (unambiguous — `unrenderable_content`), and an 83-byte page
   at HTTP 200 (genuinely ambiguous; decide deliberately). **The axis is
   permanence, not ownership** — do *not* loosen the inference tier's byte bounds.
2. **The patchright tier must skip classes already known permanent.**
   `_is_blocked` (`aitosoft_patchright_fallback.py:163`) matches the block-marker
   *string*, so `render_defect` — already in `NON_RETRYABLE_CLASSES` — still gets
   a retry leg, which then waits 30 s on `wait_for_selector("body")`: exactly the
   element whose absence defined the failure. A few lines.
3. **Two log holes** (§4b): static-mode failed fetches carry no `failure_class`
   (~6 lines), and `api.py:1198`'s `failed_result` omits `render_mode` so a static
   request to a dead domain is reported as `"full"` (one word, and MAS parses it).
4. **Strip the fragment before the `CONSENT NAVIGATION` comparison** (§2). Three
   false positives; fold into any of the above.

### To MAS — three corrections and three asks

5. **Correct their §6 before segment 3.** `kea.fi` is not blocking us: four
   successful pages, one 403 path, no HTTPS. Us-specific is **1 of 50, not 2** —
   and they pre-registered a stop rule at ≥2 in 50, so the threshold needs
   re-deriving or the sweep stops on an artefact. (§5)
6. **§5a is our documented correct behaviour, not an inconsistency.** The
   discriminator is `success`, not the host, and it is already on the wire. Ask
   them to store `success` and `error_message` beside `class`. **§5b is false as
   diagnosed** — that result carries `status_code=None`, so no status branch can
   fire. Ask for the untruncated `net::ERR_*`; it is the one token that decides it.
   (§4c)
7. **Send them the proof they asked for** — `done/consent-scripts-delete-the-page.md`
   already reproduces all four shapes through the browser, plus `kubler.fi` at
   15 bytes → 55,545 chars. Optionally add the `raw://` A/B against `--0000036`
   (~11 min, zero egress) as a corpus-free artefact for the upstream PR. (§1)
8. **Ask for the `markdown_raw` minimum and near-empty count**, and for a re-fetch
   of a sample of their **36 known-empty companies** on this image. This is the
   only silent-loss channel neither our guard nor our counter can see, and it is
   the one genuine unknown before a large sweep. (§5c)
9. **Ask whether `st1ranua.fi` and `energyplaza.vattenfall.fi` stored the wrong
   page** in segment 1 — the only retrospective handle on the click channel. (§5b)

### Docs, done in this session

10. **`OVERNIGHT_PLAYBOOK.md`: three fixes.** The `ContainerAppHTTPLogs` column
    names were wrong (the table is unsuffixed: `StatusCode`, `ReplicaName`,
    `RequestDuration` in ms, `ContainerAppName`). The "count from `RESULT FAILURE`,
    not ORIGIN-FAIL" row **caused the 57 % undercount in this file's first draft**
    and is replaced with "key on `failure_class=`, never on the token", plus the
    ingress-minus-admits cross-check. And a warning never to read a memory trend
    off per-tick window maxima.

**Nothing was done to the running service, and nothing needed to be.**
