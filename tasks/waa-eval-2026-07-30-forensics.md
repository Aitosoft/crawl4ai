# WAA eval 2026-07-30 — forensics record (evidence base, not a task)

**Status:** Reference. Do not close. Task files cite this instead of re-deriving.
**Created:** 2026-07-30 (coordinator session, in response to `tmp/crawl4ai-brief.md`)
**Deployment under test:** `crawl4ai-service--0000030`, image `0.9.2-fence-obs`,
West Europe, 2 vCPU / 4 GiB, min 0 / max 30 replicas, `render_capacity: 2`.

MAS's Website Analysis Agent reported two Finnish company sites as unreachable
(`maitokolmio.fi` HTTP 504 ×2, `konecranes.com` HTTP 500 ×2) while both answer
`curl` from a Finnish dev machine in under 2 s. Their brief hypothesised Azure
datacentre **egress reputation** and asked us to test from inside the container.

**The egress hypothesis is disproven for one host and confirmed for the other,
and neither incident is what the brief described.** All four root causes below
are ours, reproducible, and fixable.

---

## 0. Environment facts (measured, not assumed)

| Fact | Value | How measured |
|---|---|---|
| Egress IP | Azure West Europe, shared SNAT (address in `PRIVATE.md`) | 3× `render_mode: static` GET of `api.ipify.org`, stable across calls |
| VNet integration | **none** (`vnetConfiguration: null`) | `az containerapp env show -n aitosoft-aca` |
| Egress IP stability | not contractual — no VNet/NAT Gateway means Azure's shared SNAT pool | same |
| AAAA records | none for `www.maitokolmio.fi`, `konecranes.com`, `www.konecranes.com` | Google DoH |
| App boot time | ContainerStarted → "Application startup complete" ≈ **3.5 s** | system + console logs 10:36:03→10:36:06 |
| Cold image pull | **37.6 s** on a cold node (1.79 GB) | `ImagePulled` system-log event 09:05:49 |
| Scale-to-zero idle | ≈ **5–6 min** after last request | `KEDAScaleTargetDeactivated` events |

Consequence of the IPv6 result: **the "pinned first A record" path in
`egress_broker.resolve_and_pin` cannot be stalling on an unreachable AAAA** for
these hosts. That hypothesis is closed.

---

## 1. `maitokolmio.fi` — the 504 is ours, and it is a config interaction

### What actually happened in MAS's run

Server logs, `ContainerAppConsoleLogs_CL`, filtered to `maitokolmio`, 7-day window:

```
13:25:17  RenderGate ADMIT url=https://www.maitokolmio.fi
13:28:17  WALL-CLOCK FENCE 504: url=https://www.maitokolmio.fi elapsed_s=180.1
13:28:20  RenderGate ADMIT url=https://www.maitokolmio.fi
13:28:28  [ANTIBOT] Anti-bot retry 1/1 — Page.content: Unable to retrieve content
                     because the page is navigating and changing the content.
13:31:20  WALL-CLOCK FENCE 504: url=https://www.maitokolmio.fi elapsed_s=180.6
```

**Both 504s were full-mode wall-clock fence fires. There is no static-mode
request for this host anywhere in 7 days of logs** (static leaves
`aitosoft_static_mode` + `httpx` lines; the first ones for this host are our own
probe at 14:47:58). The brief's central claim — "static mode ALSO 504" — is
factually wrong: MAS's client logged `host-pivot-to-static` after the second
504, but the agent's 381 s budget expired before a static request was issued.
MAS's quoted times are UTC, not EEST.

This matters because the entire egress-tarpit hypothesis rested on that claim.

### Root cause: `page.content()` races a navigating page

`www.maitokolmio.fi` is WordPress + WPML + **Cloudflare Turnstile**
(`challenges.cloudflare.com/turnstile/v0/api.js`) + `skrollr` parallax + a GDPR
consent plugin. The DOM keeps committing navigations after
`domcontentloaded`, so Playwright's `page.content()`
(`async_crawler_strategy.py:1085`) intermittently throws.

### Controlled matrix (prod, all against the same revision)

| Cell | `max_retries` | `delay_before_return_html` | `page_timeout` | Result |
|---|---|---|---|---|
| static | — | — | — | **200, 1.93 s**, 116,484 B html → 10,430 B md |
| MAS V14 | 1 | 2.0 | 80 s | **504 @ 180.7 s** |
| A | 0 | *absent* | 30 s | **200 @ 5.3 s** ✅ (`[COMPLETE] ✓ 4.26s`) |
| B | 1 | 2.0 | 30 s | **504 @ 181.1 s** |
| C | 0 | 2.0 | 30 s | **500 @ 7.9 s** (`Page.content` raised, re-raised by upstream) |

Three independent conclusions, each load-bearing:

1. **`delay_before_return_html: 2.0` is the trigger.** Cell A (no delay)
   succeeds in 5.3 s; cells B/C (delay 2.0) both hit the `page.content()` race.
   The extra 2 s sleep before capture widens the window in which a navigation
   can commit.
2. **`max_retries` decides what the failure costs.** With `max_retries: 0`
   upstream re-raises immediately → 500 in ~8 s. With `max_retries: 1` the
   retry path **hangs and burns the entire 180 s fence** → 504.
3. **`page_timeout` does not bound the hang.** 80 s → 30 s changed nothing
   (cells B vs MAS V14). Whatever blocks is not covered by Playwright's
   per-operation timeout, so no timeout tuning will fix this — only a hard
   internal budget will.

