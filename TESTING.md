# Testing Framework

**Purpose:** Document testing approach, best practices, and learnings for crawl4ai development and validation.

**Last Updated:** 2026-01-21

---

## Overview

This repo tests the crawl4ai service deployed to Azure. We coordinate with the `aitosoft-platform` (MAS) repo which uses this service for Finnish SME contact extraction.

**Key Testing Principles** (learned from MAS V1-V10 investigation):
1. **Systematic versioning** - Label test runs (V1, V2, etc.) with clear hypothesis
2. **Safety-first** - Prefer false positives (extra tokens) over false negatives (missing contacts)
3. **Risk-based analysis** - Classify changes as ZERO/LOW/MEDIUM/HIGH/UNACCEPTABLE risk
4. **Preserve artifacts** - Save raw outputs for comparison across versions
5. **Diverse site coverage** - Test small/medium/large, different industries, edge cases

---

## Testing Learnings from MAS Investigation

### What Works ✅

| Finding | Confidence | Evidence |
|---------|-----------|----------|
| **`magic: true` + `scan_full_page: true` solves cookie walls** | HIGH | Accountor: 32 tokens → 14,493 tokens |
| **Raw markdown preferred over fit_markdown** | HIGH | PruningContentFilter removes contact data at threshold ≥0.35 |
| **LLM handles email obfuscation naturally** | HIGH | JPond: all 19 `(at)` emails extracted correctly |
| **Safety-first cleaning (4 patterns only)** | MEDIUM | 9 sites tested, zero contact data loss |
| **Contact pages need navigation (not on homepage)** | HIGH | 8/9 test sites require 1-2 hop navigation |

### What Doesn't Work ❌

| Approach | Why It Failed | Evidence |
|----------|---------------|----------|
| **RegexExtractionStrategy (built-in)** | Finnish phone formats not matched | 0/14 contacts extracted (V5) |
| **PruningContentFilter for contact pages** | Removes structured contact data | Talgraf: ALL contacts lost at threshold 0.4 (V2) |
| **Cookie consent marker truncation** | Deletes content after marker | HIGH risk - could delete contacts below banner (V8) |
| **Link scoring** | Not available in deployed version | 0 intrinsic_score fields returned (V5) |
| **`networkidle` as default wait** | Too slow (30-60s vs 2-4s) | Use only as fallback for edge cases (V7) |

### Edge Cases Discovered 🔍

| Edge Case | Sites Affected | Solution |
|-----------|----------------|----------|
| **Cookie consent wall** | accountor.com | `magic: true` + `scan_full_page: true` |
| **Split-line email obfuscation** | vahtivuori.fi | LLM semantic understanding (regex fails) |
| **Homepage timeout** | talgraf.fi | Try contact page directly (`/yhteystiedot`) |
| **Domain redirects** | monidor.fi → monidor.com | Use `redirected_url` field |
| **Names in ALL CAPS** | solwers.com | LLM handles naturally |

---

## Test Site Registry

See [TEST_SITES_REGISTRY.md](TEST_SITES_REGISTRY.md) for complete list.

**Tier 1 (always test):**
- talgraf.fi - Cookie consent + structured contacts
- vahtivuori.fi - Email obfuscation
- accountor.com - Cookie wall edge case
- monidor.fi - Clean baseline

**Testing all 4 validates:**
- Cookie consent handling (2 patterns)
- Email obfuscation (LLM understanding)
- Fast path (monidor) vs heavy config (accountor)
- Structured data extraction (contact cards)

---

## Testing Best Practices

### 1. Systematic Versioning

**Good example (MAS V1-V10):**
- V1: Initial exploration (baseline)
- V2-V3: Hypothesis testing (PruningContentFilter thresholds)
- V4: Quality analysis (raw vs fit markdown)
- V5: Feature testing (RegexExtractionStrategy)
- V6: Custom patterns
- V7: Legacy pattern evaluation (2 sites)
- V8: Broader coverage (7 sites) + risk analysis
- V9: Full validation (all 9 sites)
- V10: Cookie consent investigation (root cause)

