# Open tasks, in the order to do them

**Updated:** 2026-07-30, after `0.9.2-failure-class` shipped (rev `--0000031`).
**This file holds ordering and gating only** — the reasoning lives in each task
file, the evidence in `waa-eval-2026-07-30-forensics.md`. If they disagree, the
task file wins and this index is stale; fix it.

Production is current. Nothing below is a deploy blocker.

| # | Task | Gate | Why here |
|---|------|------|----------|
| 1 | `post-deploy-measurement-0.9.2-failure-class.md` | MAS's re-scrape | The only task waiting on someone else, and it sets the size of #2, #6 and #7. Everything else is cheaper to decide after it. |
| 2 | `blocked-host-retry-economy.md` | none | A blocked host costs ~4 page loads to re-prove it is blocked, and the redirect fix just moved a new population onto that path. Its classifier is also the prerequisite for #7 — that decision cannot be made properly until this exists. |
| 3 | `static-fallback-within-fence.md` | none — MAS answered Q1 (b) | Converts our most expensive failure (180 s for zero bytes) into a ~5 s degraded success. Build it on the `failure_class` shape that just shipped. |
| 4 | `preflight-batch-endpoint.md` | none — the detector fix it waited for shipped | Time-boxed by MAS's ~15,000-company sweep: it is the gate that stops that sweep destroying good captures. Slips to urgent the moment they schedule. |
| 5 | `base-config-boolean-defaults-never-applied.md` | none | `simulate_user` has never taken effect, and the next boolean anyone adds won't either. Small fix, but turning it on changes every render on a 2 vCPU replica — measure before shipping. |
| 6 | `static-mode-tls-impersonation.md` | informed by #1 | Hardens the path #3 makes everything fall back to. Lower priority than it looked: IP has dominated fingerprint in every case we have measured. |
| 7 | `residential-egress-retry-path.md` | **#1's numbers, then Tero** | On hold. Sized for 171 hosts; 5/5 probes came back clean (forensics §8d), so the population may be ~3. Do not spend before the re-count. |
| 8 | `antibot-minimal-text-false-positive.md` | none | Latent, no MAS report. Likely merges into the classification work now that Q2 is settled. |
| 9 | `pool-browser-retains-last-page.md` | none | One document's memory pinned per browser. Low impact, but it is why our memory numbers have never been readable. |
| — | `file-upstream-prs.md` | upstream | Standing tracker, four PRs open. No action beyond checking. Small `fix(docker):` PRs merge in 1–5 days; core behavioural changes sit for months — expect no movement. |
| — | `waa-eval-2026-07-30-forensics.md` | — | Reference, not a task. Never close it; task files cite it instead of re-deriving. |

## Cross-repo state

MAS (`aitosoft-platform`) is our only consumer. The exchange is markdown files
in gitignored `tmp/`, relayed by Tero both ways. Durable conclusions get copied
into the forensics record; `tmp/` is the transcript, not the source of truth.

Open with MAS after the deploy note:

- **They re-scrape and report** the 70 `empty_*` and the 171 `challenge_*`.
- **We asked one question:** should envelope `success` become the aggregate?
  Today it stays `true` when the single result failed — matching static mode,
  which they are adopting right now as a pre-delete gate. Their call; it is one
  line in each path.
- **They cannot answer HTML-side questions** about their corpus: `scraped_pages`
  stores markdown only. Landing `cleaned_html` storage is on their roadmap.
  Our `/crawl` response already returns both `html` and `cleaned_html`.
- **Unit hazard:** they measure markdown, we reason about HTML. It has already
  caused one bad inference. Name the unit explicitly every time.
