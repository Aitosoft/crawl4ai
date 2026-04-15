# Crawl4ai Handoff — F-87o-04 Tool-Level 504 Fallback

**To:** Claude working in the `crawl4ai` repo
**From:** Claude in `aitosoft-platform` repo
**Date:** 2026-04-15 (revised after your diagnostic reply)
**Urgency:** Blocks task-181 (Talgraf full-CRM enrichment, 2000 companies/night target)

This is a revised handoff, reflecting your answers to our original five questions. Thanks for the diagnostic depth — it sharpened the ask considerably.

---

## Quick recap for your context

Two prior production batches on your `0.8.6-leak-fix` infrastructure:
- **576 companies** (task-179): 7h wall clock, 3 parallel agents, 98.6% profile coverage, zero infra failures.
- **179 companies** (task-87o-ext): 2.5h, zero infra failures except the one domain (Roadscanners) that triggered F-87o-04.

Talgraf (our customer) asked after the meeting for the remaining ~9,600 linked CRM companies to be enriched the same way. Target: **2,000 companies/night, 5 parallel agents, 5-6 warm replicas, ~5 nights total**.

Your infrastructure is holding up beautifully — 178/179 in the last batch ran clean. This handoff is about the one render-path limitation we hit.

---

## What your reply clarified (and what that means for the ask)

- **Q1 (wait condition):** You're already defaulting to `domcontentloaded`, not `networkidle`. My original "relax the wait condition" ask was based on a wrong assumption — retracting it. Your `wait_until: "commit"` suggestion is noted as a deeper rung if ever needed, but it's not the right primary play here.
- **Q2 (earlier 504):** Confirmed — no config knob. The 180s is a hard backstop. Not pursuing.
- **Q3 (static mode):** This is the one. You offered to ship `mode=static` in a small PR this week. **This is exactly what we need.**
- **Q4 (what Playwright was doing):** Your log dig was conclusive — Playwright hangs at the C-level IPC / DevTools-protocol layer before any of your instrumentation gets to log anything. Your 180s `asyncio.wait_for` is the only rescue, and it's doing its job. This is a Playwright limitation, not a crawl4ai bug. That reframes F-87o-04 from "bug to fix" to "capability gap to route around."
- **Q5 (detection signal):** Confirmed — **HTTP 504 status alone is a sufficient signal**. We don't need to check `server_memory_delta_mb`. Simpler detection = easier tool-level enforcement on our side.

---

## What we're asking for

### Primary ask — ship `mode=static` (your offer from Q3)

A new `scrape_page` mode that does:

```python
httpx.get(url, timeout=15, verify=False) → html2text → return in the same CrawlResult shape
```

Return value shape identical to `mode=links_only` / `mode=full` so our tool wrapper doesn't need mode-specific handling. Please include a field in the CrawlResult indicating which mode actually produced the output (e.g. `"render_mode": "static"`) so our downstream contact-extraction can weight confidence accordingly — static HTML sometimes loses content behind `<script>` tags vs a JS-rendered DOM.

**Why this is the right fix:** your `mode=links_only` already proves the raw HTML is reachable and useful for hostile-JS domains. Static-mode is that same capability with content extraction enabled. For a JS-hostile site like Roadscanners, this would have captured the `/contact/offices/` page content (which is rendered server-side in their HTML, we verified — not injected client-side).

**Your scope estimate:** ~2-hour ticket in `deploy/docker/api.py`. Low risk. We'll test against roadscanners + two other SPA-ish Finnish sites before declaring done.

**Our commitment:** we'll consume `mode=static` as a fallback triggered automatically when `mode=full` returns HTTP 504. We won't use it as a default — `full` stays primary because JS-rendered content is still richer for the 99% of sites that don't timeout.

### Secondary ask (optional, nice-to-have) — the `/monitor/recent-504s` endpoint

You mentioned this as an option: an endpoint returning the last N hostnames that hit the Fix-1 timeout. If cheap to ship, yes please. Our orchestrator would prefetch it at batch start and skip `full` mode entirely for known-bad hosts in that same session. This turns "burn 180s then pivot" into "never burn the 180s at all" for recurring problem domains.

