# Testing Framework

Rewritten 2026-07-16 (v0.9.2 upgrade). The old version of this file predated
the stealth package and recommended `magic: true` configs — which the v0.9.x
server now REJECTS (untrusted-boundary 400) — and listed retired sites as
Tier 1. If you see advice contradicting this file elsewhere, this file wins.

---

## Golden rules

1. **Site safety:** never hit the same site more than 1-2 times per session.
   Over-scraping permanently Cloudflare-blocked talgraf.fi. Rotate sites.
2. **Tier 1 must pass 4/4 before any deploy** (quality gate).
3. Source of truth for tier membership: `test-aitosoft/test_regression.py`
   (`TIER_1_SITES`). Site metadata: `TEST_SITES_REGISTRY.md`.
4. Use the `optimal` config (matches MAS production). Never `magic` — it
   removes content on cookie sites AND the server rejects it when truthy.

## How to run

All tests are HTTP clients against a running service. Point them anywhere via
env vars:

```bash
export CRAWL4AI_API_URL=http://127.0.0.1:11235   # default: production endpoint
export CRAWL4AI_API_TOKEN=<token>                 # required

python test-aitosoft/test_regression.py --tier 1 --version <label>  # quality gate
python test-aitosoft/test_site.py <domain> --page <path>            # single site
python test-aitosoft/test_site.py <domain> --render-mode static     # static mode
python test-aitosoft/test_fingerprint.py --label <label>            # stealth diagnostic
python test-aitosoft/test_soak.py --duration-min 30                 # leak hunting
```

Three suites are OFFLINE (no server, no network) and safe to run any time:

```bash
pytest test-aitosoft/test_mas_contract.py test-aitosoft/test_admission.py test-aitosoft/test_static_mode.py
```

**Always run from the repo root** — artifact/report paths are relative
(`test-aitosoft/reports/`); running from inside `test-aitosoft/` creates a
nested `test-aitosoft/test-aitosoft/` clutter directory. Note that a bare
`pytest test-aitosoft/` will also collect the live-HTTP tests, which need a
running server + token — run the offline suites above instead.

Reports land in `test-aitosoft/reports/`.

### Running the server locally (devcontainer)

```bash
redis-server --daemonize yes
cd deploy/docker
CRAWL4AI_API_TOKEN=<anything> \
CRAWL4AI_ARTIFACT_DIR=/tmp/artifacts \
python -m uvicorn aitosoft_entry:app --host 127.0.0.1 --port 11235
```

arm64 caveat (this devcontainer): real Chrome doesn't exist for linux/arm64 —
temporarily comment the `chrome_channel`/`channel` lines in
`deploy/docker/config.yml` for local runs (NEVER commit that). The deployed
amd64 image has real Chrome.

PyJWT caveat: a stale `jwt` 1.4.0 package can shadow PyJWT and break server
boot locally — `pip uninstall jwt` fixes it (the image installs fresh and is
unaffected).

## The `optimal` config (mirrors MAS)

```json
{
  "wait_until": "domcontentloaded",
  "scan_full_page": false,
  "remove_overlay_elements": false,
  "remove_consent_popups": true,
  "page_timeout": 60000,
  "delay_before_return_html": 2.0
}
```

## Key findings (hard-won, don't relearn)

| Finding | Detail |
|---------|--------|
| `remove_consent_popups: true` solves cookie walls | Accountor: 7811 tokens; magic was never needed |
| Raw markdown > fit_markdown for contacts | PruningContentFilter drops contact blocks at threshold >= 0.35 |
| `magic: true` is harmful | Removes real content on cookie-consent sites; also rejected by v0.9.x server |
| Blocked sites are IP-based, not fingerprint | Two different browser engines got identical blocks (2026-04-11 study) |
| Playwright can hang pre-Python | Some hosts (roadscanners.com) hang the DevTools protocol; that's what `render_mode: "static"` is for |

## v0.9.x server behavior tests should expect

- Forbidden config fields (`js_code`, proxy fields, `cookies`, …) → HTTP 400
  when truthy; silently dropped when falsy (our tolerant boundary,
  `aitosoft_entry.py`).
- Unknown config fields → silently dropped.
- Dead/unresolvable domains → HTTP 400 `URL blocked (SSRF protection)`.
- Wall-clock timeout (config `limits.wall_clock_s`, 180s) → HTTP 504.
- Every result carries `render_mode: "full" | "static"`.
- Only `/health` is public; everything else needs the bearer token
  (including `/docs` and `/metrics`).

## Quality gates

| Gate | When | Bar |
|------|------|-----|
| MAS contract test (`pytest test-aitosoft/test_mas_contract.py`) | before every deploy + after every upstream sync | 7/7 pass — offline, pins MAS's exact request fields against the untrusted boundary |
| Render-gate test (`pytest test-aitosoft/test_admission.py`) | before every deploy; after any admission/capacity change | all pass — offline, pins RenderGate capacity/queue/429 semantics |
| Static-mode test (`pytest test-aitosoft/test_static_mode.py`) | before every deploy; after any static-mode change | all pass — offline, pins per-hop SSRF redirect validation, bounded fan-out, monitor outcome |
| Tier 1 regression | before every deploy | 4/4 pass |
| Fingerprint diagnostic | after stealth/browser changes | no regressions vs `test-aitosoft/stealth-v4/` |
| Soak test | after pool/leak-related changes | flat memory over 30 min |
| Post-deploy smoke | after every deploy | health + 1 crawl + auth 401 check |
| Upstream merges | after every sync | Tier 1 + `git diff upstream/develop HEAD` matches AITOSOFT_FILES.md inventory |
