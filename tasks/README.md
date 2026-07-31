# Open tasks, in the order to do them

**Updated:** 2026-07-31, after MAS's 243-host re-scrape landed
(`waa-eval-2026-07-30-forensics.md` §10).
**This file holds ordering and gating only** — the reasoning lives in each task
file, the evidence in `waa-eval-2026-07-30-forensics.md`. If they disagree, the
task file wins and this index is stale; fix it.

Production is current (`0.9.2-failure-class`, rev `--0000031`). Nothing below is
a deploy blocker.

**The re-scrape re-ordered this list.** Three items moved down because the fixes
that shipped on 2026-07-30 took most of their value, and three new items moved to
the top because MAS measured defects we did not know about. Read §10 before
trusting any priority written before 2026-07-31.

**Standing rule as of 2026-07-31: live traffic is the last instrument, not the
first.** Every failure class since 2026-04 was diagnosed against a customer's
website, all of it leaving from one shared Azure address that is not contractually
ours, and MAS's requests and our test requests are the same egress. #0 removes the
reason. Tasks #1–#3 were each drafted with live hits and each needs **zero** once
it exists.

| # | Task | Gate | Why here |
|---|------|------|----------|
| 0 | `fixture-origin.md` | none | Small, reusable, and it is what makes #1–#3 cost no live traffic. Our 130 offline tests cover pure functions well and cover *time, navigation and the browser* not at all — which is exactly the set of classes that has been costing us customer-site requests. |
| 1 | `challenge-interstitial-resolve.md` | #0 — **experiment first** | 202 turns out to be the challenge layer's code, and it serves both the interstitial and the real page. If we are capturing the interstitial, 23 of the 31 blocked hosts may come back for free and the proxy question shrinks to 4. Decisive in both directions against a local fixture: falsified ⇒ task closes; confirmed ⇒ a real capture-timing defect worth fixing whatever the vendor is. |
| 2 | `cleaned-html-collapse-guard.md` | #0 | Second silent whole-body loss in a month. The first ran 3½ months across 406 pages at `success: true`. Guard first (generic defence), then enumerate the swallowing family offline — fetch `apteam.fi` only if the enumeration comes up empty. |
| 3 | `detector-round3-evidence-vs-inference.md` | #0 | Eight hosts measured in prod: four blocks missed (every size gate is on `len(html)`; the vendor pads to 80 KB), four invented (including our own error placeholder reported as the origin blocking us). Gates #6. |
| 4 | `post-deploy-measurement-0.9.2-failure-class.md` | MAS's half is **delivered** | What remains is ours: a prod-log census since rev 31. It re-prices #5 and #7 and costs a Log Analytics query. |
| 5 | `static-fallback-within-fence.md` | #4's numbers | Was "high": 180 s for zero bytes. But `done/render-retry-unbounded-hang.md` shipped, so the fence should now fire rarely. Re-derive the rate before spending M on it. |
| 6 | `preflight-batch-endpoint.md` | #3, then MAS's sweep date | Their ~15,000-company sweep is what makes this urgent, and they have already adopted single-URL static as the pre-delete gate — so this is a throughput fix, not a correctness gate. Ask when the sweep is scheduled. |
| 7 | `blocked-host-retry-economy.md` | none | Still real, but smaller: MAS no longer retries origin-class failures, so a blocked host costs ~4 page loads, not ~12–16. Its classifier is still #9's trigger. |
| 8 | `base-config-boolean-defaults-never-applied.md` | none | `simulate_user` has never taken effect and the next boolean won't either. Small. Decide whether the setting should exist at all rather than restoring an intent nobody measured. |
| 9 | `residential-egress-retry-path.md` | **#1's outcome, then Tero** | On hold. The population is 31, not 3 — an order of magnitude more than we told Tero on 2026-07-30. But ≤8 of those may survive #1, and no one on either side has evidence a residential IP gets through. We can now test that for free: the dev container egresses from a Finnish consumer ISP. |
| 10 | `static-mode-tls-impersonation.md` | #1, #9 | Hardens the path #5 makes everything fall back to. IP has dominated fingerprint in every case measured so far; #1 and #9 are what would change that. |
| 11 | `pool-browser-retains-last-page.md` | none | One document's memory pinned per browser. Low impact, but it is why our memory numbers have never been readable. |
| — | `antibot-minimal-text-false-positive.md` | — | **Merged into #3** — the latent defect was observed live (`norex.com`). Close it when #3 ships. |
| — | `file-upstream-prs.md` | upstream | Standing tracker, four PRs open. Small `fix(docker):` PRs merge in 1–5 days; core behavioural changes sit for months — expect no movement. |
| — | `waa-eval-2026-07-30-forensics.md` | — | Reference, not a task. Never close it; task files cite it instead of re-deriving. |

## Cross-repo state

MAS (`aitosoft-platform`) is our only consumer. The exchange is markdown files in
gitignored `tmp/mas-repo-messages/`, numbered and direction-labelled, relayed by
Tero both ways. Durable conclusions get copied into the forensics record; the
messages are the transcript, not the source of truth.

Settled 2026-07-31 (their message 07):

- **Envelope `success`:** flip it to the aggregate, **conditional on the HTTP
  wire status staying 200**. That condition is the load-bearing half. Shipping in
  #3.
- **Their `DEGENERATE_CAPTURE_CHARS = 500` floor is 500 markdown characters**,
  not HTML bytes. The unit hazard is live — we reason in HTML bytes, they store
  markdown. Name the unit every time.
- They now store `cleaned_html` alongside markdown when a capture comes back
  degenerate, which removes the round-trips that dominated 2026-07-30.

Open with MAS (sent in message 08):

- The 202 finding, **before** they roll out a global capture-wait increase.
- Whether a detected collapse should be `success: false` + `render_error` with
  content attached (our default) or something else.
- When the ~15,000-company sweep is scheduled — it paces #6.
- Their observed rate of our 5xx/504 since rev 31 — it re-prices #5 from their
  side while #4 does it from ours.