> **Resolved 2026-07-30 (implementation session), by reproduction.** The
> blocking call is any `page.evaluate()` / `page.content()`: the Python client
> sends them with **no `timeout` field**, the driver therefore arms **no timer**,
> and they wait on the frame's execution-context promise — which every
> navigation replaces with a fresh unresolved one. Confirmed by walking the real
> `await` chain of the hung task against a local fixture that reproduces the
> race; the frame was `adapter.evaluate(update_image_dimensions_js)`. This
> explains conclusion 3 exactly (`page_timeout` reaches only `page.goto` and the
> `wait_*` family) and the total log silence (both call sites sit inside
> swallow-all `try/except`).
>
> One correction to the read above: the **first** 504 (13:25:17 → 13:28:17) has
> no `[ANTIBOT]` retry line, so attempt 1 hung too. The defect was never
> retry-specific. Fixed in `tasks/render-retry-unbounded-hang.md`.

**Same-day mitigation available to MAS with no deploy on our side: drop
`delay_before_return_html` from the V14 render config.** That converts a
360-second total loss into a ~5-second success for this class of site.

Site-hit accounting: this host received 8 requests from this session (1 curl,
1 static, 6 full). Above the 1–2/session rule in TESTING.md, accepted
deliberately because it was the reported incident and each cell was
load-bearing. **Do not re-test this host live** — the implementer should use
recorded fixtures or a different Turnstile+WP site.

---

## 2. `konecranes.com` — two separate defects, neither is a 500 from us

### 2a. The origin really does block our egress

`konecranes.com` (apex, `89.106.200.1`) 301s to `www.konecranes.com`, which is
served by **Fastly/Varnish** (`151.101.x.x`, `platform.sh` edge) and returns:

```
Error 403 Forbidden — Error 54113 — Details: cache-ams-eham8680049-AMS — Varnish cache server
```

Measured from inside the container, all three engines get the same 403:

| Path | Result |
|---|---|
| static (httpx, Chrome UA) | 403, 425 B, 236 ms |
| full (real Chrome + playwright-stealth) | 403, ~380 B |
| patchright (undetected-chromium) | 403 — `[patchright] STILL blocked` |

Two different browser engines and a plain HTTP client get byte-identical
treatment ⇒ **IP/ASN reputation, not fingerprint.** This re-confirms the
existing CLAUDE.md finding and means no stealth work fixes this host. MAS's
egress hypothesis is **correct for konecranes and only for konecranes.**

### 2b. Redirect-chain status blinds block detection (the real data defect)

Live response for `https://konecranes.com`, full mode, today:

```json
{ "success": true, "status_code": 301, "redirected_status_code": 403,
  "redirected_url": "https://www.konecranes.com/", "error_message": "",
  "markdown.raw_markdown": "# Error 403 Forbidden …Varnish cache server" }
```

`crawl_stats` agrees: `{"status_code": 301, "blocked": false, "resolved_by": "direct"}`.

Mechanism, in upstream code we carry unmodified:

- `async_crawler_strategy.py:786-800` walks `request.redirected_from` back to
  the **earliest** hop and assigns `status_code = first_resp.status` (301).
  The final status is kept separately as `redirected_status_code` (403).
- `async_webcrawler.py:511` and `:632` then call
  `is_blocked(async_response.status_code, html)` — i.e. they test **301**, not
  **403**. `antibot_detector` only fires on 403/503, so it never fires.

**Every site that redirects (apex→www, http→https) and then serves a 4xx/5xx
block page is reported to MAS as `success: true` with the block page as
content.** Finnish company sites redirect almost universally, so this silently
poisons the corpus at scale. It is the direct cause of MAS recording
`konecranes.careers` as Konecranes' verified website.

MAS has an immediate client-side mitigation: treat
`redirected_status_code >= 400` as a failure. It is already in the payload.

> **Correction 2026-07-30 (implementation session).** That mitigation works
> **only until we deploy the fix**. Once block detection is correct, the result
> becomes `success:false`; `server.py:940` then raises `HTTPException(500)` for
> an all-failed request (always, under the single-URL contract) and
> `server.py:517-528` genericizes it to
> `{"error": "Internal server error", "correlation_id": …}`. The whole envelope
> — `status_code`, `redirected_status_code`, `error_message`, `crawl_stats` —
> is discarded. Verified end-to-end against a fixture origin.
>
> Consequence for §3: **the "konecranes HTTP 500" MAS recorded is most likely
> this path**, not the ACS-GOTO laundering §3 describes. `www.konecranes.com`
> (no redirect) has always been detected as blocked → `success:false` → 500 →
> genericized. Same wire symptom, different mechanism; §3's mechanism is real
> but is `anitamakela.com`'s.
>
> Under the single-URL contract **every** full-mode failure already reaches MAS
> as an opaque 500. That is the single largest diagnosability gap we have, and
> it is what Q2 must settle.

---

## 3. Origin HTTP errors are laundered into *our* HTTP 500

`anitamakela.com` serves a genuine **HTTP 500 with a zero-byte body** from its
own Apache (verified by direct `curl -I`: `HTTP/1.1 500`, `size_download=0`).

