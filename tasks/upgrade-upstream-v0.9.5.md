# Merge upstream crawl4ai v0.9.2 → v0.9.5

**Status: DONE, 2026-11-04.** Merged 2026-11-03 (`937e100`); deployed 2026-11-04 as `0.9.5-merge`
to `crawl4ai-service-se` (Sweden Central, where MAS had moved that morning), by digest, between two
joint agent runs with MAS that found no regression. The branch is merged into `main`. This file stays
in `tasks/` rather than `tasks/done/` because code comments cite it by path. §8 is the implementation
record, §9 the hand-over, [§10](#10-2026-11-04-the-deploy-and-the-two-joint-runs) the deploy and the runs.
**Size:** L. Mostly reconciliation and verification; the code you write is small.
**Gate:** none to *start*. **Deploying has two gates:**
- MAS must hear about the changes they can see (§5) before the deploy. Tero had asked for quiet in
  the platform repo on 2026-11-03; check with him that it's lifted before messaging them.
- No MAS sweep may be running. Deploy while the fleet is at zero (`AZURE_OPERATIONS.md` §2.4).

**Written by the coordinator. Argue with it.** The evidence below comes from three instruments that
ran on 2026-11-03:
- report 1, a reading of upstream;
- report 2, which verified report 1 by executing against merged trees, and overturned or narrowed
  five of its claims;
- report 3, an independent trial merge with test runs and an old-vs-new server A/B, run without
  sight of the other two.

Where they disagreed, it says so below. **Then a fourth, clean-context reviewer checked this file
itself (2026-11-03), and it changed three recommendations:**
- keep recycling *off*, because upstream has an open deadlock in it (§3.7);
- keep our `strip_noscript`, because upstream's path loses text after a `<noscript>` (§3.7);
- set TLS parity as a module attribute, not an env var, because of test import order (§3.1).

It also corrected several facts. You have a cleaner context than any of them. Re-run what the merge
rests on, and record what you find wrong in this file.

---

## Why now, and why it isn't urgent

- **No hurry, and a free window.** No sweep is scheduled. Production last changed 2026-08-17 and has
  served only small MAS test batches since (~1,540 requests in 2½ months, from Azure Monitor
  daily request totals queried in ≤30-day windows; `AZURE_OPERATIONS.md` §5.1).
- **Not urgent on security.** Upstream published 14 security advisories in v0.9.3–v0.9.5:
  - **twelve** need a caller holding our bearer token, and we have one trusted client;
  - **GHSA-m446** (playground XSS) needs a human to open `/playground` in a browser, which is
    publicly served, but this service has no human users;
  - **GHSA-j2qh**, "TLS verification was off", is passive on-path exposure rather than an attack,
    and for us it is a behaviour MAS depends on (§3.1).
- **The value is less divergence and a better security posture. It fixes nothing MAS sees today.**
  - Upstream's overlay guard and `noscript` handling duplicate fixes we already carry.
  - Its PDF-placeholder fix applies only to `PDFCrawlerStrategy`, so production's inline-PDF 500
    is unchanged.
  - What we do gain: every release we skip makes the next merge larger, and upstream is editing
    exactly our heaviest files (`api.py`, `server.py`, `crawler_pool.py`, `egress_proxy.py`).
    Merging now, in a free window, is cheaper than merging later in a hurry.

## Target: v0.9.5 (`838869b`), not `develop`

`upstream/develop` (`cd61be1`, 2026-11-02) is v0.9.5 + 46 commits. Report 2 classified all of them
(its §4):
- **v0.9.5 already contains every advisory fix and every change MAS would notice.**
- **What develop adds that touches production is one commit, `3f9f790`:** replacing pooled browsers
  whose process died.
  - It lands in our most-modified file and adds a third pool conflict.
  - It brings a silent trap. Its janitor block auto-merges into *our* janitor and calls helpers that
    exist only on upstream's side of the conflict. The janitor is a bare `asyncio.create_task`, so it
    dies on its first tick with no log, and idle-browser cleanup and stuck-browser force-close end for
    the life of the process.
  - Its benefit for us is unmeasured.
  - It deserves its own task, designed against our pool (overflow keys, `_close_detached`,
    `BUSY_SINCE`), and the next sync brings it anyway.
- **Optional cherry-picks onto the v0.9.5 merge.** Report 2 tested that each applies cleanly.
  - `a4c4b2d` + `b0ed23c`: `clone()` keeps six more fields. Free, zero risk, and none matters to
    MAS today.
  - `129a950`: the image build fails loudly if the browser install fails. Build hygiene.
  - `a1bd6c8`: passes the `chromium` channel. **Only together with a decision about
    `pdf-inline`.** It makes our fixture suite run full Chromium, which has a PDF viewer, so
    `test_a_download_is_not_a_retryable_server_error[pdf-inline]` turns red. That red is *true*: it
    reproduces production's known inline-PDF 500 (`FINDINGS.md` §Downloads and PDFs). If you take
    the commit, the test has to change to describe reality, not be skipped.

Report 1 presented the `clone()` fix, the chromium-channel fix and dead-browser detection as part of
the merge. **They are develop-only.** That is one of the claims report 2 overturned.

## The evidence

Saved in gitignored `tmp/upgrade-v0.9.5-evidence/`, because the scratchpad that produced it is
session-scoped:
- `upstream-report-1.md`, `upstream-report-2-verify.md`, `upstream-report-3-trial-merge.md`;
- `scripts/`, `conflicts/` (the conflicted originals, with markers), the `probe_*.json` and
  `rescrape_*.json` outputs, `ab/` (report 3's A/B harness).

To re-run report 2's probes, set `SCR=` to that directory; no paths are hard-coded. Report 2 §0
gives the worktree recipe. Two traps when executing against a second tree:
- Plain `pytest` in a worktree imports the **main checkout's** `crawl4ai` alongside the worktree's
  `deploy/docker`. Use `python -m pytest` or `PYTHONPATH=<tree>`, and print `crawl4ai.__file__` in
  every process.
- Two editable crawl4ai installs (0.8.6 and 0.9.2) are registered in this user's site-packages.

**Conflicts:** 7 files, 25 hunks at v0.9.5. `api.py` has 11, `remove_overlay_elements.js` 5,
`config.yml` 2, `crawler_pool.py` 2, `egress_proxy.py` 2, `server.py` 2 and `.env.example` 1.
`AITOSOFT_FILES.md` "Pre-merge overlap" lists which upstream commit touches which of our files. It
is marked to be deleted after the merge.

**Test results on report 2's mechanical merged tree** (our side of every conflict, plus the fixups
in §3.5/§3.6):
- security suite (what CI runs): pass, matching pure upstream. The only failures were two
  `pypdf`-not-installed ones, and CI installs `pypdf` from the new `deploy/docker/requirements.txt`;
- `test-aitosoft/` offline suite: exactly one failure, `test_mas_contract.py` 90000 → 60000 (§3.2);
- browser fixture suite: 67/67.

**Report 3, the independent trial merge** (develop `cd61be1`, its own throwaway resolution, two
real servers on the same browser binary, MAS-shaped requests). It agrees with report 2 on everything
the two both covered:
- **TLS, executed through the server:** self-signed, expired and wrong-host origins. Main returns
  200 success with the contact email; merged returns 200 `success: false`, `origin_unreachable`.
- **`page_timeout`, also through the server:** a page that stalls 62 s gives 200 in 65 s on main and
  **500 `render_error` after 100 s** on merged, which MAS retries. Each was fixed by its env var
  (`CRAWL4AI_ALLOW_INSECURE_TLS=true`, `CRAWL4AI_MAX_TIMEOUT_MS=180000`) in a third server arm.

Report 3 also found one change report 2 did not: §3.4, the capture point moving 0.5 s earlier.

**Everything else was identical across the arms:** status, `success`, `failure_class`,
`status_code`, `redirected_status_code` and `raw_markdown` (sha-identical). That covers every
consent shape, the five collapse shapes, blocks, downloads, redirect, 404, a dead port, a 645 KB page,
and MAS's prefetch request. Render admission is the same too: 8 concurrent → 6 × 200 + 2 × 429
`render_slots` on both.

Minor deltas:
- failed results +61 B (§3.3);
- `fit_html` keeps nested-noscript content;
- the egress proxy now adds `Connection: close` on plain-http origin requests (an upstream fix);
- `/health` reports 0.9.5.

Suites on report 3's tree:
- pure-function: 5 new failures — the contract test, plus 4 `test_crawler_pool` cases whose fakes
  lack a `crawler_strategy` that develop's dead-browser check reads (develop-only, so irrelevant at
  v0.9.5);
