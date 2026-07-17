# Testing Protocol: Crawl4AI Reliability Study

**Goal**: Gather 100+ data points to validate failure rates and solution effectiveness
**Last Updated**: 2026-01-22
**Status**: In progress (14 isolated, 20 batched trials completed)

---

## Current Understanding

### Observed Behavior

- `/yhteystiedot/` fails intermittently (~7% based on 14 trials)
- Failures return **1 char** instead of expected ~7,000 chars
- **NOT concurrency-related** (happens even alone with delays)
- `/yritys/` has 0% failure rate (13/13 successes)

### Hypotheses to Test

1. **Hypothesis 1**: Baseline failure rate is ~7% for `/yhteystiedot/`
   - **Test**: 100 isolated requests to `/yhteystiedot/`
   - **Expected**: 5-10 failures (if 7% is accurate)

2. **Hypothesis 2**: Batching reduces failure rate
   - **Test**: 100 batched requests (2 URLs per request)
   - **Expected**: <5 failures if batching helps, ~7 failures if it doesn't

3. **Hypothesis 3**: `/yritys/` is 100% reliable
   - **Test**: 100 isolated requests to `/yritys/`
   - **Expected**: 0 failures

4. **Hypothesis 4**: Retry logic achieves 99%+ success
   - **Test**: 100 requests with one retry on failure
   - **Expected**: 0-1 failures (99.5% theoretical success)

---

## Test Scripts

### 1. Master Test Script

**Location**: [test-aitosoft/test_reliability_study.py](test-aitosoft/test_reliability_study.py)

**Usage**:
```bash
export CRAWL4AI_API_TOKEN="..."

# Run 100 isolated requests to /yhteystiedot/
python test-aitosoft/test_reliability_study.py --mode isolated --url yhteystiedot --count 100

# Run 100 isolated requests to /yritys/
python test-aitosoft/test_reliability_study.py --mode isolated --url yritys --count 100

# Run 100 batched requests (both URLs)
python test-aitosoft/test_reliability_study.py --mode batched --count 100

# Run 100 requests with retry logic
python test-aitosoft/test_reliability_study.py --mode retry --url yhteystiedot --count 100
```

**Output**:
- Saves results to `test-aitosoft/results/reliability-study-{timestamp}.json`
- Generates summary report
- Appends to cumulative results file

### 2. Previous Test Scripts (Reference)

| Script | Purpose | Sample Size | Key Finding |
|--------|---------|-------------|-------------|
| [test_isolation.py](test-aitosoft/test_isolation.py) | Initial isolation testing | 14 requests | 7% failure rate |
| [test_batching_reliability.py](test-aitosoft/test_batching_reliability.py) | Batching validation | 20 batches | 0% failure rate |
| [test_concurrency.py](test-aitosoft/test_concurrency.py) | Concurrency investigation | 3 scenarios | Proved NOT concurrency |

---

## Data Collection Plan

### Phase 1: Establish Baseline (Target: 100 trials)

**Test A**: Isolated `/yhteystiedot/` requests
```bash
python test-aitosoft/test_reliability_study.py --mode isolated --url yhteystiedot --count 100
```

**Expected outcome**:
- Confirm ~7% failure rate (or discover true rate)
- Identify any patterns (time of day, service state, etc.)

**Test B**: Isolated `/yritys/` requests
```bash
python test-aitosoft/test_reliability_study.py --mode isolated --url yritys --count 100
```

**Expected outcome**:
- Validate 0% failure rate
- Confirm this is specific to `/yhteystiedot/`

### Phase 2: Validate Solutions (Target: 100 trials each)

**Test C**: Batched requests
```bash
python test-aitosoft/test_reliability_study.py --mode batched --count 100
```

**Expected outcome**:
- If batching helps: <5% failure rate
- If batching doesn't help: ~7% failure rate
- Statistical significance with 100 trials

**Test D**: Retry logic
```bash
python test-aitosoft/test_reliability_study.py --mode retry --url yhteystiedot --count 100
```

**Expected outcome**:
- 99%+ success rate (theoretical: 99.5%)
- Validate retry as reliable solution

---

## Results Format

### JSON Output

```json
{
  "test_date": "2026-01-22T14:30:00Z",
  "mode": "isolated",
  "url": "yhteystiedot",
  "total_requests": 100,
  "successes": 93,
  "failures": 7,
  "failure_rate": 0.07,
  "avg_success_chars": 7058,
  "avg_failure_chars": 1,
  "avg_response_time": 4.2,
  "raw_results": [
    {"iteration": 1, "success": true, "chars": 7058, "elapsed": 4.1},
    {"iteration": 2, "success": false, "chars": 1, "elapsed": 3.7},
    // ...
  ]
}
```

### Summary Report

