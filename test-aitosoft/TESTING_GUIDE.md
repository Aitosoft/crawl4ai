# Crawl4AI Testing Guide - Complete Context

**Purpose**: Single source of truth for all testing work. Read this file at the start of any session to get full context.

**Last Updated**: 2026-01-26

---

## 🎯 Mission & Context

### What This Repo Does
**Fork of**: `github.com/unclecode/crawl4ai`
**Purpose**: Internal web scraping service for Aitosoft's AI agents
**End Users**: Only Aitosoft AI agents (no human users)

### Relationship with MAS Repo
**MAS Platform** (`aitosoft-platform` repo):
- Multi-agent system that orchestrates AI agents
- **Uses this crawl4ai service** via API to extract company contact information
- **Must scrape 100k+ company websites** to build comprehensive contact database
- **#1 Priority**: Extract ALL contact details (emails, phones, addresses) from as many companies as possible
- **MAS Claude has NO access to this repo** - all testing/optimization is YOUR responsibility

**Communication Flow**:
```
MAS Agent → API Request → Crawl4AI Service (this repo) → Return markdown/contacts
```

---

## 📊 Current Status - What We Know

### Production Baseline (160 Fresh URLs)

**Date**: 2026-01-26
**Test**: MAS crawled 160 small Finnish company websites (never previously accessed)

| Outcome | Count | % |
|---------|-------|---|
| **Usable** | 140 | 87.5% |
| Site down | 7 | 4.4% |
| Bot blocked (Cookiebot) | 7 | 4.4% |
| Parked/placeholder | 3 | 1.9% |
| Shutdown | 1 | 0.6% |
| Timeout | 1 | 0.6% |
| JS-heavy | 1 | 0.6% |

**Key insight**: Most failures (12.5%) are **site issues**, not crawl4ai issues. Only ~5% are bot-related blocks.

### Critical Config Discovery

Two crawl4ai options **destroy content** on cookie consent sites — don't use them:

| Option | Problem |
|--------|---------|
| `magic=True` | Removes cookie consent AND page content |
| `remove_overlay_elements=True` | Treats entire page as overlay on Cookiebot sites |

### The Optimal Config

```python
{
    "wait_until": "domcontentloaded",
    "magic": False,                    # CRITICAL: Don't use!
    "remove_overlay_elements": False,  # CRITICAL: Don't use!
    "page_timeout": 60000,
    "delay_before_return_html": 2.0,
}
```

**Why this works**: The content IS in the HTML, we just need to NOT filter it out. The cookie consent dialog exists but the page content is still rendered and accessible.

---

## ✅ Recommended Configuration

### For MAS API Calls

```typescript
const crawler_config = {
  wait_until: "domcontentloaded",
  magic: false,
  remove_overlay_elements: false,
  page_timeout: 60000,
  delay_before_return_html: 2.0,
};
```

### For test_site.py

```bash
# Uses "optimal" config by default now
python test-aitosoft/test_site.py any-site.fi --page yhteystiedot

# Explicitly specify optimal
python test-aitosoft/test_site.py accountor.com/fi/finland --page suuryritykselle --config optimal
```

---

## 📋 Test Sites & Quality Gates

### Regression Test Sites

| Site | Expected | Status |
|------|----------|--------|
| **jpond.fi** | 1.8k+ tokens | ✅ Works |
| **showell.com** | 14k+ tokens | ✅ Works |
| **solwers.com** | 5k+ tokens | ✅ Works |
| **caverna.fi** | 5k+ tokens | ✅ Works |
| **accountor.com** | 12k+ tokens | ✅ Works |

**Quality Gate**: All 5 must pass before deploy.

### Retired Test Sites

| Site | Reason |
|------|--------|
| talgraf.fi | Blocked after stress testing (Cloudflare) |
| vahtivuori.fi | Site restructured (404) |
| monidor.com | Returns bot verification challenge |

---

## 🚨 Known Issues

### Cloudflare Blocking (talgraf.fi)

**Affected Sites**: talgraf.fi (all pages)
**Symptom**: Playwright navigation times out after 60-120s
**Root Cause**: **We triggered Cloudflare Bot Management** by running 200+ stress test requests to the same URL during Phase 1-2 reliability testing
**Evidence**:
- `curl https://talgraf.fi/` returns 200 OK in 0.2s (not IP blocking)
- `curl https://talgraf.fi/yhteystiedot/` returns 403 with Cloudflare challenge
- Playwright hangs indefinitely (Cloudflare JS challenge detection)

