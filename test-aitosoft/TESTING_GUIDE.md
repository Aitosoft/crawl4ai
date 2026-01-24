# Crawl4AI Testing Guide - Complete Context

**Purpose**: Single source of truth for all testing work. Read this file at the start of any session to get full context.

**Last Updated**: 2026-01-24

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

### Phase 3 Complete: Cookie Wall Root Cause Found ✅

**Date**: 2026-01-24
**Status**: ✅ **SOLVED** - Root cause identified and fixed

#### 🚨 Critical Discovery

**The problem was NOT cookie consent walls - it was our config options!**

Two crawl4ai options were **destroying content** on cookie consent sites:

| Option | What it does | Problem |
|--------|--------------|---------|
| `magic=True` | Auto-handles popups | Removes cookie consent content (including the actual page!) |
| `remove_overlay_elements=True` | Removes overlays | Treats **entire page** as overlay on Cookiebot sites |

#### Test Results (4 MAS sites)

| Site | Before (magic=True) | After (optimal) | Improvement |
|------|---------------------|-----------------|-------------|
| **accountor.com** | 31 tokens ❌ | **14,492 tokens** ✅ | **467x better** |
| **monidor.com** | 15 tokens ❌ | **914 tokens** ✅ | **61x better** |
| **solwers.com** | 3,555 tokens | **5,671 tokens** ✅ | 60% better |
| **showell.com** | works | **22,401 tokens** ✅ | works |

**All 4 sites now work** - no special cookie handling needed.

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

### Tier 1 Test Sites (Always Test Before Deploy)

| Site | Challenge | Config | Expected | Status |
|------|-----------|--------|----------|--------|
| **talgraf.fi** | Cookie consent + 7% intermittent | optimal + retry | >95% with retry | ✅ |
| **vahtivuori.fi** | Email obfuscation `(at)` | optimal | LLM extracts all | ✅ |
| **accountor.com** | Cookiebot (was blocking) | **optimal** | 14k+ tokens | ✅ FIXED |
| **monidor.fi** | Was showing "verifying" | **optimal** | 900+ tokens | ✅ FIXED |

**Quality Gate**: All 4 must pass before production deploy.

### Tier 2 Test Sites (Extended Validation)

| Site | Type | Contact Page |
|------|------|--------------|
| **jpond.fi** | Software consulting | `/yhteystiedot/` |
| **neuroliitto.fi** | Non-profit | `/yhteystiedot/hallinto-ja-tukipalvelut/` |
| **solwers.com** | Public company | `/sijoittajat/hallinnointi/#johtoryhma` |
| **caverna.fi** | Restaurant | Homepage |
| **showell.com** | SaaS | Homepage |

---

## 🚨 Known Issues & Patterns

### Issue 1: Cookie Consent Sites ✅ SOLVED

**Affected Sites**: Enterprise sites (Accountor, Monidor, etc.)
**Symptom**: Returns 31 tokens instead of 14,000+ tokens
**Root Cause**: ~~Cookie consent blocking~~ **`magic=True` and `remove_overlay_elements=True` were removing the content!**
**Solution**: Use `optimal` config (magic=False, remove_overlay_elements=False)
**Status**: ✅ **SOLVED** - no special handling needed

### Issue 2: Intermittent Failures (talgraf.fi)

**Affected Sites**: talgraf.fi (7% contact page, 1% company page)
**Symptom**: Returns 1 char instead of full content
**Root Cause**: Site-specific (anti-bot, CDN, rate limiting - unconfirmed)
**Solution**: ✅ Retry logic (99.5% success with 1 retry)
**Status**: ✅ **SOLVED** - retry logic handles it

### Issue 3: Email Obfuscation ✅ SOLVED

**Affected Sites**: Many sites (vahtivuori.fi, jpond.fi use `(at)` pattern)
**Symptom**: Emails written as `info (at) company.com`
**Solution**: ✅ LLM extraction handles it naturally
**Status**: ✅ **SOLVED** - no action needed

---

## 🔬 What Needs Testing Next

### PRIORITY 1: Validate "Optimal" Config at Scale

**Why**: The solution seems too simple - need to validate on more sites
**Goal**: Confirm optimal config works on ALL Tier 1 and Tier 2 sites

**Tests Needed**:
1. Run all 9 test sites with optimal config
2. Compare tokens and contact extraction rates
3. Identify any sites that still fail
4. Document edge cases

**Success Criteria**:
- 100% of test sites return >500 tokens
- Contact data (emails/phones) found on all contact pages
- No regressions from previous working sites

### PRIORITY 2: Update MAS Repo Configuration

**Why**: MAS is using magic=True which breaks cookie consent sites
**Goal**: Update MAS TypeScript tool to use optimal config

**Action Items**:
1. Communicate findings to MAS team
2. Update crawler_config in MAS tool
3. Re-test the 2 sites that were failing in MAS

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
| **test_site.py** | Quick single-site testing | `python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot` |
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

## 🚀 Current Focus

**Active Priority**: Validate optimal config at scale
**Success Metric**: 100% success rate on all Tier 1 and Tier 2 sites
**Next Step**: Run comprehensive test on all 9 sites

**Ready to validate!**