```
================================================================================
RELIABILITY STUDY SUMMARY
================================================================================
Test Date: 2026-01-22 14:30:00
Mode: isolated
URL: /yhteystiedot/
Total Requests: 100

Results:
  ✅ Successes: 93/100 (93.0%)
  ❌ Failures: 7/100 (7.0%)

Statistics:
  Success avg: 7,058 chars (±0)
  Failure avg: 1 chars (±0)
  Avg response time: 4.2s

Failure Pattern:
  Iteration 2: 1 char
  Iteration 15: 1 char
  Iteration 23: 1 char
  Iteration 47: 1 char
  Iteration 68: 1 char
  Iteration 79: 1 char
  Iteration 91: 1 char

Conclusion:
  Baseline failure rate confirmed: ~7%
  No obvious temporal pattern detected
================================================================================
```

---

## Statistical Analysis

### Sample Size Justification

**For 95% confidence interval**:

With baseline failure rate p = 0.07 and n = 100 trials:

```
Standard error = sqrt(p(1-p)/n) = sqrt(0.07 × 0.93 / 100) ≈ 0.026
95% CI = p ± 1.96 × SE = 0.07 ± 0.05 = [2%, 12%]
```

**With 100 trials**, we can confidently say the true failure rate is between 2-12%.

### Comparing Batched vs Isolated

**Question**: Does batching reduce failure rate?

**Test**: Two-proportion z-test

```python
from scipy.stats import proportions_ztest

isolated_failures = 7  # out of 100
batched_failures = ?   # out of 100 (to be measured)

stat, p_value = proportions_ztest(
    [isolated_failures, batched_failures],
    [100, 100]
)

if p_value < 0.05:
    print("Batching significantly reduces failures")
else:
    print("No significant difference")
```

---

## Test Execution Checklist

### Before Starting

- [ ] Set `CRAWL4AI_API_TOKEN` environment variable
- [ ] Ensure crawl4ai service is running (health check: `curl https://...wonderfulsea.../health`)
- [ ] Create results directory: `mkdir -p test-aitosoft/results`
- [ ] Note start time and conditions (time of day, any service issues)

### During Testing

- [ ] Monitor test progress (check console output)
- [ ] Watch for service errors or timeouts
- [ ] Note any anomalies (unusual response times, errors)
- [ ] Take breaks between large batches to avoid overwhelming service

### After Testing

- [ ] Review JSON results file
- [ ] Check summary report
- [ ] Update [TESTING_RESULTS.md](test-aitosoft/TESTING_RESULTS.md) with findings
- [ ] Commit results to repo: `git add test-aitosoft/results/ && git commit -m "[testing] Add reliability study results"`

---

## Interpreting Results

### Scenario 1: Baseline confirmed (~7% failure rate)

**Finding**: `/yhteystiedot/` fails 5-10% of the time

**Conclusion**: This is a page-specific or service-level issue

**Recommendation**: Implement retry logic (99.5% expected success)

### Scenario 2: Batching eliminates failures

**Finding**: Batched requests have 0-2% failure rate (vs 7% isolated)

**Conclusion**: `arun_many()` has better page loading coordination than `arun()`

**Recommendation**: Implement batching at MAS tool level

### Scenario 3: Both methods fail similarly

**Finding**: Batched requests also fail ~7% of the time

**Conclusion**: Issue is at page/service level, not request method

**Recommendation**:
- Implement retry logic
- Or investigate page-specific issues (redirects, JS timing, etc.)
- Or increase `page_timeout` or use `networkidle`

### Scenario 4: Failure rate is much higher than 7%

**Finding**: >15% failure rate in 100 trials

**Conclusion**: Initial 7% was statistical noise, true rate is higher

**Recommendation**: Escalate issue, investigate crawl4ai service stability

### Scenario 5: Failure rate is much lower than 7%

**Finding**: <3% failure rate in 100 trials

**Conclusion**: Initial 7% was an outlier, issue is rare

**Recommendation**: Accept occasional failures, simple retry sufficient

---

## Next Steps After 100 Trials

1. **Analyze results** using statistical tests (see above)
2. **Update documentation** with confirmed failure rates
3. **Choose solution** based on evidence:
   - If batching helps: Implement batching
   - If batching doesn't help: Implement retry
4. **Test chosen solution** with another 100 trials
5. **Document final recommendation** for MAS team

---

## Files Reference

| File | Purpose |
|------|---------|
| [test_reliability_study.py](test-aitosoft/test_reliability_study.py) | Master test script |
| [TESTING_RESULTS.md](test-aitosoft/TESTING_RESULTS.md) | Cumulative findings |
| [results/](test-aitosoft/results/) | JSON data files |
| [CONCURRENCY_FINDINGS.md](temp-mas-repo-tests/CONCURRENCY_FINDINGS.md) | Detailed analysis |
| [FINDINGS_AND_RECOMMENDATIONS.md](temp-mas-repo-tests/FINDINGS_AND_RECOMMENDATIONS.md) | Summary for MAS |

---

## Questions to Answer

- [ ] What is the true baseline failure rate for `/yhteystiedot/`? (Target: 95% CI)
- [ ] Does `/yritys/` truly have 0% failure rate?
- [ ] Does batching reduce failures statistically significantly?
- [ ] Does retry logic achieve 99%+ success rate?
- [ ] Are there temporal patterns (time of day, service state)?
- [ ] Is this specific to talgraf.fi or do other sites have similar issues?

---

**Status**: Ready to begin Phase 1 testing (100 isolated requests)
