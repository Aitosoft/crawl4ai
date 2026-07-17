# Archived Testing Files (historical — do not act on these)

Everything in this directory describes the **January 2026 talgraf.fi
reliability investigation**, which is complete. It predates the stealth
package, the v0.9.x untrusted-config boundary, and the render-admission
gate. Configs shown in these files (e.g. `magic: true`) are rejected by
the current server, and talgraf.fi is a **retired test site** (permanently
Cloudflare-blocked by the over-scraping this very study performed — see
the site-safety rules in TESTING.md). Kept as history only.

The study's runner scripts (`test_reliability_study.py`, `test_isolation.py`,
`test_concurrency.py`, `test_batching_reliability.py`) were deleted 2026-07-17;
they live in git history if ever needed.

## Phase 1-2: Reliability Testing (Complete)

**Investigation Period**: 2026-01-22
**Status**: ✅ Complete
**Conclusion**: talgraf.fi 7% failure is site-specific, NOT a crawl4ai issue

### Files

- **TESTING_PROTOCOL.md** - The study's runbook (moved here from repo root 2026-07-17)
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

Current testing framework and priorities: [../../TESTING.md](../../TESTING.md).
(The old `TESTING_GUIDE.md` / `TESTING_RESULTS.md` this README used to link
were deleted in the 2026-07-16 doc cleanup.)
