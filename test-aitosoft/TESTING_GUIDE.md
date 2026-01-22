# Crawl4AI Testing Guide - Complete Context

**Purpose**: Single source of truth for all testing work. Read this file at the start of any session to get full context.

**Last Updated**: 2026-01-22

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

**Critical Success Factors**:
1. **High success rate**: Need 95%+ success across diverse sites
2. **Cookie consent handling**: Many enterprise sites use Cookie Bot/OneTrust
3. **Contact extraction reliability**: Raw markdown > fit_markdown for contact data
4. **Cost efficiency**: Use fast config when possible (2-4s vs 30-60s)

---

## 📊 Current Status - What We Know

### Phase 1-2 Complete: Reliability Baseline ✅

**Sample Size**: 400 isolated requests across 2 sites
**Status**: Investigation complete, root cause identified

#### Key Findings

| Finding | Evidence | Impact |
|---------|----------|--------|
| **talgraf.fi has site-specific 7% failure** | 200 trials: 7% contact page, 1% company page | Need retry logic |
| **jpond.fi works perfectly** | 200 trials: 0% failures on both pages | Proves crawl4ai is reliable |
| **Issue is NOT systemic** | Statistical significance confirmed | No need to fix crawl4ai |
| **Retry logic solves it** | 1 retry = 99.5% success, 2 retries = 99.97% | Deploy and move on |

**Conclusion**: The intermittent 1-char failure is **talgraf.fi-specific**, not a crawl4ai bug.

### Tier 1 Test Sites (Quality Gates)

**Must test these 4 sites before any deploy:**

| Site | Challenge | Config Needed | Success Criteria |
|------|-----------|---------------|------------------|
| **talgraf.fi** | Cookie consent + intermittent 7% failures | fast + retry | >95% with retry |
| **vahtivuori.fi** | Email obfuscation `(at)` | fast | LLM extracts all emails |
| **accountor.com** | Cookie wall (Cookie Bot) | heavy (magic + scan_full_page + networkidle) | 14k+ tokens |
| **monidor.fi** | Clean baseline | fast | Perfect extraction |

**Quality Gate**: All 4 must pass before production deploy.

### Config Learnings (MAS V1-V10)

| Learning | Evidence | Recommendation |
|----------|----------|----------------|
| **`magic=true` + `scan_full_page=true` solves cookie walls** | Accountor: 32 tokens → 14,493 tokens | Use for cookie consent sites |
| **Raw markdown > fit_markdown for contacts** | PruningContentFilter removes contact data at threshold ≥0.35 | Use raw_markdown for extraction |
| **LLM handles obfuscation naturally** | JPond: all 19 `(at)` emails extracted | No special preprocessing needed |
| **Use fast config by default** | 90% of sites work with domcontentloaded | Reserve heavy for edge cases |

**Fast Config** (default):
```python
{
    "wait_until": "domcontentloaded",
    "page_timeout": 60000,
    "magic": True,
    "scan_full_page": True
}
```

**Heavy Config** (cookie walls only):
```python
{
    "wait_until": "networkidle",
    "page_timeout": 60000,
    "magic": True,
    "scan_full_page": True
}
```

---

## 🚨 Known Issues & Patterns

### Issue 1: Cookie Consent Walls (HIGH PRIORITY)
**Affected Sites**: Enterprise sites (Accountor, many large companies)
**Symptom**: Returns 32 tokens instead of 14,000+ tokens
**Root Cause**: Cookie Bot, OneTrust, GDPR consent popups block content
**Solution**: Use heavy config (magic=true, scan_full_page=true, wait_until=networkidle)
**Impact**: **Blocks entire site categories** - thousands of enterprise sites affected
**Status**: ⚠️ **NEEDS INVESTIGATION** - manual config works, need auto-detection

### Issue 2: Intermittent Failures (talgraf.fi)
**Affected Sites**: talgraf.fi (7% contact page, 1% company page)
**Symptom**: Returns 1 char instead of full content
**Root Cause**: Site-specific (anti-bot, CDN, rate limiting - unconfirmed)
**Solution**: ✅ Retry logic (99.5% success with 1 retry)
**Impact**: Low - site-specific, retry logic solves it
**Status**: ✅ **SOLVED** - no further action needed

### Issue 3: Email Obfuscation
**Affected Sites**: Many sites (vahtivuori.fi, jpond.fi use `(at)` pattern)
**Symptom**: Emails written as `info (at) company.com`
**Solution**: ✅ LLM extraction handles it naturally
**Impact**: None - already works
**Status**: ✅ **SOLVED** - no action needed

---

## 🔬 What Needs Testing Next

### PRIORITY 1: Cookie Consent Detection & Handling 🔥
**Why**: Blocks thousands of enterprise sites (highest value targets)
**Goal**: Auto-detect cookie consent → use heavy config only when needed

**Tests Needed**:
1. Find 15-20 sites with Cookie Bot/OneTrust
2. Test fast config (baseline failure rate)
3. Test heavy config (expected success)
4. Build detection logic (scan HTML for cookie consent keywords/elements)
5. Prototype auto-upgrade (detect → use heavy config)
6. Measure false positive/negative rates

**Success Criteria**:
- Auto-detect cookie walls with 95%+ accuracy
- Achieve 95%+ success rate on cookie consent sites
- Minimize false positives (don't waste time on sites that don't need heavy config)

### PRIORITY 2: Site Categorization Framework
**Why**: Enables intelligent config selection for 100k+ sites
**Goal**: Predict which config to use before crawling