**Solution**: None available - site is now blocking our headless browser fingerprint
**Status**: ❌ **BLOCKED** - remove from test suite, skip in production

**Lesson Learned**: See "Testing Best Practices" section below

### Email Obfuscation

Sites using `info (at) company.com` patterns work fine — LLM extraction handles them naturally.

---

## 🛠️ Test Infrastructure

### API Endpoint
```bash
https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io/crawl
```

### Authentication
```bash
# Load from .env file
source .env
# Or export manually (see .env for token)
```

### Key Test Scripts

| Script | Purpose | Example Usage |
|--------|---------|---------------|
| **test_site.py** | Quick single-site testing | `python test-aitosoft/test_site.py jpond.fi --page yhteystiedot` |
| **test_regression.py** | Run Tier 1 regression tests | `python test-aitosoft/test_regression.py --tier 1 --version v1` |
| **test_reliability_study.py** | Large-scale reliability testing | `python test-aitosoft/test_reliability_study.py --mode isolated --count 100` |

### Quick Start

```bash
# 1. Ensure you're in the repo root
cd /workspaces/crawl4ai-aitosoft

# 2. Load API token
source .env

# 3. Test with optimal config (now default)
python test-aitosoft/test_site.py accountor.com/fi/finland --page suuryritykselle

# 4. Run Tier 1 regression
python test-aitosoft/test_regression.py --tier 1 --version v1
```

---

## 💡 Key Principles

1. **Simple config wins**: optimal config (magic=False) works on 100% of tested sites
2. **Don't over-engineer**: Cookie consent is NOT a technical barrier with correct config
3. **Contact extraction is #1**: All other metrics are secondary
4. **Raw markdown for extraction**: fit_markdown removes contact data
5. **Retry logic for intermittent**: 99.5% success with 1 retry
6. **Test before deploy**: All Tier 1 sites must pass
7. **Distribute test load**: Never hammer a single site (see below)

---

## ⚠️ Testing Best Practices (Avoid Bot Detection)

### The talgraf.fi Incident (2026-01-26)

We ran 200+ requests to `talgraf.fi/yhteystiedot` during reliability testing to measure error rates. This triggered Cloudflare's behavioral analysis, which now blocks our Azure IP/browser fingerprint on that site permanently.

### Rules for Future Testing

| Rule | Why |
|------|-----|
| **Never run >10 requests to the same URL in one session** | Triggers rate limiting and behavioral analysis |
| **Use diverse test sites** | Spread load across many domains |
| **Add delays between requests to same domain** | Minimum 5-10 seconds between requests |
| **Rotate test URLs** | Don't always test the same page |
| **Monitor for 403/challenge responses** | Stop immediately if you see Cloudflare challenges |

### Stress Testing Protocol

If you need to measure reliability/error rates:

```python
# BAD: Hammering one site
for i in range(200):
    crawl("https://talgraf.fi/yhteystiedot")  # Will get blocked!

# GOOD: Distributed testing
sites = ["jpond.fi", "showell.com", "solwers.com", "caverna.fi", ...]
for site in sites:
    for i in range(5):  # Max 5 per site
        crawl(site)
        time.sleep(10)  # Delay between requests
```

### What To Do If Blocked

1. **Accept it** — Once Cloudflare blocks a fingerprint, it's very difficult to unblock
2. **Don't retry** — More requests make it worse
3. **Document it** — Mark the site as blocked in the registry
4. **Move on** — Focus on the 100k+ other sites that work

---

## 📁 Key Files Reference

### Essential Files
- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** ← YOU ARE HERE
- **[TESTING_RESULTS.md](TESTING_RESULTS.md)** - Raw statistical data
- **[TEST_SITES_REGISTRY.md](../TEST_SITES_REGISTRY.md)** - All test sites with metadata

### Test Scripts
- **[test_site.py](test_site.py)** - Single site testing (updated with optimal config)
- **[test_regression.py](test_regression.py)** - Tier 1/2 regression suite

### Documentation
- **[CLAUDE.md](../CLAUDE.md)** - Main developer guide
- **[AITOSOFT_CHANGES.md](../AITOSOFT_CHANGES.md)** - Our modifications to upstream

---

## 🚀 Current Status (2026-01-26)

**Production validated**: 87.5% success rate on 160 fresh Finnish company URLs.

The optimal config (V11) is working well. Most failures are site-side issues (down, parked, shutdown) rather than crawl4ai issues.