**Each version has:**
- Clear hypothesis ("Does PruningContentFilter preserve contacts?")
- Comparison to previous version
- Preserved artifacts (raw JSON, cleaned markdown)
- Summary table of findings

### 2. Risk-Based Analysis

Classify every change by risk level:

| Risk Level | Definition | Example |
|------------|------------|---------|
| **ZERO** | Definitionally cannot affect contact data | Remove `![]` empty brackets |
| **LOW** | Extremely unlikely to affect contacts | Remove 150+ char URLs (except LinkedIn) |
| **MEDIUM** | Theoretically could affect contacts | Remove privacy section by header match |
| **HIGH** | Plausible scenarios for data loss | Truncate after cookie consent marker |
| **UNACCEPTABLE** | Will inevitably lose contact data | PruningContentFilter threshold ≥0.35 |

**Decision rule:**
- ZERO/LOW: Include by default
- MEDIUM: Include only with validation on diverse sites
- HIGH: Require strong justification + extensive testing
- UNACCEPTABLE: Never use

### 3. Comparison Tables

Always show before/after in tables:

**Good:**
| Site | Raw Tokens | Cleaned Tokens | Savings | Contacts Lost |
|------|------------|----------------|---------|---------------|
| talgraf.fi | 1,892 | 1,859 | 1.7% | 0 ✅ |
| vahtivuori.fi | 1,551 | 1,491 | 3.9% | 0 ✅ |

**Bad:**
"The cleaning worked well on both sites."

### 4. Preserve Test Artifacts

**Directory structure:**
```
test-aitosoft/
├── reports/
│   ├── v1-baseline.md
│   ├── v2-pruning-filter.md
│   └── v10-cookie-consent.md
├── artifacts/
│   ├── v1/
│   │   ├── talgraf-raw.json
│   │   ├── talgraf-raw.md
│   │   └── vahtivuori-raw.json
│   ├── v2/
│   │   ├── talgraf-threshold-0.4.md
│   │   └── talgraf-threshold-0.5.md
│   └── v10/
│       ├── accountor-baseline.json
│       ├── accountor-magic-only.json
│       └── accountor-magic-scan.json
└── scripts/
    ├── test_site.py
    └── test_regression.py
```

**Why preserve artifacts:**
- Compare across versions (V2 threshold 0.4 vs V3 threshold 0.2)
- Reproduce bugs ("show me the exact markdown from V1")
- Validate fixes ("did V10 really solve Accountor?")

### 5. Document Null Results

**MAS did this well:**
> "FINDING: RegexExtractionStrategy Does NOT Work for Finnish Contacts"
>
> Tested EMAIL | PHONE_INTL patterns. Result: Empty extraction on both sites.
> Why it fails: [detailed explanation]

**Anti-pattern:**
Just moving on without documenting "we tried regex, it didn't work."

**Value of null results:**
- Prevents repeating failed experiments
- Explains why current approach exists
- Saves time for future developers

---

## Test Script Structure

### Basic Site Test

