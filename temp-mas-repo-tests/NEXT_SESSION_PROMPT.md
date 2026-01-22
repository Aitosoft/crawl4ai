# Crawl4AI Reliability Testing - Next Session

## Context

We're investigating intermittent 1-char failures in the crawl4ai service to determine if it's site-specific or systemic.

## What We've Learned So Far

**Phase 1 Complete**: Tested talgraf.fi with 200 isolated requests (statistically significant)

| URL | Failure Rate | Pattern |
|-----|--------------|---------|
| `/yhteystiedot/` (contact page) | 7.0% (7/100) | Returns 1 char instead of ~7,000 |
| `/yritys/` (company page) | 1.0% (1/100) | Returns 1 char instead of ~12,000 |

**Key Finding**: Contact page fails 7x more often than company page (7% vs 1%)

**Question**: Is this talgraf.fi-specific or do other sites show the same pattern?

## Next Testing Goal

Test **jpond.fi** to compare contact vs company page failure rates:

- **Company page**: `https://jpond.fi/jpond-oy/`
- **Contact page**: `https://jpond.fi/yhteystiedot/`

**Hypothesis**: If jpond.fi shows similar pattern (contact fails more than company), it suggests a systemic issue with contact page complexity/JS. If rates are equal or reversed, it's talgraf.fi-specific.

## Key Files

**Testing infrastructure**:
- `test-aitosoft/test_reliability_study.py` - Master test script
- `test-aitosoft/TESTING_RESULTS.md` - Phase 1 results and analysis

**Commands** (use export token first):
```bash
# Load token from .env file in crawl4ai repo
source /path/to/crawl4ai-aitosoft/.env
# Or manually: export CRAWL4AI_API_TOKEN="<see-crawl4ai-repo-.env-file>"

# Test JPond company page (100 requests, ~2 hours)
python test-aitosoft/test_reliability_study.py --mode isolated --url jpond-company --count 100

# Test JPond contact page (100 requests, ~2 hours)
python test-aitosoft/test_reliability_study.py --mode isolated --url jpond-contact --count 100
```

**Note**: You'll need to modify the script to add JPond URLs to the `URLS` dictionary:
```python
URLS = {
    "yhteystiedot": "https://www.talgraf.fi/yhteystiedot/",
    "yritys": "https://www.talgraf.fi/yritys/",
    "jpond-company": "https://jpond.fi/jpond-oy/",      # ADD THIS
    "jpond-contact": "https://jpond.fi/yhteystiedot/",  # ADD THIS
}
```

## What to Look For

1. **Failure rates**: Does jpond-contact fail more than jpond-company?
2. **Magnitude**: Are failure rates similar to talgraf (1-7%) or different?
3. **Pattern**: All failures return exactly 1 char?

## Expected Outcome

After testing, update `test-aitosoft/TESTING_RESULTS.md` with:
- New section: "### Phase 2: Cross-Site Validation (jpond.fi)"
- Comparison table showing talgraf vs jpond failure rates
- Conclusion: Site-specific vs systemic issue

## Context from Previous Session

- We already have proven solution: **retry logic** → 99.5% success
- MAS team should deploy retry logic regardless of Phase 2 outcome
- This Phase 2 testing is about understanding root cause, not finding solution
