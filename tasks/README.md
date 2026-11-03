# Open tasks, in the order to do them

**Updated 2026-11-03.** Each task file carries the concern, the evidence and the design space, and
deliberately no checklist. You're expected to challenge it and record what you found wrong in the
file itself; that has happened on nine consecutive task files, and it is the quality gate that
works. Where a task file and this index disagree, the task file wins.

## State of the world

- **Production is healthy and idle.** It last changed 2026-08-17. Check image, revision, trigger and
  replica bounds with `az` (`AZURE_OPERATIONS.md` §0), never from a document. **`main` ==
  production + docs** as of 2026-11-03. Verify that rather than believe it.
- **No sweep is scheduled.** MAS's last sweep ended 2026-08-16. Since then, traffic has been small
  test batches only (~1,540 requests in 2½ months). That makes now the window for changes that need a
  quiet service.
- **What the last sweep says about priorities.** 186,178 requests over 175 h. Of MAS's 60,874
  capture attempts, 86.1 % were stored and **95 % of failures were the origin's**. Our share, in
  captures lost:
  - 500s: 156;
  - 429s: 29;
  - `render_defect`: 27;
  - `unrenderable_content`: 4.

  Size any new defect against those numbers before investigating it.
- **Cost.** ~$0.605 per hour of sweep (2 replicas) and $0 when idle. **Invoice-verified** to within
  1 % on 2026-08-15/16 (`AZURE_OPERATIONS.md` §4.4). USD, not EUR.

## Open items

| # | Task | Size | Why now |
|---|---|---|---|
| **1** | `upgrade-upstream-v0.9.5.md` | L | 233 upstream commits since our last sync. Two silent behaviour changes MAS depends on: TLS verification turns on, and the `page_timeout` cap drops to 60 s. The service is quiet now, and won't be during a sweep. |
| **2** | The `render_mode` mislabel (no file; one word) | XS | We report a wrong value in a field MAS parses. Do it after #1 ships. |
| **3** | `file-upstream-prs.md` | M | After #1 ships. File the two PRs a maintainer can verify alone. Close #2114 only once upstream fixes #2416. |

**Owed to MAS, not a task file:**
`tmp/mas-repo-messages/54-to-mas-live-config-unchanged-and-14-5-is-now-invoice-verified.md` is
drafted and **unsent**, because Tero asked for quiet in the platform repo on 2026-11-03 while they
deploy. Send it when he lifts that, and before their next sweep. Item 1's MAS heads-up can go in the
same message.

### 2. The `render_mode` mislabel

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
- **Scale-trigger or `render_capacity` changes.** The fleet is at its floor, and loop gain is ~0.45 at
  trigger 12 (`AZURE_OPERATIONS.md` §3.2). Only worth a run if MAS picks the slow-LLM shape (a) from
  `52-to-mas-…`.
- **Memory work.** Closed by two repos independently: `anon` moved +26 MB of 4,096 over 53 h.
  `tasks/done/post-sweep-closure-2026-08-17.md` has the seven closures from 2026-08-17. Read it
  before re-deriving any of them.

## Open threads that need someone else's data

- **53 captures came back with no `<body>` element**, on 28 hosts (`etlistat.fi` ×15). On 26 of the 28
  hosts our consent JS logged nothing, so it is not the cause. That is a real, unexplained mechanism,
  and it is 53 captures. Worth a task only if it grows, or if MAS can hand over the bytes.
- **Text after an inline `<style>`, `<link>` or `<meta>` is dropped from our output today**
  (upstream #2416, verified open 2026-11-03; a maintainer has a fix in progress). lxml keeps the
  following text in the removed element's `.tail`, and the scraper's removal loop discards it. Our
  `strip_noscript` protects only the `<noscript>` case. The size of the loss is unknown, but it is
  cheap to measure on the stored corpus. **Take upstream's fix when it ships, and don't build ours.**
  The upgrade task keeps `strip_noscript` for the same reason.
- **PDF text extraction.** MAS holds April captures with extracted PDF text; today the class returns
  a 174-byte viewer shell. Who caused that is not established (`FINDINGS.md` §Downloads and PDFs).
  Upstream now ships `pypdf` and an opt-in PDF path, which arrive with the merge. Nobody needs it
  yet: MAS removes PDFs at dispatch.

## Reference, not a task

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
- `54-to-mas-…` is a **draft, unsent** (see above).

**Corrections we sent in `50-…`, in case they come back on any of them:**
- The first OOM was 2026-08-13, not 08-15, and it wasn't "two containers": ACA emits two rows per
  kill.
- There were 34 container restarts in the 53-hour window, not 4.
- `az containerapp replica list` *can* see silent restarts, via `restartCount`.
- `unrenderable_content` has fired 12 times.