```python
#!/usr/bin/env python3
"""Test a single site with configurable options."""

import requests
import json
from pathlib import Path

CRAWL4AI_URL = "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

def test_site(domain: str, page: str = None, config_type: str = "default"):
    """
    Test a single site.

    Args:
        domain: Domain to test (e.g., 'talgraf.fi')
        page: Specific page path (e.g., 'yhteystiedot')
        config_type: 'default' (fast) or 'heavy' (Accountor-type)
    """
    # Build URL
    url = f"https://{domain}"
    if page:
        url = f"{url}/{page}"

    # Config
    configs = {
        "default": {
            "wait_until": "domcontentloaded",
            "magic": True,
            "scan_full_page": True,
            "remove_overlay_elements": True,
            "page_timeout": 30000
        },
        "heavy": {
            "wait_until": "networkidle",
            "magic": True,
            "scan_full_page": True,
            "remove_overlay_elements": True,
            "page_timeout": 60000
        }
    }

    # Crawl
    response = requests.post(
        f"{CRAWL4AI_URL}/crawl",
        headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
        json={
            "urls": [url],
            "crawler_config": configs[config_type]
        },
        timeout=120
    )

    result = response.json()

    # Analyze
    if result["success"]:
        data = result["results"][0]
        print(f"✅ Success: {url}")
        print(f"   Tokens: {len(data['markdown']['raw_markdown']) // 4}")
        print(f"   Status: {data['status_code']}")
        print(f"   Redirected: {data.get('redirected_url', 'No')}")

        # Save artifacts
        version = os.getenv("TEST_VERSION", "manual")
        artifacts_dir = Path(f"test-aitosoft/artifacts/{version}")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        with open(artifacts_dir / f"{domain.replace('.', '-')}.json", "w") as f:
            json.dump(data, f, indent=2)

        # Save markdown
        with open(artifacts_dir / f"{domain.replace('.', '-')}-raw.md", "w") as f:
            f.write(data["markdown"]["raw_markdown"])

        return data
    else:
        print(f"❌ Failed: {url}")
        print(f"   Error: {result.get('error', 'Unknown')}")
        return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python test_site.py <domain> [page] [config_type]")
        sys.exit(1)

    test_site(*sys.argv[1:])
```

### Regression Test Suite

```python
#!/usr/bin/env python3
"""Run regression tests across all tier sites."""

import json
from pathlib import Path
from test_site import test_site

TIER_1_SITES = [
    ("talgraf.fi", "yhteystiedot"),
    ("tilitoimistovahtivuori.fi", "?page_id=77"),
    ("accountor.com/fi/finland", "suuryritykselle"),
    ("monidor.fi", "fi/fi-yritys/yritys/")
]

def test_tier_1(version: str):
    """Run all Tier 1 tests."""
    results = []

    for domain, page in TIER_1_SITES:
        print(f"\nTesting {domain}/{page}...")

        # Try default config first
        result = test_site(domain, page, "default")

        # If blocked, retry with heavy config
        if result and len(result["markdown"]["raw_markdown"]) < 100:
            print("   ⚠️  Blocked, retrying with heavy config...")
            result = test_site(domain, page, "heavy")

        results.append({
            "site": domain,
            "page": page,
            "success": result is not None,
            "tokens": len(result["markdown"]["raw_markdown"]) // 4 if result else 0,
            "config_used": "heavy" if len(result["markdown"]["raw_markdown"]) < 100 else "default"
        })

    # Generate report
    report_dir = Path(f"test-aitosoft/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    with open(report_dir / f"{version}-regression.md", "w") as f:
        f.write(f"# {version} Regression Test Results\n\n")
        f.write(f"**Date:** {datetime.now().isoformat()}\n\n")
        f.write("| Site | Success | Tokens | Config |\n")
        f.write("|------|---------|--------|--------|\n")
        for r in results:
            status = "✅" if r["success"] else "❌"
            f.write(f"| {r['site']} | {status} | {r['tokens']} | {r['config_used']} |\n")

    print(f"\nReport saved: test-aitosoft/reports/{version}-regression.md")

if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "v-manual"
    test_tier_1(version)
```

---

## Configuration Testing Matrix

Based on MAS V10 findings, test these configs systematically:

| Config Name | wait_until | magic | scan_full_page | Use Case |
|-------------|-----------|-------|----------------|----------|
| **fast** | domcontentloaded | true | true | Default (90% of sites) |
| **heavy** | networkidle | true | true | Cookie walls (Accountor) |
| **minimal** | domcontentloaded | false | false | Baseline (no special handling) |
| **magic_only** | domcontentloaded | true | false | Test magic alone |
| **scan_only** | domcontentloaded | false | true | Test scan alone |