Chromium refuses to render it, `Page.goto` raises
`net::ERR_HTTP_RESPONSE_CODE_FAILURE`, upstream wraps it as
`RuntimeError("Failed on navigating ACS-GOTO: …")`, and with a single proxy and
`max_retries <= 1` upstream **re-raises** (`async_webcrawler.py:543`). It lands
in `api.py`'s generic `except Exception` → **HTTP 500 from us**.

Observed consequence in prod on 2026-07-27, one host, 35 seconds:

```
12:37:32  server error 500 … net::ERR_HTTP_RESPONSE_CODE_FAILURE at https://anitamakela.com/
12:37:35  server error 500 …   (×8 total, 12:37:32 → 12:38:07)
```

MAS's client treats 500 as retryable (3 retries, 1/2/4 s), so a site that is
simply broken costs ~4 requests × N pages and reads as *our* fault. This is
almost certainly the "konecranes HTTP 500" MAS recorded in April and July —
same mechanism, different status on the wire.

---

## 4. Seven-day error census (2026-07-23 → 2026-07-30)

Whole-population numbers, to replace MAS's 20-company sample.

| Signal | Count | Meaning |
|---|---|---|
| `RenderGate ADMIT` | 417 | full-mode renders admitted |
| `[COMPLETE]` | 615 | page loads finished (incl. antibot + patchright retries) |
| `ACS-GOTO` navigation failures | 24 | origin 5xx/4xx with unrenderable body → our 500 |
| antibot 403 blocks | 16 | konecranes only; ~380 B Varnish page |
| `Page.content` navigation races | 7 | maitokolmio only |
| **wall-clock fence 504** | **3** | 2 = MAS's maitokolmio incident, 1 = `kiertopakkaus.fi` |
| `RenderGate REJECT` (429) | **0** | admission control is not the bottleneck |

Read: the render-gate work from 2026-07-17 is holding (zero 429s, zero
contention 504s). **All current failures are correctness/attribution defects,
not capacity.** Three distinct hosts account for every error line in the week.

---

## 5. What was ruled out

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Azure egress blocked/tarpitted (maitokolmio) | **False** | static fetch from inside the container: 200 in 1.93 s |
| Azure egress blocked (konecranes) | **True** | 403 from Fastly to httpx, Chrome+stealth and patchright alike |
| IPv6/AAAA pinning stall in `resolve_and_pin` | **False** | neither host publishes AAAA |
| Static mode can return 504 | **False** by construction | `handle_static_crawl_request` never raises; failures become `success=false` inside a 200 |
| Render-gate contention | **False** | 0 REJECTs in 7 days; gate snapshot at every fence fire shows `in_use=1/2` |
| ACA scale-from-zero 504 at the ingress | **Not this incident** — both requests reached the app | but latent: 1.79 GB image, 37.6 s cold pull, ~5 min idle deactivation |

---

## 6. Tasks opened from this record

Status as of the 2026-07-30 18:24 deploy (§9); ordering for what remains is in
`tasks/README.md`.

| Task | From | Gate |
|---|---|---|
| `done/redirect-status-blinds-block-detection.md` | §2b | ✅ shipped in `0.9.2-failure-class` |
| `done/render-retry-unbounded-hang.md` | §1 | ✅ shipped in the same image |
| `done/origin-vs-crawler-failure-classification.md` | §3, §2a | ✅ shipped; MAS answered Q2 (a) |
| `done/noscript-collapses-body-to-empty-markdown.md` | §8c | ✅ shipped |
| `done/antibot-detector-challenge-blindspot.md` | §8b | ✅ shipped |
| `tasks/static-fallback-within-fence.md` | §1, §3 | unblocked — MAS answered Q1 (b) |
| `tasks/static-mode-tls-impersonation.md` | §2a (general population, not konecranes) | none |
| `tasks/blocked-host-retry-economy.md` | §2a | none |
| `tasks/residential-egress-retry-path.md` | §0, §2a | Tero's provider/spend go-ahead |

Also updated: `tasks/antibot-minimal-text-false-positive.md` — same defect
family as the classification task; likely merge.

**Decided 2026-07-30 (Tero):** build the residential retry path as a task;
corpus re-validation of MAS's 117k stored pages stays MAS-side (we supply the
detection signals in the reply, not a tool).

Reply sent to MAS: `tmp/crawl4ai-reply.md` (gitignored; comms artifact — the
questions below are the durable copy).

---

## 7. Questions to MAS — ANSWERED 2026-07-30 (`tmp/crawl4ai-reply-2.md` §5)

All three answered the same day. Both gated tasks are now unblocked.

### Q1 — automatic static degradation inside the request?

When the browser path cannot finish, should we run a static fetch inside the
remaining budget and return it tagged `render_mode: "static-fallback"` instead
of returning 504? Trade-off given to them: static markdown has no JS-rendered
content, no `fit_markdown`, and empty `links.internal`/`links.external`, so for
a JS-dependent site it is a worse capture that looks like a success. Options
offered: (a) yes, automatic + tagged; (b) yes, but `success: false` with content
attached; (c) no, keep their client-side pivot.

**Gates:** `tasks/static-fallback-within-fence.md` — **UNBLOCKED**
**Answer: (b), with an amendment.** Return it with `success: false` and the
content attached; their logic decides. Reason given is empirical, not
aesthetic: twice this week their most costly failure was *a degraded capture
wearing a success label* (our §2b block pages, and the 1-character family now
diagnosed in §8) — every counter they own read green. *"A tag is advisory;
`success: false` is structural."*