- fixture: 66/67 on full Chromium (`pdf-inline`, §Target), 67/67 on the headless shell;
- security: 343 pass with `pypdf` installed.

---

## §3 Decisions you have to make, with the reasoning I'd want back

Each one is a choice, not a resolution recipe. Several of them change what MAS receives.

### 3.1 TLS verification turns on, and it is the most dangerous change in the merge

**The mechanism.** Upstream `f0ada4c` removed `--ignore-certificate-errors` from every Chromium
launch, and that flag is the *only* reason broken-cert sites render in full mode today
(`tasks/done/tls-broken-cert-regression-2026-07-17.md` predicted exactly this, and so does the
comment at `deploy/docker/config.yml` ~274–282). `egress_broker.enforce_egress` forces
`ignore_https_errors=False` on every request config. After the merge, an expired, self-signed or
wrong-host certificate fails with `net::ERR_CERT_*` → `origin_unreachable` → **HTTP 200,
`success: false`**. MAS reads that as a dead site. The patchright leg inherits the enforced config,
so both legs lose tolerance.

Report 2 executed this against a local self-signed origin: HEAD succeeds and both merged trees fail
with `ERR_CERT_AUTHORITY_INVALID`.

**The lever is `egress_broker.ALLOW_INSECURE_TLS`.** The env var `CRAWL4AI_ALLOW_INSECURE_TLS` sets
it at import. `enforce_egress` reads the module global at *call* time (`egress_broker.py` ~194),
and so does `webhook.py` (we don't use webhooks). `_DANGEROUS_BROWSER_ARGS` strips
`--ignore-certificate-errors` from `extra_args`, so putting the flag in `config.yml` is silently
undone.

**The choice:**
- **(a) Parity.** Set the variable, and behaviour is as today. *My recommendation for this merge*:
  - It keeps the merge behaviour-neutral on the axis MAS can least see. A silently dropped company
    looks exactly like a company with no website.
  - Static mode already uses `verify=False` (`aitosoft_static_mode.py`), so (b) would also make the
    two render modes disagree on the same URL, the "one class, two behaviours by mode" family we
    already paid for once.
  - The exposure it keeps is an on-path attacker between Azure's egress and a Finnish SME's web
    server altering public contact pages. That is real but small for what we do.
- **(b) Verification on.** More correct as a default, and the cost is unknown. **Nobody has
  measured how many MAS targets have broken certificates.** If you want (b), size it first:
  - MAS's archive can answer it;
  - or a static-mode probe over a sample of their domain list, comparing `verify=True` with
    `verify=False`. Static mode is httpx, so it's cheap and needs no browser. It is still live
    traffic, so keep it small and record it.
  - Then take it to MAS as a contract change. Don't let it ride along with a merge.

**Set parity where tests see it too, and not as an env var.**
- **Don't use `os.environ.setdefault` in our code.** Measured in a full `pytest test-aitosoft/`
  collection: `egress_broker` is imported *before* `aitosoft_trust`, because
  `test_egress_dns_offload.py` imports `api` and `egress_broker` at module level. So a broken-cert
  test would pass alone and behave differently in the full run.
- **Do set the module attribute** (`egress_broker.ALLOW_INSECURE_TLS = True`) in
  `apply_trust_relaxations()`. That works whatever the import order, and upstream's own test patches
  exactly this attribute (`test_security_ssrf_egress.py` ~102).
- **Check what flipping a global does to tests that exercise `enforce_egress`.**
- **`supervisord.conf` covers only production.** Never set it on the Container App: no env-var
  changes during a deploy (CLAUDE.md).
- **Also set `ignore_https_errors: true` explicitly in `config.yml`'s browser kwargs.** Upstream
  #2437 (2026-10-22) proposes flipping `BrowserConfig.ignore_https_errors` to default False, and the
  attribute above only stops `enforce_egress` from *forcing* False. *[Corrected 2026-11-03: #2437 is
  a discussion issue ("migrate … default to False (deprecation path)"), open, not a PR.]*

Either way, **pin the decision with a test:** a broken-cert fixture origin whose expected outcome is
whatever you chose. Report 2's `scripts/tls_probe.py` is a working local self-signed origin. The
upstream flag disappeared without any test of ours noticing. Don't let the next flip be silent too.

### 3.2 MAS's `page_timeout` silently drops from 90 s to 60 s

`aitosoft_trust.py` sets `_ac._MAX_TIMEOUT_MS = 180_000`. Upstream replaced that constant with
`_max_timeout_ms()`, which reads env `CRAWL4AI_MAX_TIMEOUT_MS` (default 60,000) on every call. After
the merge our assignment does nothing. `test_mas_contract.py:108` catches it (`assert 60000 ==
90000`), and that test is the only thing that does.
- **Fix:** set the env var. `os.environ.setdefault("CRAWL4AI_MAX_TIMEOUT_MS", "180000")` in
  `aitosoft_trust.py` works here, unlike §3.1, because `_max_timeout_ms()` reads it on every call, so
  import order doesn't matter, and the contract test keeps covering it.
- **Delete the dead `_ac._MAX_TIMEOUT_MS = 180_000` assignment**, so nobody believes it still works.
- **The variable also raises the caps on `wait_for_timeout` and on the newly allowlisted
  `body_visibility_timeout`.** Check you're content with that.
- **New edge:** `page_timeout: 0` now becomes 60,000 even with the env var set (it was 180,000).
  Malformed input deliberately falls back to the default (`61eb573`). MAS doesn't send 0. Check
  `test_mas_contract.py` anyway.

### 3.3 Two changes MAS will see in the bytes

- **Failed results change shape.** `8bd0776` makes a failed `CrawlResult` carry `links: {internal:
  [], external: []}` and `media: {images: [], videos: [], audios: []}` instead of `{}`. **Three of
  our builders emit no `media` at all:** `aitosoft_failure_class.failed_result()`, the static-mode
  failure builder and the static-mode *success* builder (`aitosoft_static_mode.py`). Normalising
  only one would make the shape depend on `render_mode`. The simpler fix is to default
  `links`/`media` once in `server._crawl_response`, which both modes pass through (the same pattern
  as `envelope_extra_for`). Tell MAS.
- **Tables: checked, unchanged.** Upstream's table rework (`dd542e7`) alters `result.tables`, which
  MAS receives. 13 of the 74 corpus captures produce tables, and none changes between HEAD and v0.9.5
  (`tmp/upgrade-v0.9.5-evidence/review/tables/cmp_tables.py`).
- **Markdown gains whitespace.** `c381413` keeps a space where it deletes a whitespace-only
  element. Re-scraping 74 stored real captures: **36 change, every one whitespace-only, +2 to +32
  chars, none over 5 %** (`rescrape_*.json`). Harmless for contact extraction. Tell MAS anyway,
  because anything that hashes or diffs page text will see 36 of 74 pages "change".

### 3.4 Pages are captured 0.5 s earlier, and some come back blank: found only by execution

Report 3 found this; report 2's reading missed it. Upstream `b536bf5` (#2139) merges into **our**
`remove_consent_popups.js` without a conflict, and it makes the snippet's in-page 500 ms "wait for
CMP animations" run only when Phase 1 clicked something or Phase 2 called a CMP API. #2139's purpose
is sound: a CSP `sandbox` directive disables page timers, so an unconditional in-page `setTimeout`
never resolves and the render hangs. The Python-side `page.wait_for_timeout(500)` after the evaluate
stays unconditional on both sides.

The side effect: **MAS's `delay_before_return_html: 2.0` used to mean ~2.5 s after load, and now
means ~2.0 s.** Median shift −0.50 s across 21 successful cases. A page that paints inside that gap
is now captured blank. Tier-3 `minimal_text` inference then calls it blocked, which forces the
anti-bot retry (also blank) and then the patchright leg with its 10 s wait. Measured through the
real server with `fixture_origin`'s existing `/hydrate-after/N`:

| paints at | main | merged |
|---|---|---|
| 2.4 s | 1 navigation, ~3.3 s | 1 navigation, ~2.8 s |
| 2.8 s | 1 navigation, 3.3 s | **3 navigations, 16.1 s** |
| 3.0 s | 1 navigation, 3.3 s | **3 navigations, 16.0 s** |
| 3.3 s | patchright, 17.6 s | patchright, 16.2 s |

On loopback the patchright leg rescued every one, with byte-identical markdown. **On a real host
where that leg fails, a page that succeeds today becomes a failure.** The window is pages that
finish painting between the new and old capture points: about **2.6–3.1 s after navigation start**
on loopback. A page painting at 2.4 s is fine on both. How many real pages fall in that window is
unmeasured. Our existing hydrate tests use paint times outside it, which is why every suite stays
green.

**Options. My recommendation is parity, by (a) or (c):**
- **(a) Driver-side compensation.** When the in-page wait didn't run, add the missing 0.5 s with
  `page.wait_for_timeout`, a Playwright-side timer that a CSP sandbox can't disable, so #2139's hang
  fix survives. It makes the capture point explicit in Python rather than an incidental JS timer. The
  snippet's report has to gain `apiCalled` (today it carries only `accepted`,
  `remove_consent_popups.js` ~858).
