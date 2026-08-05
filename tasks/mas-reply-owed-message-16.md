# Reply owed to MAS — the answers, ready to write up

**Status:** open. The ball is with us. Written 2026-08-05, **updated the same
day** after the egress-path work shipped to `main`.
**Size:** S — it is a message, not code. Every answer below is already
established; nothing needs measuring first.
**It now gates a deploy.** `main` holds an undeployed wire-status change; see
the "Announce first" section.
**Their message:** `tmp/mas-repo-messages/15-from-us-your-answer-sat-here-two-days-and-the-run-went-cold.md`
(gitignored). Ours becomes `16-to-mas-...`.

**Cite filenames, never integers.** MAS asked for this explicitly: their ledger
numbers diverged from ours (our "13" is their "11"; they have no 12 or 13), and
the mismatch is part of why our 14 sat unread for two days.

---

## Context a clean session needs first

**Message 14 was delivered and read.** It sat unread in their repo 2026-08-03 to
2026-08-05 because their thread ledger never got a row for it. They have fixed
the ledger. Their §3 gate — a whole-site URL inventory — was released by our
answer two days before they knew it. **Nothing of ours is now gating their
sweep.**

**Their 2026-08-05 run:** 10 companies, `--concurrency 2`, deliberately
unpinned against a scaled-to-zero service. Their owner has ruled they will
**never** pin a warm replica, because every real campaign starts cold and
engineering around that would measure the wrong thing. The larger cohort will
run **in segments**, which *raises* cold-start exposure rather than lowering it.

**Our numbers for that run, and they reconcile with theirs exactly:** 62
renders, 57 success / 5 failure, p50 4.61 s, p90 7.36 s, longest 60.38 s. Their
51 stored + 11 failures = our 62. Our 57 successes are exactly 6 more than their
51 stored — **those 6 are the 404s**, which is the 404 class confirmed from both
sides at once. 0 × 429, 0 × 504, 0 × 500, 0 memory refusals, 0 collapse-guard
fires, 0 janitor force-closes. Pool memory p95 29.9 %, max 33.7 % against an
85 % guard. KEDA scaled 0 → 15 and back to 0 cleanly.

---

## Announce first: one wire status changes, and it needs their ack before we deploy

**This did not exist when the file was written.** The egress-path work is
committed to `main` and **deliberately undeployed**, because it contains a
behaviour change and this repo's rule is that behaviour changes wait for the
relay. Full record: `tasks/done/egress-proxy-blocks-the-event-loop.md`.

**What changes for them, in one line: a domain that does not resolve stops
being an HTTP 400 and becomes an ordinary terminal failure envelope.**

| | before | after |
|---|---|---|
| wire status | **400** | **200** |
| body | `{"detail": "URL blocked (SSRF protection): URL blocked"}` | normal envelope |
| `success` | — | `false` |
| `failure_class` | **absent** | `origin_unreachable` |
| retryable | no | no |
| cost to us | 0.08 s, no render slot | unchanged |

Why it was wrong: our egress broker mapped `socket.gaierror` — NXDOMAIN, i.e. a
lapsed domain — onto the same exception as an SSRF policy refusal. So our own
security string was blaming a customer's domain, with no class attached. **A
company-registry sweep is mostly lapsed domains**, so on their current corpus
this is the difference between several hundred companies filed as "we refused
this URL" and the same companies filed as "the domain is dead".

Three things to say plainly:

1. **Their `origin_unreachable` count will rise after we deploy.** That is the
   reclassification, not a regression. If they are trending that class across
   segments (and they should be — see the block-rate note), the discontinuity is
   ours and it is this.
2. **Ask whether anything on their side branches on 400 from us.** It is
   terminal either way, so we expect no impact — but 400 is the one status where
   "our fault vs theirs" changes meaning, and it is one sentence to confirm.
3. **Ask for a go-ahead to deploy.** Nothing else in the image is visible to
   them: DNS resolution moved off our event loop, a dead host now costs 30 s of
   a render slot instead of 60 s, and a failed `http://` connect stopped
   reporting itself as the customer blocking us.

---

## Their five questions

### (1) `crawl_stats` / `response_headers` — "any reason not to rely on them?"

**Yes. Say so plainly — they are about to build their per-page record on this.**

**Neither is contractual.** `test-aitosoft/test_mas_contract.py:168-178`
enumerates the nine fields they may parse — `url`, `success`, `status_code`,
`redirected_status_code`, `error_message`, `failure_class`, `render_mode`,
`markdown`, `links`. Neither field is among them. Both are 100 % upstream-owned
(`crawl4ai/models.py:148,162`; populated `async_webcrawler.py:423-429,683,695`),
untested by us, and an upstream sync could change either without tripping
anything we own.

Four traps, all specific:

- **`crawl_stats` is absent on three paths they will hit.** Key entirely absent
  in static mode (`aitosoft_static_mode.py:173-182`) and in `failed_result()`
  (`aitosoft_failure_class.py:428-438`); `null` on cache hits and robots
  refusals. Full-mode results always have the *key* (pydantic emits it) but it
  may be `null`. **Three different encodings of "no data"** — absent, `null`,
  and `{}`. A `.get()` chain with defaults is mandatory.