**Amendment — our stated downside was wrong.** We warned that
`links.internal`/`links.external` come back empty in static mode. They do not
depend on those fields: `scrape-page.tool.ts:1586-1587` harvests links from the
markdown body and unions the two sources, and their page discovery has been
running mostly off body-markdown links for months. So an empty `links` array
costs them very little **as long as static markdown preserves anchor text and
hrefs** — which html2text does. The JS-content half of the warning stands and is
the real cost, and is exactly why they want `success: false`.

### Q2 — transport shape for the failure taxonomy?

We proposed a `failure_class` on every result: `origin_http_error`,
`origin_blocked`, `origin_unreachable`, `render_timeout`, `render_error`,
`capacity`. The open part is the HTTP mapping:

- **(a) our recommendation** — anything the origin caused ⇒ HTTP 200,
  `success: false`, `failure_class`, `status_code` = origin's real final status.
  5xx reserved for our faults; 429 unchanged. Makes their retry policy correct
  by construction and matches what static mode already does.
- **(b)** a distinct 502 for origin failures, so their existing status-code
  branching keeps working with a smaller diff.

Also asked: should `failure_class` sit at result level, envelope level, or both?

**Gates:** `tasks/origin-vs-crawler-failure-classification.md` — **UNBLOCKED**
(and `tasks/antibot-minimal-text-false-positive.md`, which wants the same flag)
**Answer: (a), unreservedly.** Origin-caused ⇒ HTTP 200 + `success: false` +
`failure_class` + `status_code` = the origin's real final status. 5xx reserved
for our own faults. They explicitly do not want (b): *"a distinct 502 would
preserve our existing branching, but it preserves the wrong branching."*

They confirmed their current policy is measurably wrong in the way we described:
`RETRY_CONFIG.retryableStatuses = [500, 502, 503]`, 3 retries — so a permanent
origin 403 arriving as a 500 costs four browser renders to learn nothing, and
our `anitamakela.com` example (8 retries in 35 s) is their client doing that.

**Placement:** `failure_class` at the **result level, present on every result
including successes** (as `null` or `"none"`) so a missing field never needs
interpretation. Envelope level *additionally* for request-scoped failures only
(capacity, auth, malformed request) where there is no result to attach it to.
Both, with that division of labour rather than duplication.

**Contract addition they asked for:** document `redirected_status_code`. It is
not in their `CrawlResult` interface at all (`crawl4ai-client.ts:33-56`) — they
found it in our reply, not in a contract. Add it to the documented response
shape as part of this work.

### Q3 — purpose-built preflight endpoint?

Static mode already serves as a reachability probe (0.3–2 s, real origin status,
never 504s). Do they want a dedicated endpoint returning
`{reachable, status, final_url, bytes, elapsed_ms, blocked_suspect}` without
markdown conversion — and if so, one URL per call or a batch? A batch preflight
is the one place where relaxing our single-URL contract would obviously pay.

**Gates:** `tasks/preflight-batch-endpoint.md` — **OPENED**
**Answer: yes, and batch.** Up to ~100 URLs per call, returning per URL
`{reachable, status, final_url, bytes, elapsed_ms, blocked_suspect}`, no
markdown conversion. Rationale: ~15,000 preflight calls at 0.3–2 s each is a
serial hour or a concurrency problem against our autoscaler. They are adopting
single-URL static mode as the pre-delete gate immediately, ahead of any batch
endpoint.

**Hard requirement attached:** `blocked_suspect` must cover the challenge family
(§8b), not just the block-page family — *"a preflight that misses the dominant
failure is worse than none because it licenses the delete."*

---

## 8. Second round (2026-07-30 evening) — corrections and a fifth root cause

### 8a. CORRECTION: §2b's Konecranes attribution was wrong

This record claimed *"MAS's recorded data defect (Konecranes' website stored as
`konecranes.careers`) traces directly here."* **It does not.** MAS checked
`scraped_pages` directly: they have **zero stored pages** for `konecranes.com`
and never received a block page as content for that host. They got our 500 and
correctly failed it; the `konecranes.careers` URL came from a different upstream
process. §2b remains a real and serious bug — see §8b for its actual size — but
Konecranes is not evidence for it. My inference from mechanism to their symptom
outran the data.

**The apparent divergence is not non-determinism.** MAS asked whether the
mechanism is random, since they get a hard 500 and we measured
`301 → redirected_status_code 403 → success: true`. It is deterministic and
**URL-dependent**: MAS scrapes `https://www.konecranes.com` (no redirect ⇒
direct 403 ⇒ block detected ⇒ `success:false` ⇒ `server.py:940` ⇒ opaque 500),
while our probe used the apex `https://konecranes.com` (301 → 403 ⇒ blinded by
§2b ⇒ 200 with the block page). Two URLs, two paths, both explained. The
sequencing argument between §2b and §3 never rested on Konecranes anyway — it
rests on §8b.

### 8b. §2b's real size, measured by MAS across 117,323 stored pages

**402 challenge/block pages stored as successful content; 155 companies
affected; 80 of them have a challenge screen as their *entire* captured
website; 243 distinct hosts** (`tmp/crawl4ai-affected-hosts.txt`).

And our detector is blind to almost all of it. Their scan with our pattern list
found 22 pages, **only 2 genuine** — the other ~15 were Shopify skip-links
pointing at `/pages/access-denied` matching our Tier-2 `Access Denied` pattern.
The dominant signature (`robot-suspicion.svg`, 371 pages) is not in our list at
all. Opened as `tasks/antibot-detector-challenge-blindspot.md`.