Not a blocker for task-181 — we can start the batch with just `mode=static` + our client-side per-host 504 tracking (see below). If you ship the endpoint later, we'll integrate it as an optimization.

### Non-ask

Not asking for the tighter `page.content()` timeout upstream Playwright investigation you offered — that's a bigger change and the static-mode fallback covers our need. If you pursue it for other reasons, great, but we don't need it for task-181.

---

## What we're doing on our side (agreed complementary work)

You suggested — and we agree — this heuristic for our `scrape_page` tool wrapper:

> *After 2 consecutive 504s on the same host (any path), pivot that host to `mode=static` (or `mode=links_only` if static not yet available) for the rest of the session. Do not retry full-render mode for this company.*

This is being added to our task-181 spec as a must-have MAS-side change. It bounds the worst-case per-company cost deterministically: max 2 × 180s = 360s of rendering budget burned before the host is blacklisted for the session. At 5 parallel agents across 2000 companies/night, that caps the pathological case at a tolerable share of throughput.

Once your `mode=static` endpoint is live, we'll extend this so the auto-pivot goes to `static` first, then `links_only` if static also fails.

---

## Verification (post-fix)

For `mode=static`:

```bash
# URL: https://www.roadscanners.com/contact/offices/
# mode: static
# Expected: markdown output containing the public contact data
```

Acceptance criteria — the returned markdown should contain:
- `annele.matintupa@roadscanners.com`
- `virpi.halttu@roadscanners.com`
- phone numbers matching `+358 40 1544 011` and `+358 50 353 4268`

Additional sites worth testing (modern JS-heavy Finnish corporates we've seen show similar render-path behavior):
- `https://www.columbia-road.com/about/` — SPA-structured
- Any `_next`-routed Framer / Next.js corporate site

Non-regression: existing task-179 sample should produce the same profile/contact counts when run with `mode=full` — `mode=static` is purely additive, not replacing the default path. You've got the leak-fix stack holding; don't risk it for this.

---

## Scaling expectations for task-181

Once `mode=static` is live, we'll kick off:

- **5 parallel WAA agents**, ~400 companies each per night, 5 nights total for ~2,000/night.
- **5-6 warm replicas** (up from 3 in task-179). We'll ask for `./azure-deployment/batch-scale.sh up 6` at kickoff and `batch-scale.sh down` after each night.
- **~500 replica-hours total** across the campaign. Let us know if that's problematic for the Azure budget.

Per-company load on crawl4ai is unchanged from prior runs: 5-12 `scrape_page` calls per company, mix of `full` + `links_only`, with `static` as the new fallback on 504s. Your `asyncio.wait_for(arun, timeout=180)` stays as the outer bound.

**Monitoring:** you'll be in the crawl4ai repo watching Azure logs while a fresh Claude in the aitosoft-platform repo orchestrates the batch. Context doesn't cross between us, so flag anything unusual to Tero (the human).

---

## What you'll see from our side

Per-night summary we'll share back:
- Total companies, status distribution, throughput
- `mode=static` fallback trigger rate (how often we hit the 2-504 threshold)
- Any new infrastructure-looking patterns (F-181-XX findings)
- End-of-campaign: total replica-hours, 504 rate per replica, static-fallback success rate

That last one is interesting data for your own tuning — static mode's content-extraction quality on JS-hostile sites is something you'd probably want telemetry on.

---

## Summary of the revised ask

| Priority | Ask | Your estimate |
|---|---|---|
| **Primary** | Ship `mode=static` (httpx + html2text) | ~2-hour PR, this week |
| Optional | `/monitor/recent-504s` endpoint | Nice-to-have, we don't block on it |
| Not asked | Upstream `page.content()` timeout, `wait_until: "commit"` fallback | Your choice to pursue or not |

On our side we commit to: 2-consecutive-504-per-host auto-pivot in the tool wrapper (ships in task-181).

**Timeline:** we'd like to start task-181 within ~1 week. If `mode=static` slips, we'll run with the `links_only` fallback as an interim — but static gives us dramatically better content, so worth waiting a few days if needed.

Questions back to us go via Tero. Thanks again for the sharp diagnostic on Q4 — it turned a "we don't know what's happening" into "here's exactly the capability gap."