- **(c) Resolve that one auto-merged line back to ours.** Zero code, exact parity. For us the
  CSP-sandbox hang is already bounded at 10 s, by `bounded_evaluate(timeout=OPTIONAL_DOM_STEP_TIMEOUT_S)`
  around the consent evaluate. CSP-sandboxed pages are things like GitHub raw and HuggingFace raw,
  not Finnish SME sites. The cost is one more line of divergence in a file we hope to send upstream.
- **(b) Take the 0.5 s saving.** It is ~20 % of a render, but make it a deliberate change told to
  MAS, who can move `delay_before_return_html` to 2.5 if they want the old capture point back.

Whichever you choose, add a `/hydrate-after/2.8`-style test pinning the capture point, so the next
timing shift fails a test instead of passing silently.

### 3.5 `egress_proxy.py`: one correct resolution, and CI rewards the wrong one

| Resolution | Upstream proxy chaining (`890af3d`) | Our 15 s connect budget | Security suite |
|---|---|---|---|
| ours | lost | kept | **2 fail** (`TestUpstreamChaining`) |
| theirs | kept | **silently lost**: `_dial()` hardcodes `timeout=30`, and so does the plain-http dial | passes |
| upstream's code with `self._connect_timeout_s` threaded through both dials | kept | kept | passes |

The natural "make CI green" move silently doubles what a dead host costs a render slot (why 15 s:
`FINDINGS.md` §Egress). Report 2's `scripts/fix_egress.py` implements the third row.
*[Corrected 2026-11-03: worse than stated. Our own suite would not have caught "theirs" either.
`test_connect_timeout_is_honoured` sent `CONNECT slow.example:443`; the proxy dials the request
line's port, so it dialled `127.0.0.1:443`, got connection-refused at once and passed at any budget.
Measured: with every dial set back to `timeout=30`, it still passed. Fixed, plus a four-path test;
all five fail at 30 s now.]* **Add a test
that pins the connect budget on the new dial path**, so the next sync can't lose it unnoticed. Our
off-loop `resolve_and_pin` and close-without-reply-on-`http://` sit outside the conflict and
auto-merge intact. Verify that rather than trust it.

Chaining activates only if `CRAWL4AI_UPSTREAM_PROXY`, `HTTP(S)_PROXY` or `http(s)_proxy` is set.
**None is set on the Container App.** Checked 2026-11-03 with `az containerapp show -n
crawl4ai-service -g aitosoft-prod --query "properties.template.containers[0].env[].name"`: its env
vars are `CRAWL4AI_API_TOKEN`, `ENVIRONMENT`, `LOG_LEVEL`, `MAX_CONCURRENT_REQUESTS` and
`GUNICORN_BIND`.

### 3.6 A mechanical "ours" resolution leaves undefined names

`ruff --select F821` on the ours-resolved tree found these at v0.9.5:
- **`crawler_pool.py`:** `RECYCLE_PAGES` exists only on upstream's side of hunk 1, but the
  auto-merged `init_permanent` uses it. The server won't start. Loud, but only at boot.
- **`api.py`:** `refused` and `_prepend_results` are unbound. Our `_normalize_and_validate_seeds`
  returns a list, while upstream's (`350a141`) returns `(allowed, refused, …)`. Most uses sit behind a
  `deep_crawl_strategy is not None` guard, **but `if refused:` runs on every `/crawl/stream`
  request**, which would raise NameError. MAS doesn't stream; fix it anyway.

**Run `ruff --select F821` (or full `ruff`) over every file the merge touched.** An undefined name
inside code that auto-merged is exactly what no conflict marker shows you.

### 3.7 Other reconciliations, by file

- **`api.py` (11 hunks):**
  - **Read upstream PR #2428 before resolving the seed-check and `egress_proxy` hunks.** It is open,
    and a maintainer tested it positively on 2026-10-22. It is upstream's own version of our off-loop
    `resolve_and_pin` and seed check: a sync `_normalize_and_validate_seeds` returning
    `(allowed, refused)`, wrapped in `asyncio.to_thread`. Shaping ours like it makes the next sync
    quieter, and could later delete that patch of ours outright.
  - Keep: our dead-domain → `origin_unreachable` behaviour, the single-URL guard, `failure_class`,
    the collapse guard, static mode and admission.
  - Take: upstream's `_load_crawler_configs`.
  - Upstream's partial-refusal plumbing is unreachable under the single-URL contract. Bind it or drop
    it; don't leave it half-present.
  - **Upstream's PDF routing** (`_needs_pdf_crawler`/`PDFCrawlerStrategy`) gets dropped by the ours
    side. That isn't an SSRF hole: a global URL validator is installed at boot and checked on every
    hop. But it is less divergence to keep it, and it is the opt-in PDF path a future PDF request
    would want. With `pypdf` now installed, that path is live for any client that opts in, and
    upstream #2460 reports that a PDF scrape thread outlives the Docker deadline. MAS doesn't opt in.
    Know about #2460 before anyone does.
- **`server.py` (2 hunks):**
  - Keep `_crawl_response`, which is MAS's status contract. Upstream's own status work (`130a382`,
    `588de04`) has no failure classification and is a strict subset of ours.
  - Carry over upstream's `_reject_disabled_hooks(...)` and the `hooks.code` → `"ignored"` rewrite.
    Our side drops them, and four upstream legacy-hook tests notice.
  - Accept the auto-merged `init_permanent(get_default_browser_config())` (`7b02a2c`).
    - Whether it makes the permanent browser's signature reachable **depends on the recycling
      decision below.** `init_permanent` signs `_sig(_apply_pool_defaults(cfg))` and our
      `get_crawler` signs `_sig(cfg)`. With recycling at 0, `_apply_pool_defaults` changes nothing
      and the two match; at 200 they don't.
    - MAS always sends a persona, so it rarely matters. Then fix the `config.yml` comment on
      `permanent_unused_ttl_sec` to match.
