# Archived Testing Files

This directory contains archived files from completed testing phases.

## Phase 1-2: Reliability Testing (Complete)

**Investigation Period**: 2026-01-22
**Status**: ✅ Complete
**Conclusion**: talgraf.fi 7% failure is site-specific, NOT a crawl4ai issue

### Files

- **PHASE_2_COMPLETE.md** - Executive summary of Phase 1-2 findings
- **NEXT_SESSION_DEEP_DIVE.md** - Original handoff prompt for Phase 3
- **FINDINGS_AND_RECOMMENDATIONS.md** - Detailed analysis
- **CONCURRENCY_FINDINGS.md** - Concurrency testing results
- **NEXT_SESSION_PROMPT.md** - Earlier handoff prompt
- **test-task.md** - Original task description from MAS repo

### Key Findings (Summary)

- ✅ talgraf.fi: 7% contact page failure, 1% company page failure
- ✅ jpond.fi: 0% failure on both pages (200 trials)
- ✅ Issue is site-specific, not systemic
- ✅ Retry logic achieves 99.5% success (1 retry), 99.97% (2 retries)

### Current Work

**Active**: See [../TESTING_GUIDE.md](../TESTING_GUIDE.md) for current priorities and status.

**Latest Results**: See [../TESTING_RESULTS.md](../TESTING_RESULTS.md) for raw data.
