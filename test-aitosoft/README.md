# Aitosoft Test Suite

**Purpose:** Test and validate crawl4ai Azure deployment for Finnish SME contact extraction.

**See also:** [TESTING.md](../TESTING.md) and [TEST_SITES_REGISTRY.md](../TEST_SITES_REGISTRY.md)

---

## Quick Start

### Prerequisites

```bash
# Set API token in your environment
export CRAWL4AI_API_TOKEN="your-token-here"

# Or create .env file
echo "CRAWL4AI_API_TOKEN=your-token-here" > .env.local
source .env.local
```

### Test a Single Site

```bash
# Test with default (fast) config
python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot

# Test Accountor (needs heavy config for cookie wall)
python test-aitosoft/test_site.py accountor.com/fi/finland --page suuryritykselle --config heavy

# Test without saving artifacts
python test-aitosoft/test_site.py monidor.fi --no-save
```

### Run Regression Tests

```bash
# Test Tier 1 sites (required before deploy)
python test-aitosoft/test_regression.py --tier 1 --version v11

# Test all sites (comprehensive)
python test-aitosoft/test_regression.py --all --version v12
```

---

## Directory Structure

```
test-aitosoft/
├── README.md              # This file
├── test_site.py           # Single site testing script
├── test_regression.py     # Multi-site regression testing
├── artifacts/             # Test outputs (gitignored)
│   ├── v11/
│   │   ├── talgraf-fi-yhteystiedot-fast.json
│   │   ├── talgraf-fi-yhteystiedot-fast-raw.md
│   │   └── talgraf-fi-yhteystiedot-fast-meta.json
│   └── manual/
└── reports/               # Test reports (gitignored)
    ├── v11-regression-tier1.md
    └── v12-regression-tierall.md
```

---

## Test Configurations

| Config | wait_until | magic | scan_full_page | Use Case |
|--------|-----------|-------|----------------|----------|
| **fast** | domcontentloaded | ✅ | ✅ | Default (90% of sites, 2-4s) |
| **heavy** | networkidle | ✅ | ✅ | Cookie walls like Accountor (30-60s) |
| **minimal** | domcontentloaded | ❌ | ❌ | Baseline (no special handling) |
| **magic_only** | domcontentloaded | ✅ | ❌ | Test magic parameter alone |
| **scan_only** | domcontentloaded | ❌ | ✅ | Test scan_full_page alone |

**Key learnings:**
- `magic: true` + `scan_full_page: true` required for cookie consent walls
- `networkidle` only needed for JS-heavy sites (use `fast` for most)
- Most sites work with `fast` config (2-4s response)

---

## Test Site Tiers

### Tier 1: Core Sites (Always Test)

Must pass before deploying any changes:

| Site | Challenge | Expected Contact |
|------|-----------|------------------|
| talgraf.fi | Cookie consent, structured data | Toni Kemppinen (CEO) |
| vahtivuori.fi | Email obfuscation `(at)` | Jaana Toppinen, Kirsi Haltia |
| accountor.com | Cookie wall (requires heavy config) | Jani Järvensivu |
| monidor.fi | Clean baseline | Mikko Savola (CEO) |

**Pass criteria:** All 4 sites return expected contacts

### Tier 2: Extended Sites (Major Changes)

Test when making significant changes:

- jpond.fi (all emails obfuscated)
- neuroliitto.fi (deep navigation)
- solwers.com (public company, names in ALL CAPS)
- caverna.fi (restaurant, multiple phones)
- showell.com (heavy tracking, SaaS)

**Pass criteria:** ≥95% success rate

---

## Common Testing Patterns

### Test a hypothesis

```bash
# Create a new version for your investigation
export VERSION="v11-test-regex"

# Test with different configs
python test-aitosoft/test_site.py accountor.com/fi/finland --page suuryritykselle --config minimal --version $VERSION
python test-aitosoft/test_site.py accountor.com/fi/finland --page suuryritykselle --config magic_only --version $VERSION
python test-aitosoft/test_site.py accountor.com/fi/finland --page suuryritykselle --config fast --version $VERSION

# Compare artifacts
ls test-aitosoft/artifacts/$VERSION/
```