- **`crawler_pool.py` (2 hunks):**
  - Keep both lines of hunk 1.
  - **Keep recycling off: set `max_pages_before_recycle: 0` explicitly in `config.yml`, and don't
    make `get_crawler` apply `_apply_pool_defaults`.**
    - Upstream `15f4b29` puts `max_pages_before_recycle: 200` in `DEFAULT_CONFIG`, and our
      `config.yml` doesn't set the key, so the deep-merge turns recycling on.
    - Upstream **#2419** (opened 2026-10-19, maintainer-confirmed 2026-10-21):
      `BrowserManager.get_page()` leaks context refcounts when a crawl is cancelled. After a recycle,
      `_maybe_bump_browser_version()` waits forever, and every `/crawl` returns 504 until the
      container restarts. The reporter hit it every 10–14 h.
    - **The trigger is a cancellation, and our `wall_clock_s` fence cancels crawls.**
    - The fix, PR #2432, is open, and `browser_manager.py` is unchanged on develop. Revisit when it
      ships.
    - Don't count on recycling to bound the per-browser memory ratchet either. Upstream replaces the
      *context* inside the same Chromium process, and our measurement says only closing the browser
      resets the floor (`FINDINGS.md` §Browser pool). The benefit is unverified.
- **`remove_overlay_elements.js` (5 hunks):** take upstream's `isDocumentStructure` guard
  (equivalent to ours) and its removal of the 50 ms in-page wait. **Keep our alpha fix**: upstream
  still has `includes("rgba")`. MAS sends this flag `false`, so the stakes are only our divergence.
- **`remove_consent_popups.js`** auto-merges with #2139 (`b536bf5`), and the result parses
  (`node --check`). That auto-merge is the capture-timing change in §3.4. Decide it there.
- **`content_scraping_strategy.py`: keep our `strip_noscript`.** It auto-merges, so keeping it
  costs nothing.
  - Upstream's `unwrap_orphaned_noscript` alone passes every body-survival test, and output on all
    74 real captures is byte-identical either way. That is what first made dropping ours look free.
  - **But upstream's path loses text after a *balanced* `<noscript>`.** `unwrap_orphaned_noscript`
    leaves a balanced element in the tree, and `_scrap` later removes it with `getparent().remove()`
    (v0.9.5 `content_scraping_strategy.py` ~827), which discards the element's `.tail`. Executed:
    `<p>Soita meille <noscript>…</noscript>numeroon 010 123 4567 …</p>` keeps the phone number
    on HEAD, and pure v0.9.5 outputs `Soita meille ` and loses it
    (`tmp/upgrade-v0.9.5-evidence/review/tail_test.py`). Our pre-parse string removal keeps the
    tail.
  - It is upstream **#2416** (2026-10-19). On 2026-11-02 a maintainer said the same pattern exists
    in ~11 places and a fix is in progress. 0 of 74 corpus captures are affected, so the population
    is small, but the loss is silent and it is contact data.
  - #2416 also covers text after an inline `<style>`, `<link>` or `<meta>`. **That loss exists on
    our tree today and isn't changed by this merge.** Note it for MAS, and take upstream's fix when
    it ships.
  - Revisit when #2416's fix lands, and leave #2114 open until then (`tasks/file-upstream-prs.md`).
  - Careful with the browser fixtures. With *both* defences disabled, all 21 noscript/collapse
    fixtures still pass, because Chromium's serialisation plus our collapse-guard recovery cover
    them. They can't tell the two fixes apart, and none has text after a balanced `<noscript>`. Add
    the tail case as a test.
- **`config.yml` (2 hunks):**
  - Keep `wall_clock_s: 180`; upstream moved to 300.
  - Rewrite the TLS tripwire comment, because the predicted event has happened.
  - The comment near the scale-rule notes (~line 241) says the live trigger is 6. It is 12.
- **`supervisord.conf`** auto-merges (upstream changed redis's `--bind` for missing IPv6). Consider
  `CRAWL4AI_NO_CLOUD_NOTICE=1`. Without it, upstream's new `cloud_notice.py` prints a multi-line
  rich banner to stderr daily until 2027-01-01, through the console logger that wraps lines in Log
  Analytics.

### 3.8 The build that ships this also moves the browser stack, and that confounds every before/after

`playwright`, `patchright` and `playwright-stealth` are unpinned (`>=`), and the Dockerfile's
`playwright install chrome` installs whatever Google Chrome stable is current. `az acr build`
resolves all of it at build time:
- Playwright-python was at 1.64.1 on 2026-10-22, against 1.58 in this devcontainer. The 2026-08-17
  production image has whatever was current then.
- So anything that changes in rendering after the deploy is attributable to "upstream merge" *or*
  "new Playwright/Chrome", and you can't tell which.

**Cheapest complete mitigation:**
- **Read the exact versions out of the production image itself.** It uses `CMD` with no
  `ENTRYPOINT` (`Dockerfile` ~242), so
  `az acr run --registry aitosoftacr --cmd 'aitosoftacr.azurecr.io/crawl4ai-service:<current tag> pip freeze' /dev/null`
  prints them, and the same with `google-chrome --version` gives Chrome's. ACR build-log retention
  may not reach back to 2026-08-17, so don't rely on the logs.
- **Build with a constraints file made from that `pip freeze`,** excluding crawl4ai itself; `pypdf`
  and `mcp` aren't in the old freeze, so they stay free. *[Corrected 2026-11-03: `mcp` is in it
  (1.29.0; v0.9.5 only added `<2` to an existing requirement); only `pypdf` is new. And `anyio` can't
  be constrained at all: `deploy/docker/requirements.txt` pins `anyio==4.9.0` while the image ends up
  with 4.14.2, because a later step upgrades it, so either pin fails one step. It is left out.]* That also pins `lxml` (`>=5.3,<7` in
  `pyproject.toml`), whose libxml2 drives the collapse family. Pinning only the three browser
  packages would leave it floating.
- **Chrome stable can't be pinned cheaply,** so record its version from the new image.
- The browser-stack move then becomes its own later, attributable change.

If you decide not to pin, say so in `AITOSOFT_CHANGES.md`, so the post-deploy readout isn't misread.

### 3.9 Smaller behaviour changes worth knowing

- **`OptimizationHints` is no longer disabled** in the launch flags (`5ee5110`). Its memory effect
  is unmeasured. The `raw://` load probe can measure RSS per browser on both trees.
- **More public paths.** `/` and `/monitor` become public redirects (`ffd9a36`). Already public today:
  `/health`, `/token` (which itself requires the API token) and the static UI under `/dashboard`,
  `/playground` and `/static`.
- **Untrusted delays are capped at 60 s.** MAS sends 2.0 s. `raw://` probes that dial render time
  through `delay_before_return_html` cap at 60 s too.
- **`wait_for` / `css_selector` can no longer run page JS** (GHSA-qj46). MAS sends neither.
- **`Connection: close` on plain-http origin requests through the egress proxy** (upstream fix).
  It is more than a header: it ends keep-alive reuse through the proxy, and fixes an existing case
  where a second request on a spliced connection went raw to the first origin. The loopback A/B only
  covered single-origin pages.
- **Not caused by the merge, but it could be blamed on it:** report 3 §6.2 saw, once and
  unreproduced, full Chromium get our egress proxy's own `400 Bad Request` on a stalled plain-http
  request, ending as `origin_http_error` after 162.9 s. `_handle` writes `_BAD` when an idle socket
  times out after 30 s (`egress_proxy.py` ~91, ~105). Production runs full Chrome. If one A/B row
  shows it, it's pre-existing; it's parked in `tasks/README.md`.