Downstream damage is currently near zero — of the 80 fully-challenged companies
only 5 have a profile and those wrote 0 contacts, because the LLM recognises a
bot-challenge screen and refuses it. **`success: true` is being caught by a
language model, not by code**, on either side. That holds only while block pages
read as recognisable prose.

### 8c. FIFTH ROOT CAUSE: nested `<noscript>` discards the whole body

MAS's `empty_*` family — **406 pages, 70 hosts, HTTP 200 with markdown of
exactly one character** — was the one class this record could not explain. Now
diagnosed, offline-reproducible, one-line fix:
`tasks/noscript-collapses-body-to-empty-markdown.md`.

`https://www.kiertopakkaus.fi/`: 312,628 B rendered HTML → **97 B
`cleaned_html`** → 1 B markdown. A WordPress lazy-load plugin emits a **nested
`<noscript>`** around the GTM block; `<noscript>` cannot nest, the outer element
is never closed, and libxml2 swallows the entire remaining document. Excising
that one region alone: 97 B → 47,310 B. Static mode is unaffected because
`aitosoft_static_mode._strip_hidden_decoys` already decomposes `noscript`.

Explains every observation MAS had: exact reproduction 3½ months apart (stable
plugin markup), `vaskisepat.fi` recovering on its own (markup changed), JSON
through `wp-json` working while HTML came back empty (no HTML parse), and the
"nav-only" hosts yielding one character.

### 8d. Live re-check of the challenge family — 5 of 5 came back clean

First `magicad.com` (classified `challenge_all`, 4/4 pages) returned clean
content from our Azure egress: static 12,304 B, full 15,982 B. After MAS's
reply-4 nominated four more `challenge_all` hosts to probe, **all four were
clean too** — full mode, MAS's V14 config, prod rev 0000030:

| host | MAS's April capture | our Azure egress, 2026-07-30 |
|---|---|---|
| `magicad.com` | 4/4 pages challenged | 200, 96,764 B html, 15,982 B md |
| `savagroup.fi` | 16/16 challenged | 200, 183,502 B html, 8,842 B md |
| `palsatech.fi` | 10 pages challenged | 200, 102,354 B html, 8,096 B md |
| `pajala.fi` | 10 pages challenged | 200, 156,137 B html, 9,320 B md |
| `recset.fi` | 13 pages challenged | 200, 100,248 B html, 1,671 B md |

None carried `robot-suspicion` or `connection security`. MAS separately
confirmed three of their hosts serve clean content from a Finnish consumer IP,
and `magicad.com` is clean to *both* of us.

**Reading: the challenge looks time-bounded — a deployment around 2026-04 that
has since been withdrawn — not a standing block on our egress.** MAS's captures
are dated 2026-04-21.

**This is the finding that moves money.** The residential-proxy case rested on
"171 of 243 affected hosts are egress-reputation" (§8b). If the challenge is
gone, most of those 171 are re-capturable today at zero cost, and the genuine
reputation class shrinks to roughly `konecranes.com` + `louisvuitton.com` +
`alpit.io`. **Do not authorise proxy spend on the 171 number** — re-decide from
MAS's post-deploy re-scrape. Carried into
`tasks/residential-egress-retry-path.md`.

Honest caveats: n=5, MAS-nominated rather than randomly sampled, and per-host
site changes could explain individual cases. Suggestive, not conclusive.

Two consequences that already bound implementation work:

- The blindspot fix had to be built against MAS's stored bodies as fixtures,
  not against live hosts — which is what was done.
- `recset.fi` returned 1,671 B of markdown from 100,248 B of HTML. Thin but not
  1 byte, so probably a genuinely thin page rather than the `<noscript>`
  collapse. Worth a second look in MAS's re-scrape data rather than another
  live hit; the host is now on the do-not-test ledger.

### 8e. Open with MAS

- Asked for one full stored challenge HTML so the `robot-suspicion` vendor can
  be identified and the pattern generalised properly rather than guessed.
- Told them the deploy now bundles Q2, so their `redirected_status_code >= 400`
  check keeps working and redirect-blocked hosts never pass through an
  opaque-500 window.

---

## 9. Deployed 2026-07-30 18:24 UTC — `0.9.2-failure-class`, revision `--0000031`

All five root causes from this record are now in production in one image.

| § | Root cause | Task | Verified in prod |
|---|---|---|---|
| §1 | untimed `page.content()`/`page.evaluate()` wedge the render | `done/render-retry-unbounded-hang.md` | offline only — see below |
| §2b | block detection judged the first redirect hop | `done/redirect-status-blinds-block-detection.md` | ✅ konecranes.com |
| §2a/§3 | origin failures laundered into our 5xx | `done/origin-vs-crawler-failure-classification.md` | ✅ konecranes.com |
| §8b | detector blind to the dominant challenge family | `done/antibot-detector-challenge-blindspot.md` | fixtures only — challenge is egress-specific and intermittent |
| §8c | nested `<noscript>` discards the body | `done/noscript-collapses-body-to-empty-markdown.md` | fixtures only — reference host is on the do-not-test list |

`https://konecranes.com` in prod, one response carrying two of the fixes:

```json
{ "success": false, "status_code": 403, "redirected_status_code": 403,
  "failure_class": "origin_blocked", "render_mode": "full" }
```

