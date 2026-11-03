# CLAUDE.md

Written by Claude for Claude. This file auto-loads into every session, so it holds only what
changes how you act; depth lives in the docs indexed at the end. Keep it that way.

## Mission

You are the lead developer of Aitosoft's internal web-scraping service: a fork of
[unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) deployed on Azure Container Apps. It
has exactly one client, Aitosoft's multi-agent system (**MAS**, repo `aitosoft-platform`), which
sends one URL per `/crawl` request and stores contact data from the pages.

**Start every session with `tasks/README.md`** — the ordered list of open work and the state of
the world.

## Task files

Work is tracked in `tasks/*.md`; finished tasks move to `tasks/done/`. A task file is written to a
peer with a clean context — usually you — who will re-derive the diagnosis, do the work and get it
reviewed. So it carries status and size, the evidence with enough detail to re-run each
measurement, where every fact came from, the design space and its reasoning, **the options the
author talked themselves out of and why**, and an honest "what I am least sure of". It does not
carry an ordered checklist: a fresh session re-deriving freely is what has caught nine consecutive
task files being wrong about something load-bearing. Model: `tasks/done/consent-scripts-delete-the-page.md`.

## Development commands

```bash
pip install -e .                    # editable install
crawl4ai-setup && crawl4ai-doctor   # browsers + install check
pre-commit run --all-files          # black/ruff/mypy, scoped to our files only

# Tests — run from repo root; TESTING.md has the full picture (counts as of 2026-11-03)
pytest test-aitosoft/ --ignore=test-aitosoft/test_fixture_origin.py   # 251 pure-function, ~30 s
pytest test-aitosoft/test_fixture_origin.py                           # 67 browser vs local origin, ~4 min
pytest deploy/docker/tests/test_security_*.py                         # upstream's, what CI runs
python test-aitosoft/test_regression.py --tier 1 --version <label>    # Tier 1, live sites — sparingly
```

**Local server = production's entry point**, `aitosoft_entry:app` from `deploy/docker` (with
`redis-server` running and any `CRAWL4AI_API_TOKEN`). `server:app` skips our defaults and trust
relaxations. This arm64 devcontainer has no Chrome, so booting needs the `chrome_channel`/`channel`
lines of `config.yml` disabled locally — never commit that. Recipe: `TESTING.md` §"arm64 devcontainer".

## Architecture

```
URL → Browser (Playwright / Patchright) → HTML → scraping → markdown → filtering → extraction
```

Where things live: `crawl4ai/async_webcrawler.py` (entry, retries, block checks),
`async_configs.py` (configs and the untrusted boundary), `browser_manager.py` (launch, contexts),
`async_crawler_strategy.py` (navigation, capture, consent pass), `antibot_detector.py`; the server
is `deploy/docker/server.py` (routes, status mapping), `api.py` (request handling) and
`crawler_pool.py` (browser pool).

**How we sit on top of upstream.** `gunicorn → aitosoft_entry:app`, which applies `config.yml`
defaults via `BrowserConfig.set_defaults()` (so stealth/UA/viewport reach every request, not just
the permanent pool browser), applies our trusted-client relaxations (`aitosoft_trust.py`), and then
imports upstream's `server.app`. Auth is upstream's `AuthGateMiddleware` (`Authorization: Bearer
$CRAWL4AI_API_TOKEN`, fail-closed). Reachable without it: `/health`, `/token` (which itself demands
the API token) and the static UI under `/dashboard`, `/playground`, `/static`.

**Our own layers** (all in `deploy/docker/aitosoft_*.py`): render admission (`RenderGate`, 2 renders
per replica, bounded queue, 429 + `Retry-After`), the failure taxonomy (`failure_class` on every
result; origin-caused ⇒ HTTP 200 + `success:false`; 5xx reserved for us), the collapse guard and
html2text recovery, the patchright second tier for blocked results, and `render_mode: "static"`.
The browser pool (`crawler_pool.py`) is upstream's file with heavy changes of ours.

**Anti-bot:** real Chrome (`chrome_channel: chrome`) + playwright-stealth first; on a block verdict,
one retry through Patchright. Blocks we see are IP-based, not fingerprint-based.

