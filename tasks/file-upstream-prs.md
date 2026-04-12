# File Upstream PRs for 4 crawl4ai Bugs

**Status:** Open
**Priority:** Medium — good citizenship, keeps our patches mergeable
**Blocked by:** merge-upstream-develop (do the merge first so PRs are clean)

## Goal

File 4 PRs to `unclecode/crawl4ai` for the bugs we found and fixed during
the stealth package work. All 4 are confirmed still broken in upstream
develop as of 2026-04-11.

## PRs to file

1. **browser_adapter.py: playwright-stealth 2.x API port**
   - `StealthAdapter._check_stealth_availability` + `apply_stealth`
   - Old: `from playwright_stealth import stealth_async` (1.x, no longer exists)
   - New: `from playwright_stealth import Stealth; Stealth().apply_stealth_async(page)`
   - Impact: `enable_stealth=True` was silently broken for everyone using playwright-stealth 2.x

2. **browser_manager.py: _build_browser_args GPU flag drift**
   - `_build_browser_args` hardcodes `--disable-gpu` unconditionally
   - `build_browser_flags` (sibling method) correctly gates on `enable_stealth`
   - Fix: same conditional in both places
   - Impact: WebGL killed in stealth mode, one of loudest anti-bot signals

3. **browser_adapter.py: navigator.webdriver init_script**
   - playwright-stealth's webdriver.js only patches when `navigator.webdriver`
     is truthy, but `--disable-blink-features=AutomationControlled` makes it
     false (falsy, still defined). Real Chrome has it as undefined.
   - Fix: explicit `page.add_init_script` to force undefined
   - This one is arguably a playwright-stealth bug, not crawl4ai — file
     against both repos or just crawl4ai with a note

4. **api.py: config.yml browser.kwargs not merged into requests**
   - `handle_crawl_request` calls `BrowserConfig.load(user_dict)` directly,
     ignoring config.yml browser.kwargs for all API requests
   - Only the PERMANENT pool browser sees config.yml
   - Fix: merge helper that layers config.yml under user dict
   - This one may be controversial — upstream may prefer the current behavior
     (config.yml only affects default, user always gets full control). Frame
     it as "opt-in default merging" or document the behavior gap.

## Notes

- PRs 1-2 are clear bugs with no design ambiguity. File those first.
- PR 3 is a workaround for a playwright-stealth limitation. Useful but niche.
- PR 4 is a behavior change. May need discussion with maintainer.
- Target branch: `develop` (that's where unclecode merges PRs).
