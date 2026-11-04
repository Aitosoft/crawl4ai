# Open tasks, in the order to do them

**Updated 2026-11-04.** Each task file carries the concern, the evidence and the design space, and
deliberately no checklist. You're expected to challenge it and record what you found wrong in the
file itself; that has happened on nine consecutive task files, and it is the quality gate that
works. Where a task file and this index disagree, the task file wins.

## State of the world

- **Production is v0.9.5 on `crawl4ai-service-se` (Sweden Central) since 2026-11-04 09:12:58Z**,
  deployed by digest, Google Chrome 157. MAS moved every agent there that morning and cloned us; the
  West Europe `crawl4ai-service` is idle on the old image and MAS deletes it on or after 2026-11-11.
  **Every query and command must name `-se`**: a wrong app name reads zero without an error
  (AZURE_OPERATIONS §0). Check image, revision and scale with `az`, never from a document.
- **`main` == production + docs** since the branch was merged on 2026-11-04. Verify it.
- **Two joint runs with MAS found no regression** (`upgrade-upstream-v0.9.5.md` §10): 1,604 requests,
  counts agreed on both sides, the only lost company a parked domain.
- **What's next is MAS's follow-up, `task-608`**: real never-scraped prospects with production
  writes, in announced windows, one change per window. They lead it; we read our side of each
  window (`tmp/research/readout.sh`) and count twice.
- **What the last sweep says about priorities.** 186,178 requests over 175 h. Of MAS's 60,874
  capture attempts, 86.1 % were stored and **95 % of failures were the origin's**. Our share, in
  captures lost: 500s 156 (152 of the 163 URLs got four 500s, i.e. every attempt of MAS's ladder, so
  deterministic, not scale-in), 429s 29, `render_defect` 27, `unrenderable_content` 4. Size any new defect against
  those numbers before investigating it.
