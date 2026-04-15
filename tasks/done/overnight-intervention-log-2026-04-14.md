# Overnight Intervention Log — 2026-04-14 Batch

**Purpose:** Record autonomous actions taken while the user sleeps during the
overnight Talgraf enrichment batch. Referenced at morning handoff.

---

## Intervention 1 — Rolling restart of revision 0000010 (23:39:30 UTC)

**Trigger:** Third memory-pressure backstop fire in 41 minutes AND sustained
>92% on two replicas simultaneously — breached autonomous action thresholds
I had stated in-chat.

**Timeline:**
- 22:57:48 UTC — Fire #1 on `bdvg4` at 86.4%/87.2% (two near-simultaneous)
- 23:28:20 UTC — Fire #2 on `kncpr` at 90.2% (spiked to 94.1% briefly)
- 23:38:42 UTC — Fire #3 on `pd2k5` at 94.9%. Simultaneously `bdvg4` at 94.5%.
- 23:39:30 UTC — Executed `az containerapp revision restart --revision crawl4ai-service--0000010`. Returned "Restart succeeded".
- 23:39:30 UTC — New replica `mhl8s` spawned with fresh template hash `7d57d94ccf` (old pods: `668fb4899`).

**Pre-restart state:**
- All 3 pods had been up 6.8+ hours (since 16:42 UTC scale-up)
- Suspected cause: Chromium process cruft accumulating in long-running browsers (cookies, caches, idle page state)
- Azure-side WorkingSet peaks climbing over 6h: ~3100 MB at 17:00 → ~3500+ MB at 23:00
- Patchright singleton almost certainly past its 100-use recycle threshold but hadn't recycled (recycle only fires when semaphore is fully idle)

**What happens during the roll:**
- Azure brings up new replicas (new template hash) before stopping old ones
- minReplicas=3 means at least 2 old replicas keep serving during rollout
- Each new replica needs ~45-60s to warm up (gunicorn + redis + permanent Chromium init)
- Full rolling restart takes ~3-5 min for all 3

**Expected outcome:**
- Memory drops back to baseline (~65-70% per pod) after roll completes
- Clean Chromium processes, fresh patchright singleton
- Overnight batch continues uninterrupted

---

## Service state summary at intervention time

- Image: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-leak-fix` (unchanged — restart only)
- Scale: minReplicas=3, maxReplicas=20 (pinned during batch)
- Fix 1 firings: ~80 across the 7.5h batch (all clean 180s timeouts on slow/broken hosts)
- Fix 2 force-closes: **zero** (never needed)
- Memory pressure events: 3 total in 7.5h before restart

## If memory pressure returns post-restart

Pre-stated escalation rules continue:
- 3+ fires in 30 min → another rolling restart
- Sustained >92% anywhere → immediate restart
- If a second restart doesn't help within 1 hour, consider: bumping memory to 8 GiB
  (`az containerapp update --memory 8.0Gi --cpu 2.0 --name crawl4ai-service --resource-group aitosoft-prod`), which doubles headroom at zero cost (MS credits).

## If batch goes fine overnight

Morning report will include: companies processed, clean vs timeout vs error counts, memory trend by hour, and note this intervention as a known event.
