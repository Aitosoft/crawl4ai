# Stealth Package: Real Chrome + Working Stealth + Config Merge

**Status:** Done (2026-04-11)
**Commits:** `0a59343`, `7a00fc2`
**Deployed:** `crawl4ai-service:0.8.6-stealth-v5`, revision `stealth-v5`

## Goal

Make crawl4ai's browser fingerprint indistinguishable from real Chrome to
reduce bot-detection blocks. MAS was seeing HTTP 500 on 4 sites (baxter.fi,
lundbeck.com/fi, pedelux.fi, rederiabeckero.ax) while plain curl worked.

## Outcome

Fingerprint fully fixed (6 critical signals). Tier 1 regression 4/4 pass.
The 4 originally-blocked sites remain blocked — confirmed IP-based (Azure
egress flagged), not fingerprint-based. Patchright fallback retry also
implemented and verified; same result, which confirms the IP diagnosis.

## Learnings

- **config.yml was dead code for the request path.** `api.py` calls
  `BrowserConfig.load(user_dict)` which ignores config.yml entirely.
  Only the PERMANENT pool browser (rarely hit) saw it. Fix:
  `aitosoft_browser_merge.py` merges config.yml under user dict.
- **playwright-stealth 2.x broke the API.** Upstream pins `>=2.0.0` but
  StealthAdapter still imports 1.x names. Silent no-op. Fix: ported to
  `Stealth().apply_stealth_async(page)`.
- **Two flag-builder methods drifted.** `build_browser_flags` (static)
  gates `--disable-gpu` on `enable_stealth`. `_build_browser_args`
  (instance, the one actually used) hardcodes it. Fix: same conditional.
- **navigator.webdriver = false, not undefined.** playwright-stealth's
  patch only activates on truthy. `--disable-blink-features=AutomationControlled`
  makes it false (falsy but defined). Fix: explicit init_script.
- **Blocked sites need residential proxies, not better stealth.** When
  two different browser engines (Playwright + patchright) get identical
  blocks, it's the IP, not the fingerprint.
