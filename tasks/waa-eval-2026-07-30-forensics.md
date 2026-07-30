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
| Egress IP | `172.199.49.233` (Azure, West Europe) | 3× `render_mode: static` GET of `api.ipify.org`, stable across calls |
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

| Task | From | Gate |
|---|---|---|
| `tasks/redirect-status-blinds-block-detection.md` | §2b | none — implement first |
| `tasks/render-retry-unbounded-hang.md` | §1 | none |
| `tasks/origin-vs-crawler-failure-classification.md` | §3, §2a | MAS answer to Q2 |
| `tasks/static-fallback-within-fence.md` | §1, §3 | MAS answer to Q1 |
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

## 7. Open questions to MAS (sent 2026-07-30, awaiting answer)

Two tasks are gated on these. Record the answers **here** when they arrive.

### Q1 — automatic static degradation inside the request?

When the browser path cannot finish, should we run a static fetch inside the
remaining budget and return it tagged `render_mode: "static-fallback"` instead
of returning 504? Trade-off given to them: static markdown has no JS-rendered
content, no `fit_markdown`, and empty `links.internal`/`links.external`, so for
a JS-dependent site it is a worse capture that looks like a success. Options
offered: (a) yes, automatic + tagged; (b) yes, but `success: false` with content
attached; (c) no, keep their client-side pivot.

**Gates:** `tasks/static-fallback-within-fence.md`
**Answer:** _pending_

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

**Gates:** `tasks/origin-vs-crawler-failure-classification.md` (and probably
`tasks/antibot-minimal-text-false-positive.md`, which wants the same flag)
**Answer:** _pending_

### Q3 — purpose-built preflight endpoint?

Static mode already serves as a reachability probe (0.3–2 s, real origin status,
never 504s). Do they want a dedicated endpoint returning
`{reachable, status, final_url, bytes, elapsed_ms, blocked_suspect}` without
markdown conversion — and if so, one URL per call or a batch? A batch preflight
is the one place where relaxing our single-URL contract would obviously pay.

**Gates:** nothing yet — opens a task only if they say yes.
**Answer:** _pending