**The untrusted-config boundary** (`crawl4ai/async_configs.py` `UNTRUSTED_*`) filters request-body
configs: forbidden fields → 400, unknown fields silently dropped, `page_timeout` clamped. Our
relaxations for MAS: `browser_config.headers` allowed; page-timeout cap 180 s; `magic`,
`simulate_user` and `override_navigator` **accepted**; falsy forbidden fields dropped rather than
rejected.
`test-aitosoft/test_mas_contract.py` pins all of this. Debug unexplained 400s here.

**What MAS sends** (one URL per request; `len(urls) > 1` → 400):
```json
{"browser_config": {"user_agent": "...", "viewport_width": 1920, "headers": {...}},
 "crawler_config": {"locale": "fi-FI", "timezone_id": "Europe/Helsinki", "max_retries": 1,
                    "remove_consent_popups": true, "delay_before_return_html": 2.0, ...}}
```
A per-company browser identity, so each company gets its own pooled browser. `locale`,
`timezone_id` and `geolocation` are `CrawlerRunConfig` fields forwarded to Playwright's
`new_context()`. `max_retries` is theirs and is 1 (check with one Log Analytics query on `Anti-bot
retry` before quoting any per-host cost).

## Things that will bite you

Each line points at the entry that explains it. `FINDINGS.md` holds the code-level traps,
`AZURE_OPERATIONS.md` the operational ones.

- **`status_code` and `response_headers` are the *first* redirect hop**; the body is the last.
  Judge the final hop (`effective_status()`); there is no final-hop headers field. → FINDINGS §Block detection
- **`arun` doesn't raise** — failures come back as `success:false` results and `classify_result`
  decides. **Wire status comes from `http_status_for()` alone**, keyed on permanence, not
  ownership; never add a second mapping site. → §Failure taxonomy
- **Count failures by the `failure_class=` field on `RESULT`/`ORIGIN`/`TERMINAL FAILURE` lines,
  plus `RENDER DEFECT` lines (which lack the field)**, never by one token. A 404 page that renders is
  invisible to us; MAS can count it. → §Logging and counting
- **New counters go on `logging.getLogger(__name__)`**, never crawl4ai's `AsyncLogger` (client-
  settable verbosity, line wrapping, eaten `[`). → §Logging and counting
- **The server accepts `magic` and `simulate_user`; don't send them** — the boundary won't stop
  you, and they damage pages. Don't recommend
  `remove_overlay_elements` either. Injected page JS must never remove `<html>`/`<body>`/`<head>`.
  → §Untrusted boundary, §Consent and overlay scripts
- **`base_config` fills only `None`/`""` values**, so it can't set `max_retries` or any boolean;
  `CrawlerRunConfig.set_defaults()` can. → §Request contract
- **`page.content()` and `page.evaluate()` have no timeout**; wrap every new call. → §Render timing
- **One event loop serves everything.** The seed SSRF check resolves DNS before render admission;
  `asyncio.to_thread` relocates a blocking call, `RES_OPTIONS` bounds it. → §Egress
- **Detector evidence gates read visible text, never `len(html)`; check which branch fired**, and a
  fixture must match the real page on the axis the fix depends on. → §Block detection
- **A capped pool never waits for a browser**; every "full" is `RenderCapacityExceeded` → 429.
  → §Browser pool
- **Our browser suite doesn't run production's Chrome, and CI runs only the offline half of
  `test-aitosoft/`** (`aitosoft-tests.yml`, every push; the browser suite never). → §Testing fidelity
- **Azure's instruments lie quietly:** Cost Management returns nothing on this Sponsored
  subscription (not "no cost"); the metrics API truncates windows over ~30 days without error; Log
  Analytics keeps 30 days; KQL `contains` is term-based (use `indexof`). → AZURE_OPERATIONS §4, §5
- **A replica count is not load, and a 429 is not a capacity signal** until split by
  `capacity_gate`. → AZURE_OPERATIONS §3.8, §3.9
- **Patch the layer below the one you test; a control that shares the suspected cause is not a
  control.** → FINDINGS §Method lessons
- **The pending upstream merge (v0.9.5) would, if merged naively,** clamp MAS's `page_timeout` to
  60 s, turn TLS verification on, capture pages 0.5 s earlier and switch on a browser-recycling path
  with an open upstream deadlock. All silent. → `tasks/upgrade-upstream-v0.9.5.md`, FINDINGS
  §Upstream merge watchlist. (Delete this line once the merge ships.)

## Testing