HTTP 200. Before: `success:true, status_code:301` with the Varnish block page as
content. Before *that* (for `www.`, no redirect): an opaque, retried HTTP 500.

### What this record got wrong, kept for calibration

- **§2b's Konecranes attribution** (corrected in §8a by MAS's data, not by us).
- **The `Checking your browser` size-gate hypothesis** (§8b step 1). MAS measured
  those pages at 61 B and 99 B — three orders of magnitude under the gate. The
  real suppressor was that the tier-2 list is only reachable through
  `is_blocked`'s 4xx/5xx branches while challenge screens are served with
  **HTTP 200**, so that pattern had never been consulted for the pages it was
  written for, in any version of the detector. Found while implementing;
  confirmed against the pre-fix detector at commit `2a9daa1`.

Both errors were inferences that outran the data, and both were caught by
someone measuring instead of reasoning. That is the pattern worth carrying
forward from this eval, more than any individual fix.

### Not verifiable in prod, and why

The `<noscript>` and challenge fixes cannot be confirmed live by us. The
reference hosts are on the do-not-test list, and the challenge family is
egress-specific *and* intermittent — MAS confirmed from a Finnish consumer IP
that `kotkanjulkisetkiinteistot.fi`, `savagroup.fi` and `magicad.com` all serve
200 with full content, so a clean fetch from anywhere proves nothing. **MAS's
re-scrape is the measurement**: the 70 `empty_*` hosts should recover full
content, and the 243 challenge hosts should start failing honestly.

Expect their success rate to drop on the next sweep. Everything that drops was
already broken.

### Open, carried forward

- §8e's request for a stored challenge HTML is **closed unfulfillable**: MAS
  stores markdown only. They gave a verbatim markdown sample instead, which was
  enough. Landing `cleaned_html` storage is on their roadmap.
- The 171 egress-blocked pages remain unaddressed by design —
  `tasks/residential-egress-retry-path.md`, a budget decision.
- Envelope `success` still reads `true` when the single result failed. Asked MAS
  whether they want it as the aggregate.

---

## 10. MAS's 243-host re-scrape, 2026-07-31 — the measurement that reads §9

Source: `tmp/mas-repo-messages/07-from-us-243-host-rescrape.md`. One page per
host, chosen as a page demonstrably broken in April, production config, 243/243
carrying `failure_class` so the build is confirmed. 251 page loads for 243 hosts
(they flag five hosts that received extra visits through their retrying client,
plus 3 A/B requests — 254 for the day).

This is the deliverable `post-deploy-measurement-0.9.2-failure-class.md` was
waiting for. Four of the five fixes are now measured from outside.

| Population | n | Result | Predicted |
|---|---:|---|---|
| `empty_*` | 70 | **35 recovered, 33 still empty, 2 origin-error** | we said 70/70; MAS said 62–68 |
| `challenge_*` | 171 | **133 real content, 31 `origin_blocked`, 4 block-page, 2 empty, 1 origin-error** | split — correct in shape |
| challenge leakage | — | **zero** challenge screens returned as `success: true` | the challenge tier did its job |

### 10a. The `<noscript>` fix worked, and it was not the whole `empty_*` family

Half the family recovered. The other half is a **split with proof in both
directions**, produced by MAS's one-field A/B (`delay_before_return_html` 2.0 →
10 on three hosts):

- **Theirs:** `revisol.fi` rendered 237,037 more bytes given eight more seconds;
  `cleaned_html` 242 → 101,091. Captured before it painted.
- **Ours:** `apteam.fi` and `flvi.fi` returned **byte-identical** `html` across
  two visits forty minutes apart with a five-times-longer wait, and identical
  ~90-byte `cleaned_html`. A 73 KB body reduced deterministically inside our
  cleaning path. Second member of the `<noscript>` failure *shape*, different
  cause. → `tasks/cleaned-html-collapse-guard.md`.

Neither side claims proportions: 1 of 3 is an existence proof in each direction,
not a rate. MAS ruled their own content-filtering config out by measurement
(`word_count_threshold` inert at 1,000; `excluded_tags` reproduces the
fingerprint exactly and they do not send it).

**Calibration:** our "70/70, anything else is a second root cause" prediction was
wrong on the number and right on the inference. There was a second cause, and a
third.

### 10b. The challenge family: §8d's read held, its number did not

133 of 171 return real content, so the 2026-04 challenge is largely gone — §8d's
5/5 probe pointed the right way. But **31 hosts are genuinely blocked, not ~3.**

| class | n | content | `origin_blocked` | blocked rate |
|---|---:|---:|---:|---:|
| `challenge_all` | 117 | 108 | 9 | 7.7 % |
| `challenge_partial` | 54 | 25 | 22 | **40.7 %** |

Both sides predicted the reverse split. MAS checked whether our five §8d probes
had been drawn from the easy half and found they had not — four of the five were
`challenge_partial`, the harder one. **The sample was fine and simply too small:**
five clean draws is entirely compatible with an 18 % block rate (0.82⁵ ≈ 0.37).
"Roughly three hosts" was the most optimistic reading of a sample that could not
exclude 31. Recorded as a calibration lesson of the same family as §9's two: an
inference outrunning its data, in the cheap direction this time.