- **Log tokens.** No upstream change touches a log token our queries use (report 2 §2.12).
  `Crawl request failed:` is now built only by our `_crawl_response`, because upstream deleted
  theirs.

---

## §4 How to know it worked

The offline suites are necessary but not sufficient. Report 2's whole merged tree passed them with
the TLS change in it, and only an executed probe showed the change. The real gate is **old tree vs
new tree on identical inputs**, and nothing should differ except what you decided to change.
`TESTING.md` §"Before/after comparison (upstream merge)" describes the method: offline suites on
both trees, the fixture origin, two local servers given identical `raw://` bodies, and one Tier 1
pass at the end.

**A ready-made harness:** `tmp/upgrade-v0.9.5-evidence/ab/`, report 3 §5. `bash ab/rerun_all.sh`
does the whole thing: worktrees, merge, resolution copy, corpus copy, a venv with `pypdf`, every
suite, the server A/B, a header echo, the prefetch check, then teardown. `WITH_CD=1` adds a
full-Chromium arm and an env-fix arm.
- It merges `cd61be1`. Change that to `838869b` and drop its `ab/resolved/` copy-in when you're
  testing your own resolution. That copy is report 3's throwaway resolution of develop.
  *[Note 2026-11-03: at v0.9.5 the "full Chromium" arm C does not run full Chromium; `a1bd6c8`, which
  stops `browser_manager` dropping `channel="chromium"`, is develop-only. The implementation ran
  arms A and B by hand against committed trees instead of `rerun_all.sh`.]*
- `SP` defaults to the evidence directory.
- Each server gets its own redis and `CRAWL4AI_ALLOW_INTERNAL_URLS=true`, so it can reach the
  loopback origins.
- `ab/origins.py` builds the broken-TLS origins without touching any trust store.
- `ab/ab_entry.py` wraps `aitosoft_entry:app`, asserts `crawl4ai.__file__`, and overrides the
  `chrome` channel this arm64 box lacks.

Point it at your merged tree. The target is "every row identical except the ones you decided to
change". Add rows for anything you change: `/hydrate-after/2.8` for §3.4, and a broken-cert origin
whose expected result is your §3.1 choice.

Things worth making permanent while you're here, because they turn this merge's hazards into
tests the next merge inherits:
- **CI runs `test-aitosoft/`, and it lands on `main` before the merge commit.** Then the merge's CI
  run shows exactly the merge's failures (the `page_timeout` one, for instance) against a green
  baseline. No workflow runs our suite today; only upstream's security tests run, and only on
  path-filtered pushes.
  - The pure-function subset (251 tests, ~30 s) needs no browser, but four tests need the gitignored
    `test-aitosoft/artifacts/` corpus. Make them skip when it's absent, or CI is red on day one.
  - Use Python 3.12, which is what production runs (`Dockerfile` line 1). Upstream's security
    workflow uses 3.10.
- the broken-cert fixture (§3.1);
- the connect-budget test on the new dial path (§3.5).

Tier 1 is a smoke test, not evidence of quality (CLAUDE.md §Testing). Don't let a 4/4 stand in for
the A/B.

## §5 Deploy, and MAS

**MAS-visible changes**, to send them before deploying:
- the TLS decision;
- `page_timeout` preserved (assuming §3.2 is done);
- the capture-point decision (§3.4);
- the failed-result `links`/`media` shape;
- the markdown whitespace change, with the 36-of-74 number;
- the browser-stack versions, if they moved.

Draft it as a numbered file in `tmp/mas-repo-messages/`, cite filenames, and send it over Remote
Control once Tero confirms the platform repo's quiet period is over. Also still unsent:
`54-to-mas-live-config-unchanged-and-14-5-is-now-invoice-verified.md`. Send that first, or fold it
in.

**Deploy:**
- `./azure-deployment/deploy-image.sh <tag>`, while the fleet is at zero. A revision change kills
  in-flight renders (`AZURE_OPERATIONS.md` §2.4).
- Run the post-deploy smoke from `TESTING.md`. It includes a made-up domain for the
  `origin_unreachable` path, which is what caught the 2026-08-05 `NameError`.
- **Rollback is image-only.** Never touch env vars.

**After deploy, read MAS's first real batch against the August baseline**
(`tmp/mas-repo-messages/49-data/` is the only surviving per-request record; Log Analytics keeps 30
days):
- `origin_unreachable` rate, the TLS canary even with parity;
- render-time p50/p99, for Playwright/Chrome and `OptimizationHints`;
- browser launches per admit, and memory.

**Then archive that batch's aggregates before the 30 days expire** (`OVERNIGHT_PLAYBOOK.md`).

## §6 Things I talked myself out of

- **Targeting develop "to be current".** It buys one production-relevant commit with a silent trap
  in our most-modified file. See above.
- **The v0.9.2 technique (`merge -s ours`, then `checkout upstream/develop -- .`, re-apply
  patches).** It was right then because a formatter had touched ~90 upstream files. Today our tree is
  byte-identical to upstream outside the real patches (`AITOSOFT_FILES.md` §5), so an ordinary merge
  keeps our patches. A wholesale re-apply would put each of them at risk of being lost by hand.
- **Turning TLS verification on now, "because it's a security fix".** That's the right instinct with
  the wrong instrument. It silently converts an unknown number of real companies into "dead site"
  at 200, and nobody would notice. Decide it with a number.
- **Pinning Chrome as well as the Python packages.** `playwright install chrome` takes current
  stable, and pinning it means owning a `.deb`. Recording the version is enough to attribute changes.
- **A broad live regression to "be sure".** Live traffic is the last instrument. The A/B on `raw://`
  and the fixture origin is byte-identical across arms, and a third-party site is not.
- **Dropping `strip_noscript` to cut ~70 lines of divergence.** The first draft of this file
  recommended it, on the evidence that the 74-capture corpus was byte-identical either way. The
  review found the case the corpus doesn't contain: text after a balanced `<noscript>`. That is
  silent contact loss. "Byte-identical on our corpus" was true and wasn't enough.
- **Turning recycling on "to bound the memory ratchet".** The first draft called it low stakes. It
  isn't: it switches on a confirmed upstream deadlock (#2419), and the ratchet benefit is
  unverified.
- **Waiting for v0.9.6.** There is no tag or milestone yet (develop still says 0.9.5, and releases
  came 2026-08-31, 09-23 and 10-14). Two fixes we'd want are open upstream: #2432 (the recycling
  deadlock) and #2416 (noscript tail loss, a wider MAS-visible markdown change than the whitespace
  one). Going ahead now is still right. The window is free now and may not be then, and §3.7 keeps
  recycling off and our `strip_noscript`, so neither open bug reaches us.
- **Folding `3f9f790` (dead-browser replacement) or the `render_mode` mislabel into this merge.**
  Both are real, and both would make the merge's before/after harder to read. The mislabel is item 2
  in `tasks/README.md` and is a one-word change you're welcome to make *after* the merge is proven.

## §7 What I am least sure of

1. **That parity is the right TLS call.** I argued it from asymmetry (an invisible loss vs a small
   exposure) without a number for either side. If MAS can count broken-cert targets cheaply, that
   number should decide it, not my argument.
2. **The real `api.py` resolution.** Every merged-tree result above comes from a mechanical "ours,
   plus minimal fixups" resolution. A different resolution of its 11 hunks can surface things these
   didn't.
3. **Production's browser.** Nothing ran on Google Chrome or Playwright ≥1.6x; this devcontainer is
   arm64 and Chrome has no arm64 build. TLS behaviour shouldn't depend on the version, but nobody has
   confirmed it on Chrome.