- **Cost.** ≈0.05 ¢ per request, flat from August through both joint runs; per company it follows
  pages per company (6.4 in August, 10.5–10.9 on MAS's current brain → 0.33 → 0.52–0.55 ¢). $0 idle.
  AZURE_OPERATIONS §4.5. USD.

## Open items

| # | Task | Size | Why now |
|---|---|---|---|
| **1** | The `render_mode` mislabel (no file; one word) | XS | Unblocked by the deploy. We report a wrong value in a field MAS parses. Below. |
| **2** | `file-upstream-prs.md` | M | Unblocked. File the two PRs a maintainer can verify alone. Close #2114 only once upstream fixes #2416. |
| **3** | Scale-in kills in-flight renders (no task file yet) | S | Seen 2026-11-04: the browsers die at SIGTERM instead of finishing in the 30 s grace, so a scale-in mid-render is a `render_error` 500 (AZURE_OPERATIONS §2.4). Small: 2 of 814 in run (ii); 4 one-off-500 URLs of 163 in August; retries absorb it. Suspected cause Playwright's `handle_sigterm`, unverified. **First verify the mechanism locally** (SIGTERM the server during a stalled `raw://` render) before writing a fix; then the fix may be one launch flag. |
| **4** | Parked-domain detection (an idea, either repo's) | XS–S | fortax.fi (run ii) is a hosting company's parked page (`/cgi-sys/defaultwebpage.cgi`, "verkkotunnus on varattu"), which MAS's agent called `blocked`. A signature check could make it a truthful class. Decide with MAS in `task-608`; size it on their data first. |

**Decisions for Tero (no task files):**
- **1b, the image carried `.env`.** Images up to `0.9.2-capacity-gate-2` contain `/tmp/project/.env`,
  `PRIVATE.md` and `tmp/`; it is also the rollback target, and the West Europe app runs it. Rotate the
  token? Delete old tags once West Europe is gone? Detail: `upgrade-upstream-v0.9.5.md` §8 item 5.
- **The 630 raw pages from run (ii)** (`tmp/research/tailloss-data-2026-11-04/`, gitignored, 37 MB;
  MAS holds a copy too). Keep as the offline corpus for the next upstream merge (630 real pages,
  against the 5 hosts we have), or delete under the "temporarily" ruling? Both repos wait on it.

**Owed to MAS:** nothing. `82-to-mas-where-each-learning-lives.md` (sent 2026-11-04) points them at
the docs.

### 1. The `render_mode` mislabel

In `api.handle_crawl_request`, the exception path's `failed_result(...)` call omits
`render_mode`, which then defaults to `"full"` (`aitosoft_failure_class.failed_result`). The seed
check runs before the static short-circuit, so **a static-mode request to a dead domain is reported
to MAS as `"full"`.** One word, in a field they parse. Find it by name, not by line number: line
numbers in `api.py` drift with every change, and the merge will move them again.

Its sibling is not worth building: static-mode failed fetches log no `failure_class`. That is real in
code, but static mode was used **0 times in 186,178 requests** (MAS confirms: `renderMode: "full"` on
all 61,937 of their rows).

---

## Parked on purpose: don't pick these up unasked

- **CI could run the browser suite on real Chrome.** GitHub's `ubuntu-latest` has Google Chrome
  preinstalled, and `fixture_origin._resolve_channel()` picks it automatically, so a second CI job
  would be the first run of our browser suite on production's browser. Day one it turns
  `pdf-inline` red for the true reason (production's inline-PDF 500), so that test has to change to
  describe reality first. Not done in #1 to keep the merge readable.
- **Dead-browser replacement (upstream `3f9f790`, on develop after v0.9.5).** It replaces pooled
  browsers whose Chromium process died. We lack it, and how often a browser dies in production is
  unmeasured (the 74 restarts in the last sweep were whole-container). It lands in our most-modified
  file and carries a silent trap: an auto-merged janitor block calls helpers that don't exist on our
  side, and the janitor dies without a log. See `upgrade-upstream-v0.9.5.md`. **Make it a task only
  with a measured frequency**, or when the next sync brings it in anyway.
- **`residential-egress-retry-path.md`.** It aims at what actually dominates (blocks are IP-based,
  and Azure's shared SNAT inherits co-tenants' reputation). But it needs an instrument neither repo
  has: a real browser from a residential IP. The one independent 2026 benchmark puts Patchright at 25
  of 31 Cloudflare targets against vanilla Playwright's 24.
- **`guard-corpus-is-not-in-the-repo.md`.** XS. Three tests fail on a fresh clone because
  `test-aitosoft/artifacts/*` is gitignored. It fails loudly, in the safe direction. Commit 4–6 files
  to `artifacts/keep/`, or delete the task. Don't open its sizing table.
- **Tier 1 has drifted.** accountor redirects to `aspia.fi`, jpond.fi no longer obfuscates emails,
  caverna.fi's homepage is a location picker, and the gate checks only ~400 chars and half the
  expected names (`TEST_SITES_REGISTRY.md`). It is a smoke test now, not evidence. Refresh it only
  when a real need for a live gate appears; the fixture origin and `raw://` A/B are the real
  instruments.
- **`test_fingerprint.py` has been broken since v0.9.2** (it sends `js_code`, which gets a 400).
  `test_soak.py` breaks the live-site rules (327 live requests in its stored run). Fix or delete each
  one when someone next needs it; until then, don't run them.
- **The egress proxy may answer with its own 400 on an idle socket.** `_handle` writes `_BAD` when
  an idle client socket times out after 30 s (`egress_proxy.py`). On full Chromium, a stalled
  plain-http navigation once got that 400 and ended as `origin_http_error` after 162.9 s (seen once
  in the upgrade's trial merge, not reproduced; `tmp/upgrade-v0.9.5-evidence/upstream-report-3-trial-merge.md`
  §6.2). Production runs full Chrome. Size it before building anything, e.g. from MAS's data:
  `origin_http_error` with status 400 on plain-http URLs.
- **The response-size backstop and the `colspan` amplifier.** Pathological markup only, and never
  seen in production. The sweep's largest response was 32.6 MB against the 232 MB that lost a customer
  before the `desc` cap (`FINDINGS.md` §Output). Raise its priority if a real instance appears, or if
  OOMs become worth fixing by bounding allocations.
- **Scale-trigger or `render_capacity` changes.** At August's ~19 requests/min the fleet sat at its
  floor of 2; at the joint runs' ~32/min it ran at 3 and tracked the rate, with cost per request flat
  (AZURE_OPERATIONS §4.5). So there is no over-provisioning to remove. Worth a run only if MAS's
  `task-608` changes the request shape a lot (more in flight, more pages per company).
- **Memory work.** Closed by two repos independently: `anon` moved +26 MB of 4,096 over 53 h.
  `tasks/done/post-sweep-closure-2026-08-17.md` has the seven closures from 2026-08-17. Read it
  before re-deriving any of them. **2026-11-04, joint run (i):** one
  replica stalled 55 s out of rotation at `anon` 3.85 GB with six per-company browsers, no kill, no
  lost work (AZURE_OPERATIONS §6.4). Reopen only if a stall costs work; the levers are fewer browser
  identities or 8 GiB replicas.

## Open threads that need someone else's data

- **53 captures came back with no `<body>` element**, on 28 hosts (`etlistat.fi` ×15). On 26 of the 28
  hosts our consent JS logged nothing, so it is not the cause. That is a real, unexplained mechanism,
  and it is 53 captures. Worth a task only if it grows, or if MAS can hand over the bytes.
- **Text after an inline `<style>`, `<link>` or `<meta>` is dropped (upstream #2416, open; a
  maintainer plans one `drop_tree()` fix across ~11 sites).** Measured 2026-11-04 on 630 real WAA
  raw pages: **0 change** (FINDINGS §Parse collapse; harness in `tmp/research/tailloss/`). Take
  upstream's fix when it ships; don't build ours. Re-run the harness on the fix to confirm it.
  We keep `strip_noscript` until then.
- **PDF text extraction.** MAS holds April captures with extracted PDF text; today the class returns
  a 174-byte viewer shell. Who caused that is not established (`FINDINGS.md` §Downloads and PDFs).
  Upstream now ships `pypdf` and an opt-in PDF path, which arrive with the merge. Nobody needs it
  yet: MAS removes PDFs at dispatch.

## Reference, not a task

`upgrade-upstream-v0.9.5.md` is done (2026-11-04) and stays in `tasks/` because code comments cite
it by path; §10 has the deploy and the two joint runs.

`waa-eval-2026-07-30-forensics.md` is the evidence base for the five root causes behind the
2026-07-30 image. Code comments and older tasks cite it by path, so it stays in `tasks/`.

## Cross-repo state

**Since 2026-11-03 the MAS thread is direct, session to session over Remote Control** (CLAUDE.md
§Cross-repo). Messages are filed in gitignored `tmp/mas-repo-messages/`. Cite filenames, never
integers.
- `50-to-mas-…` sat unrelayed from 2026-08-17 until 2026-11-03, when it was sent verbatim. **Don't
  send it again.**
- `51-from-us-…` is MAS's: a slower LLM host for WAA, and does our bill follow pages or wall-clock?
  They number it 50.
- `52-to-mas-…` answers it. The bill follows wall-clock (`$0.605/h × wall-clock ÷ companies in
  flight`), so a slow host is cheap only at ~15 in flight.
- `53-to-mas-…` reconciles their ≈$85/day with our $14.5: those are the trigger-6 and trigger-12
  regimes.
- `54-to-mas-…` and `55-to-mas-…` (the v0.9.5 heads-up, rewritten for the cutover) were sent
  2026-11-04.
- `56-from-us-…` (their 53): the move to Sweden Central, the digest pin, a 161-address egress pool.
- `57-from-us-…` (their 56): the thread is now held by their **task-606 session** (Remote Control
  bridge address in the file). Nothing calls West Europe. Yes to two runs. TLS stays off.
  `scraped_pages.content_hash` hashes raw markdown, so the whitespace change rewrites ~half the pages
  once and loses nothing.
- `58-to-mas-…`: pointed; deploy by digest; one egress address per replica so far; run design
  agreed. At ≈480 requests a run expects ~2 blocks, so 7 or more is a signal.

**Corrections we sent in `50-…`, in case they come back on any of them:**
- The first OOM was 2026-08-13, not 08-15, and it wasn't "two containers": ACA emits two rows per
  kill.
- There were 34 container restarts in the 53-hour window, not 4.
- `az containerapp replica list` *can* see silent restarts, via `restartCount`.
- `unrenderable_content` has fired 12 times.
