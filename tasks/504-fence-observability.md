# Fence-504 observability + ramp-window render wedge

**Status:** Open (created 2026-07-17, spun off from capacity-scaling-redesign
WAA eval cross-check)
**Priority:** Medium — 3/808 requests (0.37%) hit opaque 504s during cold
ramp; contained client-side by MAS's static pivot, but we are blind
server-side and cannot distinguish the two candidate mechanisms.

## Problem

1. **Fence fires are invisible.** `api.py:923-925` raises
   `HTTPException(504, "Crawl exceeded the time limit")` with no log line.
   (The playbook's old "Crawl exceeded 180s … Releasing pool slot" line was
   the 0.8.6-era patch, superseded in the v0.9.2 upgrade.) During the eval
   the three 504s had to be located via RenderGate "admitted after Ns"
   echoes at slot-release time.
2. **Admissions don't log the URL.** Immediate admits log nothing at all;
   queue-wait admits log only the wait duration. No way to map a request to
   a replica unless it queued AND the timing is unambiguous.
3. **Upstream nav-retry loop is silent in server context** (verbose muted):
   a page that times out at goto burns page_timeout × attempts with zero log
   lines. Documented hazard since the 07-16 forensics; still unobservable.

## Evidence (WAA eval 2026-07-17, full detail in
tasks/done/capacity-scaling-redesign-2026-07-17.md)

- 3×504, all fired 14:33:21–14:35:04 UTC — exactly the window when only 6
  replicas served all ~45 concurrent renders (nodes for the other 24 were
  provisioning + pulling the 1.79 GB image). Zero 504s after ramp settled.
- kynnos.fi/yhteystiedot: admitted on 255ps 14:33:32 (10.6s queue wait),
  **acquired hot browser sig=79149154 instantly**, then zero log lines for
  exactly 180s; slot released cleanly at fence (next waiter admitted
  14:36:32.7). Replica healthy on its other slot throughout → per-render
  wedge, not the 07-16 replica-wide starvation.
- teollisuuskatot.fi /palvelut + /referenssit (same-ms fire): 180.2/181.3s
  total ≈ zero queue wait + full fence, same zero-log signature.
- Zero Page.goto-timeout, zero [ERROR] lines → consistent with silent retry
  arithmetic: MAS page_timeout 80s × 2 attempts = 160s + patchright tail ≈
  180s fence. Equally consistent with one indefinite page hang. Can't
  distinguish without the logging below.
- Aggravator: browser-launch churn during ramp (275 creates / 158 closes in
  11 min fleet-wide; one Chromium launch per ~2.7 renders because personas
  spread across all replicas).

## Plan

- [ ] `logger.warning` at the fence except-branch (api.py ~923): URL,
      elapsed, RenderGate snapshot. One line; makes every future 504
      greppable.
- [ ] Log every admission grant with URL (info level, include queue wait —
      merge with the existing queue-wait line).
- [ ] Surface nav-retry attempts: at minimum a counter/log line per retry in
      the render path so 80s×2 burns are visible. Check what upstream's
      retry loop exposes before patching (keep the upstream diff minimal).
- [ ] Offline tests still green; deploy with next image; watch the next MAS
      batch. If wedges recur POST-ramp or the rate grows, escalate to a code
      fix (e.g. per-attempt time budget so attempt 2 + patchright can't
      exceed the fence remainder).

## Non-goals (parked, revisit only on data)

- Persona-affinity routing to cut browser churn — needs ingress/MAS work,
  not justified by 0.37%.
- Image diet (faster uncached-node pulls would shorten the wedge-prone
  window) — the retry ladder absorbed the ramp fine; MAS observed one
  request needing rung 4 of 4, zero exhaustions.
- MAS-side 5th retry rung — their call, they ship-lean until data says
  otherwise.