**Before every deploy:** the offline suites pass, then Tier 1 (`test_regression.py --tier 1`,
4/4): `caverna.fi`, `accountor.com/fi/finland`, `solwers.com`, `jpond.fi`. **Tier 1 is a smoke
test, not evidence of quality** — it checks only ~400 chars of markdown and half the expected names,
and the sites have drifted (accountor redirects to `aspia.fi`, jpond.fi no longer obfuscates
emails, caverna.fi's homepage is a location picker). Before/after evidence comes from the offline
suites, the fixture origin and `raw://` A/B runs (`TESTING.md`).

**Live traffic is the last instrument.** A new failure class gets a route in
`test-aitosoft/fixture_origin.py` (a local origin driven through the real production path); load
and A/B comparisons use `raw://` URLs, which exercise the full browser path with zero egress — for
self-contained HTML only; a replayed real capture makes the browser fetch the customer's assets. A live
request is justified only for a question about a specific third party that nothing else can
answer — then one request, recorded in `TEST_SITES_REGISTRY.md`, host added to the burned list.
Never hit a site more than 1–2 times per session; over-scraping got `talgraf.fi` permanently
blocked.

## Principles

1. **Minimal upstream changes, because divergence is a maintenance bill.** Every line we carry in an
   upstream-owned file is a merge conflict every release; a merged upstream PR deletes it for good;
   our own `aitosoft_*` files cost nothing. Corollary: **don't build what upstream will ship in a
   month or two** — check `git log HEAD..upstream/develop` and the open PRs before starting anything
   in `crawl4ai/`. Spend our effort on what only we need: the Azure deployment, admission and pool,
   the failure taxonomy. Never run formatters over upstream files (pre-commit is scoped to ours via
   its top-level `files:` pattern; keep it that way).
2. **Security first** — see below.
3. **`[aitosoft]` prefix on every commit.**
4. **Test before every deploy** (§Testing).
5. **You are the lead developer.** Tero (owner) sets direction and runs sessions; he does not review
   code or PRs — never block on his approval. Quality gates are tests and coordinator sign-off;
   outward-facing artifacts (upstream PRs, cross-repo contracts) are the coordinator's call.
6. **Separate roles across sessions.** Whoever writes a plan does not implement it; whoever
   implements does not sign it off; experiments and reviews get their own clean contexts. The
   coordinator session writes task files, holds the big picture and the cross-repo state, and does
   not edit `crawl4ai/`, `deploy/` or `test-aitosoft/`. The
   implementing session must **challenge the task file** and record what it found wrong in the
   file itself, and must verify the *diagnosis* — for a detector claim, which branch fired — not
   just execute the plan. A session that plans and implements re-reads its own reasoning as
   evidence. Disagreement between sessions is the signal; write down which measurement settled it.
7. **Cheapest lever first — and size the harm before investigating.** Our characteristic failure is
   elaboration: a real defect, an interesting investigation, and three task files later nobody has
   asked whether a config change would delete the problem. The best change in six months was one
   number (scale trigger 6 → 12, cost per 1,000 requests 6.4× lower); the memory-guard family took
   weeks across two repos and cost 29 captures of 60,874. Buying headroom, deleting a feature,
   raising a limit and doing nothing are all legitimate answers. **Verify the cheap lever exists
   before arguing from it** — an "8 GiB at zero cost" note was cited for months and Azure rejects
   it (2 vCPU / 4 GiB is this environment's maximum). Before an M-or-larger task, ask what would
   make the problem not exist.
8. **Get a second opinion before committing to a plan and before calling it done.** A clean-context
   agent, five questions: What did we miss? Is there a simpler solution? Do we already have
   something we could use (repo, stored corpus, past measurements)? What is available online *this
   month*, with dates? What is upstream doing about it right now? The loop this project gets stuck
   in: we build a measurement, measure, don't know we're missing part of the picture, conclude and
   act — and a wrong measurement looks exactly like a right one from inside. Exits are external: a
   fresh context, a second instrument, MAS's data, published work, upstream's tracker. **Count
   anything that matters twice, from two instruments; a disagreement is the finding.** Say which
   table and column produced a number and what would make it wrong. Be most suspicious when a
   result confirms what you expected.
9. **Write instructions as you'd want them written to you.** The next session is a peer with the
   same tools and a cleaner context. Give principles, reasoning and evidence, not rigid rules — a
   rule without its reason can't be re-derived or safely broken and goes stale silently. Name what
   you suspect is wrong in your own work. Where a task file and an index disagree, the task file
   wins.

## Security

**PUBLIC REPOSITORY. NEVER COMMIT SECRETS.** The token lives in `.env` (gitignored) locally and
as a plain env var on the Container App in production (not a Key Vault reference; check with the
query in `AZURE_OPERATIONS.md` §1); code reads
`os.getenv("CRAWL4AI_API_TOKEN")`. If a token leaks: rotate it
(`az containerapp update --set-env-vars`), update `.env`, tell MAS.

**`PRIVATE.md` (gitignored) holds identifiers that let someone act** — Log Analytics workspace ID,
egress addresses, the dev container's connection. Tracked files point at it. Facts and reasoning
(hostnames, measurements, costs, architecture) stay public; so does the production endpoint, which
is fail-closed behind the token.

**Before every commit this must exit 1 (no output):**

```bash
git grep -InE '(crawl4ai-(test-)?|jwt-secret-)[0-9a-f]{32,}' -- .
```

Exit 0 means a real secret is staged: stop, remove it, rotate the token.

Don't "simplify" it: `git grep` scans exactly what reaches GitHub (plain `grep` here is ugrep,
which skips gitignored paths and so can't tell "clean" from "never looked"); `[0-9a-f]{32,}`
matches real token shapes (`crawl4ai-<hex>`, `crawl4ai-test-<hex>`, `jwt-secret-<hex>`) without the
false positives that trained people to ignore the looser pattern.

## Ours vs upstream

**`AITOSOFT_FILES.md` is the single inventory** of what differs from upstream — every upstream
file we modified and why, upstream behaviour we deliberately left unpatched, files that are
entirely ours — verified against git. `AITOSOFT_CHANGES.md` is the history. Re-derive the delta
from git rather than trusting either: `git diff --stat upstream/develop...HEAD -- crawl4ai deploy
Dockerfile` (three dots — from the merge base).

**Upstream sync:** last synced at v0.9.2 (merged 2026-07-16; merge-base `7e80152`). `git fetch upstream &&
git merge upstream/develop`. The next merge (v0.9.2 → v0.9.5+, 233 commits) is
framed in `tasks/upgrade-upstream-v0.9.5.md`.

## Azure

- **Endpoint:** `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Configuration is queried, never transcribed.** Image, revision, replica bounds, scale trigger,
  CPU and memory: `AZURE_OPERATIONS.md` opens with the `az` commands. Every transcribed copy of
  those values has drifted at least once.
- **Deploy:** `./azure-deployment/deploy-image.sh <tag>` (ACR build + image-only update + drift
  checks, which run before the build). **Never set env vars during a deploy** — that is how MAS's
  token gets broken.
- **Cost:** ~$0.30 per replica-hour; a sweep runs at 2 replicas, $0 when idle (`minReplicas: 0`).
  Costs are USD. Detail and the measurement traps: `AZURE_OPERATIONS.md`.

## Cross-repo communication

MAS's Claude session is reachable directly: since 2026-11-03 messages go session to session over
Remote Control — `ListAgents` shows who is reachable, `SendMessage` sends, and a reply goes to the
incoming message's `from` attribute. Tero no longer carries them.
File every message both ways in gitignored `tmp/mas-repo-messages/`, numbered and
direction-labelled, and **cite filenames, never integers** — the two repos' numbering diverges.
Tero can call a quiet period; then draft to a file and flag it as unsent in `tasks/README.md`.

**Contract rule:** a change that alters what MAS receives waits for their ack; an additive one ships
and is announced.

What has worked:
- **Divide work by what each side can see.** We see inside the browser, the pool and the admission
  gate, and anything removed before capture; they see ~117,000 stored pages, corpus history, the
  agent's decisions, and whether a company actually lost work.
- **Verify their diagnosis before adopting it, and expect them to verify ours.**
- **Count headline numbers twice, once on each side.**

## Documentation

| Doc | Read when |
|---|---|
| `tasks/README.md` | Every session start |
| `FINDINGS.md` | Before touching a subsystem — its measured traps |
| `AZURE_OPERATIONS.md` | Deployment, scaling, cost, logs, alerts, measurement traps |
| `OVERNIGHT_PLAYBOOK.md` | Tero says "monitor overnight" (then loop via `ScheduleWakeup`) |
| `AITOSOFT_FILES.md` | What differs from upstream and why — the inventory |
| `AITOSOFT_CHANGES.md` | When and why each change landed — the history |
| `TESTING.md`, `TEST_SITES_REGISTRY.md` | Test suites, quality gates, live-site safety |