### Before deploying changes

```bash
# Run Tier 1 regression
python test-aitosoft/test_regression.py --tier 1 --version pre-deploy

# Check quality gates
cat test-aitosoft/reports/pre-deploy-regression-tier1.md
```

### Investigate a failing site

```bash
# Test with verbose output
python test-aitosoft/test_site.py failing-site.fi --config fast --version debug

# Check artifacts
cat test-aitosoft/artifacts/debug/failing-site-fi-fast-raw.md | head -50

# Try heavy config
python test-aitosoft/test_site.py failing-site.fi --config heavy --version debug

# Compare
diff test-aitosoft/artifacts/debug/failing-site-fi-fast-raw.md \
     test-aitosoft/artifacts/debug/failing-site-fi-heavy-raw.md
```

---

## Quality Gates

### Before Deploying

**Required:**
- ✅ All Tier 1 sites pass (4/4)
- ✅ Zero contact data loss on expected contacts
- ✅ No new timeouts vs baseline

**Recommended:**
- At least 1 Tier 2 site tested
- Comparison report generated
- Manual spot-check of 2 sites

### For Major Changes

**Required:**
- ✅ All Tier 1 + Tier 2 sites tested (9/9)
- ✅ Versioned report saved
- ✅ Artifacts preserved
- ✅ Success rate ≥95%

---

## Troubleshooting

### "CRAWL4AI_API_TOKEN not set"

```bash
# Set in environment
export CRAWL4AI_API_TOKEN="crawl4ai-d439be7297235edd4bde58b434c0ce82c99001912a47eafd"

# Or in .env.local
echo 'CRAWL4AI_API_TOKEN="crawl4ai-d439be7297235edd4bde58b434c0ce82c99001912a47eafd"' > .env.local
source .env.local
```

### Site returns <100 tokens (blocked)

```bash
# Try heavy config (handles cookie walls)
python test-aitosoft/test_site.py site.fi --config heavy
```

### Request timeout

```bash
# Some sites (like talgraf.fi homepage) consistently timeout
# Try the contact page directly instead:
python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot
```

### Compare two test runs

```bash
# Test with two different configs
python test-aitosoft/test_site.py site.fi --config fast --version compare-fast
python test-aitosoft/test_site.py site.fi --config heavy --version compare-heavy

# Compare token counts
grep "raw_tokens" test-aitosoft/artifacts/compare-*/site-fi-*-meta.json

# Compare markdown
diff test-aitosoft/artifacts/compare-fast/site-fi-fast-raw.md \
     test-aitosoft/artifacts/compare-heavy/site-fi-heavy-raw.md
```

---

## Adding New Test Sites

When adding a test site to the registry:

1. **Test manually first:**
   ```bash
   python test-aitosoft/test_site.py newsite.fi --page yhteystiedot --version validate-newsite
   ```

2. **Verify expected contacts are found:**
   ```bash
   grep "Expected Name" test-aitosoft/artifacts/validate-newsite/newsite-fi-*.md
   ```

3. **Add to `test_regression.py`:**
   ```python
   TIER_2_SITES.append({
       "domain": "newsite.fi",
       "page": "yhteystiedot",
       "expected_decision_makers": ["Expected Name"],
       "expected_min_contacts": 5
   })
   ```

4. **Document in [TEST_SITES_REGISTRY.md](../TEST_SITES_REGISTRY.md)**

---

## See Also

- [TESTING.md](../TESTING.md) - Testing framework and best practices
- [TEST_SITES_REGISTRY.md](../TEST_SITES_REGISTRY.md) - Complete test site catalog
- [CLAUDE.md](../CLAUDE.md) - Development guidance
- MAS V1-V10 exploration findings (in aitosoft-platform repo)
