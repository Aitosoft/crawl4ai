# Fence-504 observability + ramp-window render wedge

**Status:** DONE 2026-07-17 — deployed as `0.9.2-fence-obs` (items 1+2 shipped;
item 3 investigated, no patch needed — see Results)
**Priority was:** Medium — 3/808 requests (0.37%) hit opaque 504s during cold
ramp; contained client-side by MAS's static pivot, but we were blind
server-side.

## Problem (as opened)

1. **Fence fires were invisible.** `api.py` raised
   `HTTPException(504, "Crawl exceeded the time limit")` with no log line.
2. **Admissions didn't log the URL.** Immediate admits logged nothing;
   queue-wait admits logged only the duration.
3. **Upstream nav-retry loop believed silent in server context** — a page
   timing out twice at 80s would burn 160s with zero log lines.

Full eval evidence: tasks/done/capacity-scaling-redesign-2026-07-17.md
(WAA eval cross-check section).

## Results

### 1. Fence fires now log (api.py, WARNING, logger `api`)

`WALL-CLOCK FENCE 504: url=%s deadline_s=%s elapsed_s=%.1f gate=%s`

Verified locally with a 2s fence override: 504 returned in 2.8s, warning
carried URL + deadline + elapsed + gate snapshot, and the slot released
(follow-up request admitted at in_use=1/2 and rendered 200). Snapshot is
taken before the `finally` releases, so it still counts the fenced request.
`_deadline` initialized to None at handler top (no NameError if TimeoutError
arrives before the fence is armed).

### 2. Every admission logs its URL (aitosoft_admission.py, INFO)

`RenderGate ADMIT url=%s waited=%.1fs in_use=%d/%d queued=%d`

`RenderGate.acquire()` gained optional `label=` (backward compatible,
`url=-` when absent); api.py passes `urls[0]`. Replaces the old
"RenderGate admitted after N.Ns queue wait" line (queued-only, no URL).
REJECT warnings byte-identical — playbook greps unaffected.
+2 tests in test_admission.py (8 → 10); all pre-existing assertions
unchanged.

### 3. Nav-retries: investigated, NO patch — the "silent retry" premise was wrong

The retry loop (`async_webcrawler.py` `arun`, `_max_attempts = 1 +
config.max_retries`, loop at ~line 419) ALREADY logs every retry attempt
(`Anti-bot retry {n}/{max} for {url}`, WARNING, tag ANTIBOT) and every
exception path (`error_status` → "Proxy direct failed: …"; a goto timeout
raises `RuntimeError("Failed on navigating ACS-GOTO…")` into it). Console
output is gated only on per-request `config.verbose` (`arun` does
`self.logger.verbose = config.verbose`), default True, never overridden by
MAS — and the eval's own `[FETCH]`/`[COMPLETE]` lines come from this same
AsyncLogger, proving it reaches stdout in prod.

**Forensic consequence (new evidence for the wedge mechanism):** the three
zero-log wedges cannot have been the "80s×2 silent retry arithmetic" — any
goto-timeout retry would have produced [ANTIBOT] lines. Zero lines between
browser acquisition and fence ⇒ `crawler_strategy.crawl` neither returned
nor raised for 180s ⇒ single indefinite hang. Unbounded awaits on that path
(candidates, not chased): context/page-creation CDP roundtrips against a
busy Chromium during ramp launch-churn; the redirect-chain walk
(`await prev_req.response()`, no timeout); hooks. Do NOT re-open a
"log the retries" task off the next wedge — grep FENCE-504 + ADMIT first.

### Verification

- Offline suites: 36/36 (mas_contract 8, admission 10, static_mode 10,
  crawler_pool 4, patchright_fallback 4).
- Local e2e: fence 504 + warning + slot release + normal-request ADMIT all
  confirmed (2s local fence override, reverted; config.yml untouched in git).
- Tier 1 regression vs local server: 4/4 (`--version fence-obs-local`).
- Prod smoke after deploy: see AITOSOFT_CHANGES.md Current State.

### Escalation path (from the plan, still current)

Watch the next MAS batch via FENCE-504 lines. If wedges recur POST-ramp
(replica count stable >2 min) or the rate grows past ~0.4%, escalate to a
code fix — e.g. per-attempt time budget so attempt 2 + patchright can't
exceed the fence remainder, or bounding the hang candidates above.

## Non-goals (parked, revisit only on data)

- Persona-affinity routing to cut browser churn — needs ingress/MAS work,
  not justified by 0.37%.
- Image diet (faster uncached-node pulls would shorten the wedge-prone
  window) — the retry ladder absorbed the ramp fine; MAS observed one
  request needing rung 4 of 4, zero exhaustions.
- MAS-side 5th retry rung — their call, they ship-lean until data says
  otherwise.