**27 of the ~29 genuine blocks are two vendors** — 23 serve the `robot-suspicion`
challenge from cloudfront `d1rozh26tys225`, 4 serve an 80,671-byte
`403 - Forbidden` template. So the question is not "31 heterogeneous hosts" but
"what do these two do". Neither side has evidence that a residential IP gets
through; MAS explicitly declines to recommend spend on it.

### 10c. HTTP 202 — the code that is not a page status

36 of 243 responses carried origin status **202**, `redirected_status_code: 202`,
`render_mode: full`. **100 % came from the challenge families** — not one
`empty_*` or `blockpage_*` host produced one — and 19 of the 23 challenge screens
in the whole run arrived at 202. The same 202 served a challenge screen (19), a
block page (4), the real site (10) and an empty body (3).

A status that returns both the interstitial *and* the real content is the
signature of a JS challenge that resolves into the page. That reframes the
challenge family as a possible **capture-timing** problem rather than an egress
block, which would make 23 of the 31 free to recover.
→ `tasks/challenge-interstitial-resolve.md`, which must produce a number before
anything is built on it.

> **ANSWERED 2026-08-01, offline, zero live requests.** Phase 1 of that task ran
> ~140 crawls against the fixture origin through the full production path
> (`test-aitosoft/experiment_challenge_capture.py`). The number:
>
> **A capture wait `W` captures any challenge resolving within `W + 1.22 s` of
> `domcontentloaded`, and stores the interstitial for anything slower.** One
> constant predicts all 84 cells of the resolve-delay × capture-wait grid with
> zero exceptions; the 1.22 s is our own post-`goto` pipeline, measured
> independently on `/ok` at 1.21–1.24 s across six waits. **MAS's
> `delay_before_return_html: 2.0` therefore covers a 3.2 s challenge** — the
> bottom of their own 3–5 s `raw://` estimate, not the top.
>
> So 10c's read was right as a *mechanism* and wrong as a *defect*: we do store
> interstitials instead of the pages they become, but only when the challenge
> outlasts the wait. Three consequences worth keeping:
>
> - **§1's `page.content()` race costs no captures.** `/challenge/resolve-by-nav`
>   (a top-level navigation replacing the execution context) and
>   `/challenge/resolve-after` (DOM rewrite) produced **identical grids across all
>   42 paired cells**. The `_capture_html` settle-and-retry shipped 2026-07-30
>   covers it. Any future argument of the form "a navigation loses the capture"
>   needs new evidence; this grid is against it.
> - **A raised wait is paid twice on a wall.** A blocked result costs exactly 2
>   document loads (32/32 blocked cells), because `maybe_retry_blocked` hands
>   patchright the *same* `CrawlerRunConfig`. `/challenge/never` cost 6.47 s at
>   W=2.0 and 25.22 s at W=10. A global raise is most expensive on the hosts it
>   cannot help.
> - **The unmarked interstitial is still stored as a page** — `success: true`,
>   `failure_class: none`, 54 markdown characters. Anything triggered by the
>   detector inherits the detector's recall, which is 10d's problem, not this one.
>
> Phase 2 is a **go, re-scoped from M to S**: the retry we already run is the
> re-capture, so it needs a longer wait rather than a new mechanism. Not
> established, and deliberately not tested: whether the real vendor's challenge
> resolves for us at all. MAS's next sweep after phase 2 ships measures that for
> free.

### 10d. Two measured defects in the detector, in opposite directions

Both from MAS's own run, both now tasked as
`tasks/detector-round3-evidence-vs-inference.md`.

- **Misses:** an 80,671-byte body whose entire visible content is
  `403 - Forbidden` passed as `success: true` at status 202 on four hosts, while
  the identical bytes at status 403 were caught on four others. Every size gate
  in `antibot_detector` is on `len(html)`; this vendor pads.
- **Invents:** four of 33 `origin_blocked` verdicts are not blocks, including
  `norex.com`, where **our own `Crawl4AI Error:` placeholder** was reported to MAS
  as the origin blocking us — the classification bias in
  `aitosoft_failure_class.py` inverted, in the direction its docstring calls the
  expensive one.

### 10e. What changed in the open work

| Task | Before | After 10 |
|---|---|---|
| `post-deploy-measurement-…` | gate on everything | **delivered here**; residual is a prod-log census |
| `residential-egress-retry-path` | on hold at ~3 hosts | 31, of which ≤8 may survive `challenge-interstitial-resolve` |
| `blocked-host-retry-economy` | ~12–16 page loads/company | MAS no longer retries origin-class failures ⇒ ~4; the win shrank |
| `antibot-minimal-text-false-positive` | latent, no report | **observed live** (`norex.com`); merged into detector round 3 |
| `static-fallback-within-fence` | high | re-price first — the hang fix should have made fence-504s rare |

## 11. The 9 × 500 in MAS's probe — our own memory guard, and what it really means

Verified 2026-08-01 from Log Analytics plus an offline probe, zero live traffic.
Owned by `tasks/render-500-window-2026-07-31.md`, which carries the queries. Two
passes were needed and the second corrected the first; both are recorded here
because the correction is the reusable lesson.

### 11a. The cause

All nine of MAS's HTTP 500s are one line: `crawler_pool.py:179` raising
`MemoryError` because `get_container_memory_percent()` read 85.1–95.6 % against
our own `memory_threshold_percent: 85.0`. The guard sits *before*
`AsyncWebCrawler(...)` and `crawler.start()`, so **no browser was created and no
navigation happened — MAS's day cost 246 origin hits, not 255.**