- **Its presence on failures depends on their own `max_retries`.**
  `async_webcrawler.py:581-582` re-raises when `max_retries == 0`, landing at
  `:742` which returns a result with **no** `crawl_stats` and no
  `response_headers`. If they ever drop the field, it silently vanishes from
  every exception-path failure.
- **`response_headers` on a redirected URL is the redirect's headers, not the
  page's.** `async_crawler_strategy.py:876-886` walks back to the *earliest* hop.
  Finnish sites redirect apex→www almost universally, so for much of their
  corpus this describes a hop whose body was discarded. Keys are lowercased by
  Playwright (upstream's own doc example does `.get("Server")` and never matches).
- **When patchright fires, `crawl_stats` describes only the retry leg**
  (`aitosoft_patchright_fallback.py:323` replaces the whole result), so
  `attempts` is not the request's navigation count, and nothing in the response
  says patchright ran.

**Their `vero.fi` observation is real but accidental.** `proxies_used[].status_code`
carries the *first* hop (`async_webcrawler.py:555`) while our `api.py:920-922`
rewrites the envelope `status_code` to the *final* hop. It survives only because
`crawl_stats` predates `effective_status()` and was never updated. It is the
earliest hop only — a 301→302→200 chain shows `301`, middle hops invisible — and
on a thrown attempt the status is discarded entirely.

**Four of its six sub-fields are dead constants for them, by our security
policy:** `proxies_used[].proxy` is always `null` and `fallback_fetch_used`
always `false` (both forbidden at the untrusted boundary,
`async_configs.py:210,213`); `resolved_by` is only ever `"direct"`; `retries`
is always `attempts - 1` with a single proxy. The information-bearing content is
`attempts` plus per-attempt `status_code` / `blocked` / `reason`.

**`crawl_stats` is not an outcome field.** It is written at
`async_webcrawler.py:683`, *before* our collapse guard runs (`api.py:933`), so a
page the guard fails still reads `blocked: false, resolved_by: "direct"`.
`success` and `failure_class` are the outcome.

**The offer to make:** if they want the first redirect hop as a durable record,
that is a **named field, one line in `api.py`, and a row in the contract test** —
not a stats blob. Same for anything else in `crawl_stats` they intend to depend
on. Cheap, and it is the difference between a contract and an accident.

### (2) Does a cold-start ingress 504 leave a trace? — **it did, as of today**

Until this session: **only an absence.** There were no diagnostic settings at
all on the app or the environment, so `ContainerAppHTTPLogs` — the only surface
that records a request the ingress terminated before a container existed — was
off. The platform `Requests` metric is the only other candidate and it
demonstrably under-records exactly that window (2026-07-30: one crawl served at
08:14:56, zero metric datapoints 08:13–08:19).

**Enabled 2026-08-05**, diagnostic setting `aca-http-logs` on the managed
environment, HTTP category only (console and system logs already arrive via
`appLogsConfiguration`; adding them here would double-ingest and double-bill).
It carries `ResponseFlags`, `UpstreamHost`, `ReplicaName`, `RequestDuration`,
`RequestId`, `Path` — an ingress-terminated request lands with an empty upstream
and an Envoy flag.

**Tell them it is on, that it is environment-wide, and that it has no history** —
it answers the question from 2026-08-05 forward only, so their first segment is
the first thing it can describe. Nothing in it changes their client behaviour.

### (3) `apteam.fi` / `flvi.fi` root cause — still open, and now cheaper

Unchanged from our 10 §4. Accept their offer: they store `html` and
`cleaned_html` from 2026-08-04 onward, so **ask them to hand us the bytes** if
the class recurs rather than a description. That is the whole answer — it is
their evidence to supply now, and holding both fields side by side is exactly
what distinguishes "their cleaner dropped it" from "our capture never got it".

### (4) The ACA ingress request timeout — **240 s, and they can never hit it**

Confirmed against current Microsoft docs (*Ingress in Azure Container Apps*,
updated 2026-05-11): "Request time out is 240 seconds".

**Not configurable here.** The knob is `properties.ingressConfiguration.requestIdleTimeout`
on the *environment*, minimum 4 minutes, and it requires **premium ingress**,
which requires **workload profiles**. `aitosoft-aca` is `workloadProfiles: null`,
`ingressConfiguration: null` — Consumption-only. So this is behind the *same*
environment migration as the 4 GiB memory ceiling, not a separate blocker. There
is no app-level timeout property at any API version through 2026-03-02-preview.

**It is an *idle* timeout, not an absolute one** — nothing in our docs said this.
We stream nothing until the end, so for our traffic idle == elapsed and it acts
as a hard ceiling.

**The direct answer to their question: no, there is no fourth 504 source.**
Their client gives up at 210 s; an ACA ingress 504 requires the connection still
open at 240 s. They hang up 30 s earlier, so what they would observe is their own
client timeout, never an HTTP 504 from us. True as long as their timeout stays
under 240 s — worth saying, because it makes 240 s a number they must not exceed.

Supporting: **all 13 × 504 in 93 days sat at 180–184 s** — our own
`wall_clock_s: 180` fence, to within a second. Zero anywhere near 240 s.

### (5) A live watch — agreed, and we will keep the method

Accept. Confirm we will keep read-only Log Analytics with **no `/health` curl**,
since warming a replica destroys the condition they are measuring. Ask for the
window before segment 1.

---

## Things to tell them that they did not ask

**`max_retries` is 1, not 2 — and four of our own documents said 2.** All 213
`Anti-bot retry` lines in the last 14 days read `1/1`; `config.yml`'s
`base_config` does not set it, so the value is theirs.
`async_webcrawler.py:405` is `_max_attempts = 1 + max_retries` and `:442` prints
the config value verbatim. **Ask them to confirm and to tell us if they change
it**, because it is a straight multiplier on what a dead or blocked host costs
us: at `max_retries: 2` a dead host is 90 s of a render slot instead of 60 s.

**We have no outbound politeness, and a config key makes it look like we do.**
`config.yml:106` sets `crawler.rate_limiter.base_delay: [1.0, 2.0]`, but that
limiter is only consulted on the `arun_many` path (`async_dispatcher.py:285`),
and `api.py:839` selects `arun` whenever there is one URL — which our
server-enforced single-URL contract guarantees. It never fires. The other block,
`rate_limiting:` at `config.yml:54`, is *inbound* API limiting (1000/minute per
caller) and protects us from them, not origins from us.

**So pacing across 15,000 hosts is entirely theirs**, and it matters more than
any capacity number: at `maxReplicas: 30` × `render_capacity: 2` the ceiling is
~60 concurrent renders, all leaving from **one shared Azure SNAT address that
is not contractually ours** (see PRIVATE.md). This repo's own history is a
permanent Cloudflare block earned by over-scraping.

**Watch `origin_blocked` per segment, not in aggregate.** A block rate that
*rises* segment over segment is IP-reputation decay, it is irreversible, and it
is the one signal that should stop a sweep. Segments make this measurable for
free. Nobody had written this down before today.

**The scale-down tail.** Their 9-minute run held up to 15 replicas until
**05:53:44** — renders finished ~05:45, so ~8 minutes of idle replicas at peak.
Segmenting multiplies this by the segment count, in the same direction as the
cold-start exposure they already flagged. Cost, not correctness.

---

## Questions to ask them

(Plus the deploy ack in "Announce first" — that one is the only blocking ask.)

1. **Do they honour our `Retry-After` literally?** `aitosoft_admission.py:52`
   advertises `RETRY_AFTER_S = 5`, against a **measured ~35 s** image pull on
   mid-ramp replicas (six pulled simultaneously at ~35 s each on 2026-08-05
   05:41:40). If they retry at 5 s, a scale-out burst becomes a retry storm at
   exactly the worst moment. Their earlier message implies a long backoff, so
   this is probably fine — but it is one sentence to confirm and a one-constant
   fix if not.
2. **Do they stop queuing a company's remaining pages once the root returns
   `origin_unreachable`?** Still worth asking, but **the arithmetic behind it
   was wrong and is now corrected.** "Dead host" is two populations:

   - **Does not resolve (NXDOMAIN)** — the common case in registry data.
     Measured: **0.08 s, no render slot, never reaches the render gate.** Free
     for both sides. This is the population the earlier draft priced at 60 s.
   - **Resolves but will not accept TCP** (their `vetrea.fi`, which resolves to
     a redirect service that does not answer) — **60 s of a render slot per
     URL**, dropping to **30 s** once we deploy the connect-timeout change.

   So the ask is smaller than we were about to claim, and it is worth saying so
   rather than quietly shipping a corrected number. It still matters for the
   second population: if a dead company contributes 6–8 URLs, that is 3–4
   minutes of render capacity per company, and their own message already
   identified this as why in-flight concurrency accumulated past 2.

Also worth one line: **what fraction of sweep URLs are `http://` rather than
`https://`?** The misattribution it sizes is now fixed, so this is no longer a
gate on anything — but it tells us whether the fix mattered or was theory, and
that is worth knowing before we generalise from it. Note the population is
narrower than we first thought: it needs an `http://` seed **and** a host that
resolves but refuses TCP, since a non-resolving host now never reaches the
browser at all.

---

## Things NOT to re-offer

- **The §7 response-projection offer as written is dead.** They now store `html`
  *and* `cleaned_html` on every page, and want both — holding them side by side
  is what answers "did their cleaner drop this, or did our capture never get it".
  They will accept dropping **`fit_html` only**: 101,117 B of a 634 KB result,
  **~16 %**. Do not build it unasked; they said "if you build one".
- **`crawl_stats` must not be projected away** — they asked for it by name.
- **`content_source="raw_html"`** — priced and rejected, see
  `tasks/cleaned-html-collapse-guard.md`. Do not offer it as a fix for their
  404 or collapse concerns.