4. **`noscript`.** Keeping ours sidesteps it for now. But in 2026-07 production had 406
   noscript-collapse pages on 70 hosts, and our stored corpus has no unbalanced page and no text
   after a balanced one. So neither fix has been measured on the real shapes.
5. **How many real pages paint in the ~2.6–3.1 s window (§3.4).** It's proven on loopback and
   unmeasured on real hosts. Parity makes the number not matter for this merge, which is why I
   recommend it.
6. **That #2419's deadlock reaches us.** I reasoned it from the trigger (a cancelled crawl, which
   our fence produces); I didn't reproduce it. Keeping recycling at 0 is parity with today, so the
   recommendation doesn't depend on being right about this.
7. **Whether anything in MAS hashes or diffs page text.** If it does, the whitespace change matters
   more than its 2–32 characters.

---

## 8. Implementation record (2026-11-03)

Written by the implementing session, which did not write §§1–7. The coordinator's text above is left
as written, apart from the dated *[Corrected]* notes where a claim was wrong.

### What was done

- **`main` first:** `f203391` adds `.github/workflows/aitosoft-tests.yml` (Python 3.12, every push and
  PR, the offline half of `test-aitosoft/`). The four corpus tests carry a `requires_corpus` marker
  and skip **only** when the corpus is absent *and* `CI` is set; a fresh local clone still fails them
  loudly (the guard-corpus task's safe direction). CI on `main`: 246 passed, 5 skipped, Python 3.12.15
  (run 41634199768).
- **Branch `upgrade-upstream-v0.9.5`:** `937e100` merges `838869b` (no cherry-picks); `3b6b2a1` adds
  `.dockerignore` (below). The branch is pushed; CI runs our offline suite on it. Upstream's
  `security.yml` runs only on pushes to main/develop or on a PR, so on the branch it was run locally.

### Decisions, against §3

| § | Choice | Note |
|---|---|---|
| 3.1 TLS | **(a) parity** | `egress_broker.ALLOW_INSECURE_TLS = True` in `apply_trust_relaxations()`; `ignore_https_errors: true` in `config.yml`. Pinned by `test_a_broken_certificate_still_renders` and its control `test_the_broken_certificate_origin_really_is_broken` (verification on → `ERR_CERT_*`, `origin_unreachable`, 0 GETs at the origin). The fixture's leaf is self-signed, expired *and* wrong-host at once. Flipping the global affected no other test. |
| 3.2 timeout | as recommended | `setdefault("CRAWL4AI_MAX_TIMEOUT_MS", "180000")`, dead assignment deleted. |
| 3.3 shapes | as recommended | `normalize_result_shapes()` in `aitosoft_failure_class`, called once from `server._crawl_response`. Static-mode successes gain `media` too. |
| 3.4 capture | **(c)** | Only the conditional line reverted; upstream's `apiCalled` bookkeeping kept, so the next sync conflicts on one line. (a) would add code to two upstream files for a hang `bounded_evaluate` already caps at 10 s. Pinned by `test_the_capture_point_includes_the_consent_wait` (`/hydrate-after/2.8`); negative control: with the conditional restored it fails twice in a row ("captured blank and rescued by a retry"). |
| 3.5 egress | third row | Budget threaded into both `_dial()` dials and the plain-http `dst` dial. The upstream-proxy CONNECT *reply* wait stays upstream's 30 s (chaining is off here). |
| 3.6 names | checked | `ruff --select F821,F811,F823` over all 54 touched production files: no finding that isn't already in pure v0.9.5 or in HEAD. |
| 3.7 api.py | see below | Seed check stays **async** (not #2428's sync-plus-`to_thread` shape): with the sync shape, upstream's v0.9.5 `test_every_crawl_handler_validates_destination` fails until #2428 merges, unless we edit an upstream test. It now returns upstream's `(allowed, refused)` with upstream's partial refusal and our dead-domain branch inside. Upstream's PDF routing kept. |
| 3.7 rest | as recommended | Hooks carry-over; recycling off; overlay JS reconciled; `strip_noscript` kept with a new tail test (control: neutralising `strip_noscript` fails it); `config.yml` comments; cloud notice off via `os.environ.setdefault` in `aitosoft_entry` rather than `supervisord.conf`, so tests and local servers get it too. |
| 3.8 pinning | constraints | `azure-deployment/pip-constraints.txt` = `pip freeze` of the production image `0.9.2-capacity-gate-2` (read with `az acr run`) minus crawl4ai and anyio; `ENV PIP_CONSTRAINT` in the Dockerfile. Production's stack, read from the image: playwright 1.62.0, patchright 1.61.2, playwright-stealth 2.0.3, lxml 6.1.1 (libxml2 2.14.6), Google Chrome 151.0.7922.137, Python 3.12.14. |
| Target | v0.9.5, no cherry-picks | `129a950` adds little for us (our Dockerfile's own `playwright install` steps already fail loudly); the `clone()` pair is free but makes "we are at v0.9.5" untrue. All arrive with the next sync. |

### Evidence (re-runnable; outputs copied to gitignored `tmp/upgrade-v0.9.5-evidence/implementation/`)

- **Suites on the merged tree:** offline 256/256 (251 + 5 new; 262 after the review's 6 pins); fixture origin 70/70 (67 + 3 new,
  headless shell, arm64); security 343 + 1 xfail (venv with `pypdf` 6.21.4); upstream's non-security
  docker tests 102 pass, 5 fail, all deliberate (single-URL 400 ×2, recycling off ×3).
  `test_stream_crawls_allowed_seeds_and_reports_refused`, red in report 3, passes now because of the
  partial-refusal choice.
- **Server A/B** (report 3's `ab/harness.py`, arms run by hand: A = `main` `f203391`, B = `3b6b2a1`,
  same venv, same `chromium_headless_shell`, each asserting its own `crawl4ai.__file__`): 40 cases.
  Status, class, success, markdown length and timing identical on every row, including
  `hydrate-after/2.8` (3.200 / 3.202 s), all three broken-TLS origins (200, `none`, 357 chars) and the
  62 s stall at `page_timeout: 90000` (65.2 s both). The deep diff, timing fields excluded, shows only:
  keyed `links`/`media` on 4 failed results and on static success; `fit_html` keeping nested-noscript
  content; `Date` headers. `raw_markdown` is identical everywhere. Header echo: only
  `Connection: close` differs. Prefetch shape: links sha-identical, +37 B.
- **Browser memory,** same workload, after the harness: 181 MB PSS on both arms (2 browsers each).
  Headless shell, so it says nothing about `OptimizationHints` on Chrome; it only rules out a gross
  change.
- **Corpus:** 36 of 74 captures change, all whitespace-only, +2 to +32 chars, max 0.06 %, image counts
  identical, which reproduces report 2. Tables tree-against-tree: 13 of 74 captures have tables, 0
  differ. (First attempt read `ScrapingResult.tables`, got "0 have tables, 0 differ", and would have
  passed as confirmation. They live at `result.media.tables`.)

### What this file got wrong or left out

1. **§3.5:** the existing connect-timeout test was decorative (inline correction above). It is the
   one finding here that would have survived every suite.
2. **§3.8:** `mcp` is in the old freeze; `anyio` can't be constrained (inline correction).
3. **§3.1:** #2437 is a discussion issue, not a PR (inline).
4. **§4:** the harness's full-Chromium arm doesn't exist at v0.9.5 (inline).
5. **Not covered anywhere: the image carried our secrets.** There was no `.dockerignore`, and the
   Dockerfile does `COPY . /tmp/project/` from the working tree. Checked with `az acr run`:
   `0.9.2-capacity-gate-2` contains `/tmp/project/.env` (the API token), `.env.txt`, `PRIVATE.md`,
   `tmp/` and `test-aitosoft/artifacts/`. ACR has anonymous pull off (admin user on), so the readers
   were Azure principals who can already read the Container App's plain env var: not a public leak.
   `3b6b2a1` adds `.dockerignore`. **Older tags still contain the files, and they are the rollback
   targets**, so deleting them is Tero's call, and so is rotating the token (rotation is an env-var
   change plus a MAS hand-over, neither of which this session may do).
6. **Pre-existing, not merge-caused:** `max_pages_before_recycle` is in the untrusted allowlist (it was
   at v0.9.2), so `config.yml`'s 0 governs only the default; a client could opt a browser into the
   #2419 path. MAS doesn't send it.
7. **Upstream moved:** develop is at `627461c` (#2417, `PruningContentFilter` inline text, i.e.
   `fit_markdown` only) since this file was written. It doesn't touch the target.
8. **The permanent browser** (§3.7): with TLS parity, `enforce_egress` no longer flips
   `ignore_https_errors`, so besides `_apply_pool_defaults` being a no-op, the signatures can now
   actually match: a request with no `browser_config` and the internal `/html`, `/screenshot`, `/pdf`
   calls can use it. MAS's persona configs still can't. Comments in `config.yml`, `crawler_pool.py`
   and `test_crawler_pool.py` updated.
9. **Tooling trap:** `gh run list` with no `-R` answers for **upstream** in this checkout (no default
   repo is set). Always pass `-R Aitosoft/crawl4ai`.

### Deviations from this file's recommendations

- Corpus tests skip only under `CI`, not "when absent" (reason above).
- Cloud notice off in `aitosoft_entry`, not `supervisord.conf`.
- Seed check kept async rather than shaped like #2428 (reason above).
- `.dockerignore` added on the branch: not asked for, security hygiene, no behaviour change.

### Build note (candidate image, not deployed)

`az acr build … --image crawl4ai-service:0.9.5-candidate` from `3b6b2a1` (+ docs), 2026-11-03
13:00–13:10 UTC, ACR run `cb1q`, digest `sha256:2fdddd05…`. No Container App change. The tag stays in
ACR but is **not the deploy artifact**: `deploy-image.sh` rebuilds, so re-read Chrome's version from
the image that ships (Chrome stable may have moved again). Read back with `az acr run`:
- **Python packages: identical to production's freeze** except `anyio` 4.14.2 → 4.16.0 (floats, as
  documented in the constraints header) and the new `pypdf` 6.21.4. Playwright browser caches are the
  same builds (`chromium-1228/1234`).
- **Google Chrome 151.0.7922.137 → 156.0.8078.79**, and the base image's Python 3.12.14 → 3.12.16.
  Chrome is the one stack component the constraints can't hold. It moves five majors in this deploy,
  under the old Playwright 1.62.
- `/tmp/project/` no longer has `.env`, `.env.txt`, `PRIVATE.md`, `tmp/`, `test-aitosoft/artifacts/`
  or `.claude/` (`.dockerignore` works). `PIP_CONSTRAINT` stays set in the runtime env; nothing
  pip-installs at runtime.
- **Our suites inside that image, on real Chrome 156** (`az acr run`, as `appuser`, `CI=true`,
  loopback fixture origin only): offline 251 passed + 5 skipped; **fixture origin 69/70**. The one
  failure is `pdf-inline` (`Blocked by anti-bot … minimal_text, 356 bytes`), the production inline-PDF
  500 that §Target predicted for any real-Chrome run. TLS parity and its control, the capture-point
  test and every other route pass on Chrome. This is the first time our browser suite ran on Google
  Chrome.
- **Second instrument for `pdf-inline`:** the same suite inside the *production* image
  (`0.9.2-capacity-gate-2`, Chrome 151, its own August tests). The first attempt errored 64 times on
  `PermissionError: /tmp/project/.env` (python-dotenv, run as `appuser`): the baked-in `.env` again.
  Rerun from a copy without it: **66/67, the same single `pdf-inline` failure.** So that red is
  production's today on Chrome 151 and not caused by the merge, and every other route passes on both
  images (the candidate's 69/70 is those 66 plus the 3 new tests).

### Independent review (clean context, 2026-11-03)

It ran its own worktrees (offline 256/256, fixture 70/70, security 343 + 1 xfail, negative controls
on the egress, capture-point, TLS and noscript tests) and found **no correctness bug in the
resolutions**. Its findings, and what was done:

1. **Chrome 151 → 156 ships with the merge, under Playwright 1.62: an untested combination.** Done:
   the suites ran inside the candidate image on Chrome 156 (above). The Dockerfile comment, which
   claimed "a code change and a browser-stack move never ship in one build", is corrected, and so is
   MAS draft §4 ("post-deploy deltas may be Chrome's"). Pinning Chrome via a `.deb` or copying
   `/opt/google/chrome` from the old image was considered and not done: the suite passes on 156,
   Chrome stable would have moved at the next rebuild anyway, and owning a browser binary is a
   maintenance bill for a variable we can now test.
2. **TLS parity, recycling-off, the capture point and the shape normalisation were invisible to
   CI.** It removed all four and the offline suite stayed green. Done: offline pins in
   `test_mas_contract.py` (`test_tls_tolerance_survives_enforce_egress`,
   `test_browser_recycling_stays_off_by_default`, `test_consent_wait_stays_unconditional`,
   `test_failed_results_carry_keyed_links_and_media`), each with a negative control run here. CLAUDE.md's
   pre-deploy line now says the browser suite is part of "the offline suites".
3. **§8's "checked by building it" was written before the build finished.** True; the build note is
   above now.
4. **A render slot leaks if the crawler release raises** (the PDF path's new `close()`, or
   `release_crawler`). Done: inner `try/finally` in `handle_crawl_request`, pinned by
   `test_the_capacity_slot_is_released_even_if_releasing_the_crawler_raises` (negative control run).
5. **Falsy fields in upstream's new `UNTRUSTED_GLOBAL_FORBIDDEN_FIELDS` became 400s.** Verified by
   execution on both trees: `main` drops `{"downloads_path": null}`, `{"save_images_locally": false}`,
   `{"image_save_dir": ""}`; the merge rejected them. MAS's audited payloads don't send them, but it
   narrowed the relaxation's own contract. Done: the tolerant filter prunes the global set too;
   `test_falsy_global_forbidden_fields_are_dropped_not_rejected`. Also noted, not changed:
   `crawler_configs` with a single URL is now honoured (it was ignored); MAS sends none.
6. **Unmeasured: `OptimizationHints` on Chrome, `Connection: close` on multi-origin plain-http
   pages.** Recorded; the MAS draft now says "not expected, unmeasured beyond single-origin pages".
   MAS draft §3 tables: now "unchanged on our 13 pages", with upstream's `<th>`/rowspan rework named.

### What I am least sure of

1. **Production's browser, at full scale.** The suite on Chrome 156 is loopback fixtures: no real
   anti-bot vendor, no real CMP, no real fonts or third-party scripts. Chrome 156's fingerprint
   against Cloudflare et al. is untested, and blocks are the largest failure class. Watch
   `origin_blocked` and the patchright-rescue rate in MAS's first batch as well as
   `origin_unreachable`; if they move, suspect Chrome before the merge.
2. **The capture-point test's margin** is ~0.2 s on each side on loopback. It passed on arm64 and on
   ACR's amd64 with Chrome 156, but a slow runner could flake it. If it flakes, widen the paint time
   toward 2.9 s; don't delete it.
3. **The `.env` in old images.** Not a public leak (ACR has anonymous pull off), but every
   `aitosoftacr` puller has had the token, and those images remain the rollback targets.

---

## 9. Hand-over: deploy, then the first joint agent runs (for the session after 2026-11-03)

Written at the end of the implementing session for a peer with a clean context. Not a checklist;
the reasoning is above and in the docs it points to.

**Where things stand.** The merge and its fixes are on branch `upgrade-upstream-v0.9.5` (pushed;
CI green at `9936679`). `main` is still production plus CI, so **work from the branch**, and merge it
into `main` only once its image is the one running. It should be a fast-forward. Production is
`0.9.2-capacity-gate-2`; confirm that with `az` (AZURE_OPERATIONS §0), not from here.

**Before the deploy:**
- Tero confirms the platform repo's quiet period is over.
- Send `54-…`, then `55-…`, to MAS's session (CLAUDE.md §Cross-repo: `ListAgents`, `SendMessage`,
  file both directions). Re-read 55 first; it was written before anyone knew the experiment plan,
  so adjust it to what you actually agree.
- No MAS batch is running, and the fleet is at zero (AZURE_OPERATIONS §2.3, §2.4).

**The deploy:**
- `./azure-deployment/deploy-image.sh <tag>` and nothing else. Never env vars; rollback is
  image-only to `0.9.2-capacity-gate-2` (§2.5, which also says why not `0.9.5-candidate`).
- The script rebuilds, so read the shipped image's Chrome version (AZURE_OPERATIONS §2.6) and tell
  MAS. `0.9.5-candidate` had 156.0.8078.79.
- Post-deploy smoke and SSRF negatives: TESTING.md §Quality gates. One optional extra is cheap and
  third-party-free: the suites inside the shipped image (TESTING.md §"Inside a built image"); expect
  69/70 with only `pdf-inline` red.

**The joint runs: divide by what each side can see** (CLAUDE.md §Cross-repo).
- **We see:** inside the browser, the pool and the admission gate, from Log Analytics
  (AZURE_OPERATIONS §5; 30-day retention, so archive the aggregates).
  - Count failures by the `failure_class=` field on `RESULT`/`ORIGIN`/`TERMINAL FAILURE` lines plus
    `RENDER DEFECT`, never by one token.
  - Watch: `Anti-bot retry` and patchright rescues, `COLLAPSE RECOVERED`, render time,
    `capacity_gate` on 429s, browser launches, memory.
- **MAS sees:** what was stored, which pages came back empty or wrong, what the agent decided, and
  whether a company lost work. Their August client-side record is `tmp/mas-repo-messages/49-data/`
  (61,937 requests, hourly latency percentiles and status counts), the only per-request baseline
  that survives.
- **Count the headline numbers on both sides; a disagreement is the finding** (CLAUDE.md principle
  8).

**What to be suspicious of** (§8 "What I am least sure of"):
- **Chrome moved five majors with this deploy.** Its fingerprint against real anti-bot vendors is
  the untested part. If `origin_blocked`, the anti-bot retry rate or patchright's rescue rate moves,
  suspect Chrome before the merge. The way to separate them, if it matters, is the old image vs the
  new on the same small URL set, recorded in `TEST_SITES_REGISTRY.md`.
- **`origin_unreachable`** is the TLS canary. TLS tolerance is pinned, but only on loopback.
- **The capture point:** pages painting 2.6–3.1 s after load. MAS's "newly empty pages" is the
  instrument that would catch a miss.

**Live traffic:** MAS's agent runs are production traffic and fine. Our own probes of third-party
sites stay at the CLAUDE.md §Testing rules (1–2 hits per host per session, recorded).

**After the runs:** this file moves to `tasks/done/` once the deploy is proven, and `tasks/README.md`
gets the next ordered list. Already queued:
- the `render_mode` mislabel (README item 2);
- the PRs (`file-upstream-prs.md`);
- the image-secrets decision (README item 1b, Tero's);
- the parked browser-suite-in-CI idea.

---

## 10. 2026-11-04: the deploy and the two joint runs

Written by the deploy session. §9's plan was right in outline and wrong in three places, all found
before or during the deploy.

**What §9 got wrong, and what settled each:**
1. **The deploy target.** MAS had moved every agent to Sweden Central at 06:01–06:18Z and cloned us
   as `crawl4ai-service-se`; §9 says `crawl4ai-service`. Found by `az containerapp list` before
   sending `55-…` (a faithful clone: same digest, token, scale rule, probes, env names), then
   confirmed by MAS (`56-from-us-…`, `57-from-us-…`). Tooling repointed in `cd9c4af`; deploys go by
   digest now, because MAS pinned the app to one.
2. **"Two changes in one deploy" was three.** The region change means a new egress address (the app
   lists 161; one replica used one), and our blocks are IP-based. So the plan became two runs, one
   change each (`58-to-mas-…`): (i) the region alone on the old image, then deploy, then (ii) the
   merge and Chrome.
3. **Chrome 156 was 157.** The rebuild picked up 157.0.8103.38. Our suite had never run on it, so
   it ran inside the shipped image before run (ii) was released: 326 passed, 1 failed (`pdf-inline`,
   known).

**The runs** (75 companies each, 5 in flight, MAS's brain DeepSeek V4.1-Flash-1017 on Wafer, held
identical; counts agreed request for request on both sides):

| | (i) v0.9.2, Chrome 151, `-se` | (ii) v0.9.5, Chrome 157, `-se` |
|---|---|---|
| requests | 790: 736 × 200, 54 × 429 | 814: 761 × 200, 51 × 429, 2 × 500 |
| lost work / newly empty (MAS, vs August) | 0 / 0 | 1 / 2, all the sites (below) |
| our failures | 3 unreachable, 1 http_error | 1 unreachable, 1 http_error, 2 `render_error` |
| blocks | 0 terminal; 2 CF challenges rescued | 0 terminal; 1 rescued |
| 200 latency mean / p99 | 8.06 / 44.6 s | 7.42 / 18.0 s |
| peak `anon` | 3.85 GB; one 55 s readiness outage | 2.8 GB |
| ¢ per request / company | 0.049 / 0.52 | 0.050 / 0.55 |

- **The 2 × 500 are a scale-in killing a replica mid-render** (AZURE_OPERATIONS §2.4), not the merge.
- **The newly empty pages and the lost company are the sites:** one request each through the idle
  West Europe app (old image) and `-se` (new) returned byte-identical pages. fortax.fi is now a
  hosting company's parked-domain page; suujahammas.fi/ajanvaraus redirects to a booking app.
  Recorded in TEST_SITES_REGISTRY.
- **Latency and memory improved in (ii)**, but the cohorts differ: suggestive, not measured.

**The gates, and two deviations.** Offline 262/262 and fixture origin 70/70 locally before the
deploy; smoke and SSRF negatives green after. **Tier 1 ran against the deployed `-se` image, not
from the devcontainer** (its egress is Tero's home connection): 3/4 by the script, 4/4 in
substance, the miss being site drift (aspia.fi's expected contact is gone from the raw HTML; the
expectation is updated). **The byte-compare was replaced** by the suite inside the shipped image.

**What the runs taught, and where it now lives:**
- cost per request is flat, so cost per company follows pages per company: AZURE_OPERATIONS §4.5;
- the 429 split and the parallel-scrape cold start: §3.8;
- scale-in kills in-flight renders: §2.4;
- a replica stalled by memory without a kill: §6.4;
- egress pool, two apps, the KQL-name trap: §0, §7;
- requests orphaned during the revision switch: §2.4, TESTING §Quality gates;
- #2416 is 0 of 630 real pages: FINDINGS §Parse collapse;
- two method lessons (a positive result is about the patch first; diff the line, not the version):
  FINDINGS §Method lessons.

**What I am least sure of:**
1. **That Playwright's `handle_sigterm` is what kills the browsers at scale-in.** Inferred from
   supervisord having no `stopasgroup`; not reproduced.
2. **That (ii)'s lower memory is Chrome 157's.** Different companies, different pages.
3. **Two runs of 75 companies see only gross moves.** At August's block rate a run expects ~2;
   both had 0 terminal. A fingerprint regression on Chrome 157 that costs a few percent would not
   show at this size. The first full sweep is the real test; watch `origin_blocked` there.