`api.py`'s generic `except Exception` turns that `MemoryError` into HTTP 500 with
`failure_class: render_error`. MAS retries 500 three times, so **a memory-pressure
event currently multiplies its own load by four.** RenderGate already answers the
same condition correctly — 429 + `Retry-After` — so "we are full" is served at two
different wire statuses depending on which limiter notices. Same defect shape as
the `render_error` split in §10, and it is fixed the same way.

### 11b. The 235 MB was never the container

The 500 bodies report `server_peak_memory_mb` of 204–235 MB on a 4 GiB replica,
which reads as a contradiction with a 95.6 % cgroup reading. It is not one.
`server_peak_memory_mb` is `psutil.Process().memory_info().rss` (`api.py:105`) —
the single gunicorn worker. Chrome runs as descendant processes (~7 per browser)
and has never been in it.

Measured offline through the fixture origin and the real production path, one
pooled browser per crawl with a distinct `browser_config`
(`test-aitosoft/experiment_pool_memory.py`), run cold and again warm:

| per pooled browser | cold cache | warm cache |
|---|---:|---:|
| worker RSS (`server_peak_memory_mb`) | **+2.0 MB** | **+2.3 MB** |
| cgroup `memory.current` (the guard) | **+165.0 MB** | **+138.9 MB** |
| — `anon` | +129.9 MB | **+129.4 MB** |
| — `file` / `inactive_file` | +27.1 / +26.0 MB | +1.8 / +1.4 MB |

Three things follow. **The reading is roughly right and the memory really was
scarce** — `anon`, the term the kernel cannot reclaim, is a stable ~130 MB per
browser across both runs. **The page-cache term is a one-time fill, not a
per-browser cost** — 27 MB/browser cold, 1.8 MB/browser warm, i.e. Chrome's
binary and libraries paged in once; `inactive_file` is 16 % of the growth on a
cold container and 1 % on a warm one, so subtracting it is a bounded offset
rather than the explanation. And **sum-of-RSS is not an instrument either**: each
browser moved process-tree RSS by ~486 MB against the cgroup's ~139–165 MB,
because Chrome's shared mappings are counted once by the cgroup and seven times
by a tree walk. Corroborating from prod: btv4v read 8.2 % (≈336 MB) three seconds
after boot with a 235 MB worker, so the cgroup path and a real ~4 GiB limit are
live; it later reached 100.0 % with no OOM kill and no worker restart.

### 11c. It was not a scale-out ramp. It was scale-from-zero.

The first pass reported the nine landing on two scale-out steps (2→4, 4→6). Wrong
in both directions. **All nine are on one replica** (`…-btv4v`), and the app was
**scaled to zero** at 04:40. KEDA activated 0→1 at 04:44:43; MAS's probe started
13 seconds later; the second replica admitted its first render at **04:46:54** —
*after* eight of the nine failures. The ninth, at 04:50:25, sits inside a
2½-minute `AssigningReplicaFailed / Waiting for infrastructure` node-pool stall.

One cold replica carried the entire opening burst for 122 seconds. That is worse
for the sweep than the original reading, not better: every wave that starts from
an idle service reproduces it exactly, and no amount of scale rule fixes the first
two minutes.

### 11d. The actual cause: nothing bounds pool residency

`render_capacity: 2` bounds concurrent renders; `max_pages: 5` bounds pages per
browser; **nothing bounds the number of live browsers.** Residency is governed by
idle TTL, so the browser count tracks distinct configs seen in the last TTL
window, not concurrency — btv4v held 8 browsers to do 2 renders' worth of work,
which at 165 MB each is the 4 GiB.

It thrashes on top of that: **125 creates, 132 closes, for 10–12 distinct
signatures per replica.** Under pressure the janitor drops `cold_ttl` to 30 s,
closes browsers, and the next request for the same config must launch a fresh one
— allocating while memory is tight, which is what trips the guard.

Two corrections to earlier assumptions fall out of the same numbers:

- **MAS's per-company `browser_config` does not defeat pooling.** 243 hosts
  produced 10–12 distinct signatures per replica, not one per company. The
  "15,000 companies is 15,000 signatures" worry is unfounded.
- **The permanent browser is never used.** `Using permanent browser` fired 0
  times against 224 pool gets, because MAS always sends a `browser_config` and
  `_sig` never equals `DEFAULT_CONFIG_SIG`. Every replica launches a browser at
  boot that serves nothing and holds ~165 MB for its whole life.

### 11e. Method note — this one is worth keeping

Both first-pass errors came from the same omission: **`ContainerAppConsoleLogs_CL`
is workspace-wide**, and the queries had no app filter, so `aitosoft-edge`'s
replica was counted as ours and `dcount(ContainerGroupName_s) by bin(…)` counted
"replicas that logged in a bin" as "replicas that existed". Filter
`ContainerGroupName_s startswith 'crawl4ai'`, take replica history from
`ContainerAppSystemLogs_CL` which states it, and take "started serving" from the
first `RenderGate ADMIT` rather than from container-start events. Adding `by
ContainerGroupName_s` to a query already being run would have caught it.

Second note: `janitor()` reads `mem_pct` *before* its sleep and logs it *after*
the cleanup, so the `mem=` and the `hot=/cold=` in one `📊 Pool:` line are up to
`interval` seconds apart. They are not a simultaneous sample and must not be
correlated as one.
