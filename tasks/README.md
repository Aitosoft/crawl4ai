# Open tasks, in the order to do them

**Updated 2026-11-04.** Each task file carries the concern, the evidence and the design space, and
deliberately no checklist. You're expected to challenge it and record what you found wrong in the
file itself; that has happened on nine consecutive task files, and it is the quality gate that
works. Where a task file and this index disagree, the task file wins.

## State of the world

- **Production is v0.9.5 on `crawl4ai-service-se` (Sweden Central) since 2026-11-04**, by digest,
  Google Chrome 157; MAS moved there that morning. Since 17:20Z the image is `0.9.5-http-as-asked`:
  two launch switches make Chrome fetch an `http://` URL over http, and stop refusing http-only sites
  (AITOSOFT_CHANGES, two entries). The idle West Europe copy goes when MAS deletes
  it (on or after 2026-11-11). Query the live state with `az` (AZURE_OPERATIONS §0).
- **`main` == production + docs.** Verify it.
- **Two joint runs with MAS found no regression** (`upgrade-upstream-v0.9.5.md` §10).
- **The optimisation loop with MAS is running** (item 1): announced windows on real never-scraped
  prospects, one change each, both sides counting. Three windows ran on 2026-11-04: a baseline,
  MAS's model-host retry fix, and our fleet fixed at 2, which cut cost per request 28 % against
  window 2 and removed the cold-start 429s. We proposed the fixed fleet as the standing setup.
  The ledger is in the task file. Cost per request and per company: AZURE_OPERATIONS §4.5.
- **What the last sweep says about priorities.** 186,178 requests over 175 h. Of MAS's 60,874
  capture attempts, 86.1 % were stored and **95 % of failures were the origin's**. Our share, in
  captures lost: 500s 156 (152 of the 163 URLs failed on every attempt, so deterministic), 429s 29,
  `render_defect` 27, `unrenderable_content` 4. Size any new defect against those numbers before
  investigating it.

## Open items

| # | Task | Size | Why now |
|---|---|---|---|
| **1** | `optimization-experiments.md` | M per lever, ongoing | Tero's standing green light (2026-11-04). The loop, the ledger of levers and effects, and the levers sized. Windows 1–3 ran 2026-11-04; the fixed fleet is now the standing setup. Window 4 ran MAS's 8 in flight on our fixed 2 (0.40 ¢ per company, our cheapest), and `0.9.5-http-as-asked` went live after it. MAS's side is their `task-608`. |
| **2** | The `render_mode` mislabel (no file; one word) | XS | We report a wrong value in a field MAS parses. Below. Deploy it between windows, announced. |
| **3** | `https-connect-failure-http-retry.md` | S–M | MAS asked for it (`115-from-us-…`): 137 companies failed https at the tunnel and stored nothing. A marked `http://` attempt. Ships in its own window after MAS acks the field name. |
| **4** | `file-upstream-prs.md` | M | File the two PRs a maintainer can verify alone. Close #2114 only once upstream fixes #2416. |

**Decided 2026-11-04 (Tero deferred both to us):** the API token in old images is not rotated and the
old tags stay as rollback targets (nothing reached the open internet; `upgrade-upstream-v0.9.5.md` §8
item 5); the 630 raw pages from run (ii) are kept as the offline corpus (`optimization-experiments.md`
§Instruments).

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
- **Scale-trigger or `render_capacity` changes.** The trigger is still not the lever (the scaler is
  burst-driven, AZURE_OPERATIONS §3.2). But "no idle fleet to cut" was retired on 2026-11-04: at 5 in
  flight the fleet lands on 2 or 3 by chance, and cost per request follows it. The lever being tested
  is a fixed fleet (`optimization-experiments.md` lever 2, window 3).
- **Memory work.** Closed by two repos independently: `anon` moved +26 MB of 4,096 over 53 h.
  `tasks/done/post-sweep-closure-2026-08-17.md` has the seven closures from 2026-08-17. Read it
  before re-deriving any of them. Reopen only if a memory stall costs work (AZURE_OPERATIONS §6.4).

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

`upgrade-upstream-v0.9.5.md` (done) and `waa-eval-2026-07-30-forensics.md` stay in `tasks/` because
code comments cite them by path. The second is the evidence base for the five root causes behind the
2026-07-30 image.

## Cross-repo state

The MAS thread is direct, session to session over Remote Control (CLAUDE.md §Cross-repo). Messages
are filed in gitignored `tmp/mas-repo-messages/`; cite filenames, never integers. On 2026-11-04 the
thread was held by MAS's `task-606` session; their follow-up is `task-608`. A session's listed name
changes with its title, so find it with `ListAgents`, or reply to the latest message's `from`.
Nothing is owed to them; our proposal in `110-…` (fixed fleet as the standing setup, then 8 in
flight on the same 2) awaits their answer. The thread is at `110-…` (2026-11-04).