**Tests Needed**:
1. Create site type taxonomy (Simple, Cookie Wall, Intermittent, Anti-Bot)
2. Test detection heuristics (domain, initial request, robots.txt)
3. Build decision tree (fast → detect failure → upgrade to heavy)

**Success Criteria**:
- 90%+ of sites use fast config (cost efficiency)
- 95%+ overall success rate
- <5% false upgrades to heavy config

### PRIORITY 3: talgraf.fi Deep Dive (Optional)
**Why**: Academic interest - retry already solves it
**Goal**: Understand WHY it fails 7% of the time

**Tests Needed**:
1. Capture screenshots on success vs failure
2. Compare network logs
3. Test timing variations

**Success Criteria**: Understand root cause (educational only)

---

## 🛠️ Test Infrastructure

### API Endpoint
```bash
https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io/crawl
```

### Authentication
```bash
export CRAWL4AI_API_TOKEN="crawl4ai-252ac94a0d8d54c85b2a02f5cf2215ca55fea74f70100a5d"
```

### Key Test Scripts

**Location**: `test-aitosoft/`

| Script | Purpose | Example Usage |
|--------|---------|---------------|
| **test_reliability_study.py** | Large-scale reliability testing (100+ trials) | `python test-aitosoft/test_reliability_study.py --mode isolated --url yhteystiedot --count 100` |
| **test_site.py** | Quick single-site testing with artifacts | `python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot` |
| **test_regression.py** | Run Tier 1 regression tests | `python test-aitosoft/test_regression.py --tier 1 --version pre-deploy` |

### Quick Start - Run a Test

```bash
# 1. Ensure you're in the repo root
cd /workspaces/crawl4ai-aitosoft

# 2. Set API token (already in .env, but can export manually)
export CRAWL4AI_API_TOKEN="crawl4ai-252ac94a0d8d54c85b2a02f5cf2215ca55fea74f70100a5d"

# 3. Run a quick test
python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot

# 4. Run reliability study (100 trials)
python test-aitosoft/test_reliability_study.py --mode isolated --url yhteystiedot --count 100

# 5. Run Tier 1 regression (before deploy)
python test-aitosoft/test_regression.py --tier 1 --version pre-deploy
```

### Test Results Location

```
test-aitosoft/results/
├── reliability-study-isolated-yhteystiedot-YYYYMMDD_HHMMSS.json
├── reliability-study-isolated-yritys-YYYYMMDD_HHMMSS.json
├── reliability-study-isolated-jpond-company-YYYYMMDD_HHMMSS.json
└── reliability-study-isolated-jpond-contact-YYYYMMDD_HHMMSS.json
```

**Latest Results Summary**: See [TESTING_RESULTS.md](TESTING_RESULTS.md)

---

## 📁 Key Files Reference

### Essential Files (Read These)
- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** ← YOU ARE HERE (session starter)
- **[TESTING_RESULTS.md](TESTING_RESULTS.md)** - Raw statistical data from all tests
- **[TEST_SITES_REGISTRY.md](TEST_SITES_REGISTRY.md)** - All test sites with metadata
- **[TESTING.md](../TESTING.md)** - Testing framework and best practices

### Archived Files (Phase 1-2 Complete)
- `test-aitosoft/archive/PHASE_2_COMPLETE.md` - Executive summary (archived)
- `test-aitosoft/archive/NEXT_SESSION_DEEP_DIVE.md` - Old handoff prompt (archived)

### Documentation
- **[CLAUDE.md](../CLAUDE.md)** - Main developer guide (auto-loaded)
- **[AITOSOFT_CHANGES.md](../AITOSOFT_CHANGES.md)** - Our modifications to upstream
- **[DEPLOYMENT_INFO.md](../DEPLOYMENT_INFO.md)** - Production deployment info

---

## 🎬 Starting a New Session - Quick Checklist

**Before you start coding/testing:**

1. ✅ Read [CLAUDE.md](../CLAUDE.md) (auto-loaded)
2. ✅ Read this file ([TESTING_GUIDE.md](TESTING_GUIDE.md))
3. ✅ Check [TESTING_RESULTS.md](TESTING_RESULTS.md) for latest stats
4. ✅ Review current priority (see "What Needs Testing Next")
5. ✅ Confirm API token is set: `echo $CRAWL4AI_API_TOKEN`

**You should now know:**
- ✅ Relationship with MAS repo
- ✅ What's been tested (Phase 1-2: 400 trials)
- ✅ Known issues (cookie consent, talgraf.fi intermittent)
- ✅ What to test next (Priority 1: Cookie consent auto-detection)
- ✅ How to run tests (scripts, API endpoint, token)

---

## 💡 Key Principles

1. **MAS context matters**: Every decision impacts 100k+ site crawling
2. **Contact extraction is #1**: All other metrics are secondary
3. **Cost efficiency**: Fast config (2-4s) vs Heavy config (30-60s) - use wisely
4. **Enterprise sites = cookie walls**: This is the biggest blocker
5. **Raw markdown for extraction**: fit_markdown removes contact data
6. **Retry logic works**: 99.5% success, deploy and move on
7. **Test before deploy**: All Tier 1 sites must pass

---

## 🚀 Current Focus

**Active Priority**: Cookie Consent Detection & Handling
**Next Session Goal**: Auto-detect cookie walls → use heavy config only when needed
**Success Metric**: 95%+ success rate on enterprise sites with automatic detection

**Ready to start testing!**