**Test each config on Accountor to validate:**
- minimal: Should return ~32 tokens (blocked)
- magic_only: Should return ~5,862 tokens (dialog only)
- scan_only: Should return ~32 tokens (blocked)
- fast: Should return ~14,493 tokens (full page) ✅
- heavy: Should return ~14,493 tokens (full page) ✅

---

## Quality Gates

### Before Deploying Changes

**Required:**
1. ✅ All Tier 1 sites pass (4/4)
2. ✅ Zero contact data loss on known test cases
3. ✅ No new timeouts vs baseline
4. ✅ Token usage within budget (avg ≤ baseline + 10%)

**Recommended:**
5. ⚠️ At least 1 Tier 2 site tested
6. ⚠️ Comparison report generated (before/after)
7. ⚠️ Manual spot-check of 2 sites

### For Major Changes (New Extraction Logic, Config Changes)

**Required:**
1. ✅ All Tier 1 + Tier 2 sites tested (9 sites)
2. ✅ Versioned report (V11, V12, etc.)
3. ✅ Artifacts preserved in `test-aitosoft/artifacts/vXX/`
4. ✅ Risk analysis documented
5. ✅ Comparison table (before/after)

### For Upstream Merges (crawl4ai updates)

**Required:**
1. ✅ Full regression (all tiers)
2. ✅ API compatibility check
3. ✅ Config parameter validation
4. ✅ Update AITOSOFT_CHANGES.md

---

## Metrics to Track

### Per-Site Metrics

```python
{
  "site": "talgraf.fi",
  "page": "/yhteystiedot",
  "timestamp": "2026-01-21T10:30:00Z",
  "metrics": {
    "success": true,
    "status_code": 200,
    "response_time_ms": 2341,
    "raw_markdown_length": 7568,
    "cleaned_markdown_length": 7436,
    "estimated_tokens": 1859,
    "config_used": "default",
    "contacts_found": {
      "total": 20,
      "with_phone": 17,
      "with_email": 20,
      "with_linkedin": 11,
      "decision_makers": 3
    }
  }
}
```

### Aggregate Metrics (Across Test Run)

| Metric | Target | Why |
|--------|--------|-----|
| Success rate | ≥95% | Some edge cases expected |
| Avg response time | <5s | User experience |
| Avg tokens per page | <4k | Cost control |
| Contact extraction rate | 100% | Business requirement |
| False positive rate | <5% | Quality (wrong people extracted) |

---

## When to Create a New Test Version

**Always create a new version when:**
- Testing a hypothesis ("Does custom regex work?")
- Investigating a bug ("Why does Accountor fail?")
- Validating a fix ("Did V10 solve cookie walls?")
- Before/after major changes ("V8 cleaning vs V7")

**Version naming:**
- V1, V2, ... V10 (for major investigations)
- v11-fix-timeout, v12-test-regex (for specific features)
- v-manual (for ad-hoc testing)

**Each version should have:**
1. Report: `test-aitosoft/reports/v10-cookie-consent.md`
2. Artifacts: `test-aitosoft/artifacts/v10/`
3. Summary: Added to this TESTING.md or linked

---

## Common Testing Patterns

### Pattern 1: Threshold Testing (V2-V3)

When testing a parameter with range (e.g., PruningContentFilter threshold):

```python
thresholds = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
for t in thresholds:
    result = crawl_with_threshold(url, t)
    save_artifact(f"site-threshold-{t}.md", result)

# Then compare: which threshold preserves all contacts?
```

**Output:** Table showing threshold vs token count vs contacts lost.

### Pattern 2: A/B Config Testing (V10)

When testing config combinations:

```python
configs = {
    "baseline": {},
    "magic_only": {"magic": True},
    "scan_only": {"scan_full_page": True},
    "both": {"magic": True, "scan_full_page": True}
}

for name, config in configs.items():
    result = crawl_with_config(url, config)
    save_artifact(f"accountor-{name}.json", result)

# Then compare: which config produces full content?
```

**Output:** Table showing config vs token count vs key finding.

### Pattern 3: Site Diversity Testing (V8-V9)

When validating a hypothesis across diverse sites:

```python
sites = [
    ("small_clean", "monidor.fi"),
    ("medium_tracking", "neuroliitto.fi"),
    ("large_saas", "showell.com"),
    ("edge_case", "accountor.com")
]

for category, site in sites:
    result = test_site(site)
    analyze_cleaning_impact(result)

# Then compare: does cleaning work universally?
```

**Output:** Table showing site type vs cleaning impact vs contacts preserved.

---

## Coordinating with MAS Repo

The `aitosoft-platform` (MAS) repo uses this crawl4ai service. Coordinate testing:

### Information to Share with MAS

**When we deploy crawl4ai changes:**
1. Which config parameters changed (if any)
2. Expected token usage change (+/- %)
3. Any new edge cases discovered
4. Updated test site results

**What we need from MAS:**
1. Production usage patterns (which sites are common)
2. Real-world failures ("Site X doesn't work")
3. Cost tracking (actual token usage)
4. New test sites to add to registry

### Shared Test Sites

Both repos should test the same Tier 1 sites:
- talgraf.fi
- vahtivuori.fi
- accountor.com
- monidor.fi

This ensures:
- Consistent validation across repos
- Reproducible issues
- Aligned expectations

---

## Troubleshooting Guide

### Site Returns <100 Tokens (Blocked)

**Possible causes:**
1. Cookie consent wall → Use `magic: true` + `scan_full_page: true`
2. Login required → Flag as `gated_content`
3. Bot detection → Try `simulate_user: true` (already default)
4. Timeout → Increase `page_timeout` or retry

**Debug steps:**
```python
# 1. Check raw response
print(f"Status: {result['status_code']}")
print(f"Tokens: {len(result['markdown']['raw_markdown']) // 4}")
print(f"First 500 chars: {result['markdown']['raw_markdown'][:500]}")

# 2. Look for indicators
if "cookiebot" in result['markdown']['raw_markdown'].lower():
    print("Cookie consent detected - try magic: true")
if "login" in result['markdown']['raw_markdown'].lower():
    print("Login wall detected - flag as gated")
```

### Contact Data Missing

**Possible causes:**
1. PruningContentFilter too aggressive → Use raw_markdown
2. Truncation removed content → Check cleaning pipeline
3. Contact data in JavaScript → Verify `scan_full_page: true`
4. Contact data in iframe → Currently unsupported

**Debug steps:**
```python
# 1. Compare raw vs cleaned
print(f"Raw length: {len(raw_markdown)}")
print(f"Cleaned length: {len(cleaned_markdown)}")
print(f"Reduction: {(1 - len(cleaned_markdown)/len(raw_markdown)) * 100:.1f}%")

# 2. Search for known contact
if "Toni Kemppinen" in raw_markdown:
    if "Toni Kemppinen" not in cleaned_markdown:
        print("❌ Cleaning removed contact!")
```

### Timeout Issues

**Typical patterns:**
- talgraf.fi homepage: Consistent timeout (site issue)
- accountor.com: Needs `networkidle` (JS-heavy)
- Most sites: `domcontentloaded` works (2-4s)

**Solution:**
```python
# Two-tier strategy
try:
    result = crawl(url, config="fast")  # domcontentloaded
    if result["success"]:
        return result
except Timeout:
    result = crawl(url, config="heavy")  # networkidle
    return result
```

---

## Change Log

| Date | Change | Impact |
|------|--------|--------|
| 2026-01-21 | Initial testing framework created | Consolidate MAS V1-V10 learnings |
| 2026-01-21 | Add V10 cookie consent findings | Update default config requirements |

---

## See Also

- [TEST_SITES_REGISTRY.md](TEST_SITES_REGISTRY.md) - Complete test site catalog
- [test-aitosoft/](test-aitosoft/) - Test scripts and reports
- [CLAUDE.md](CLAUDE.md) - Development guidance for Claude Code
- [AITOSOFT_CHANGES.md](AITOSOFT_CHANGES.md) - What we've modified from upstream
