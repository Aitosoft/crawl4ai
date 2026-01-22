# Test Scripts

This directory contains test scripts for validating crawl4ai service behavior.

---

## Reliability Study (Active Investigation)

**Goal**: Understand and solve intermittent failures on talgraf.fi

### Active Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| **[test_reliability_study.py](test_reliability_study.py)** | Master test script for 100+ trial testing | See [TESTING_PROTOCOL.md](../TESTING_PROTOCOL.md) |
| [test_isolation.py](test_isolation.py) | Initial isolation testing (completed) | Reference only |
| [test_batching_reliability.py](test_batching_reliability.py) | Batching validation (completed) | Reference only |
| [test_concurrency.py](test_concurrency.py) | Proved NOT a concurrency issue (completed) | Reference only |

### Results

- **Current findings**: [TESTING_RESULTS.md](TESTING_RESULTS.md)
- **Raw data**: [results/](results/) directory
- **Next steps**: See [TESTING_PROTOCOL.md](../TESTING_PROTOCOL.md)

---

## Production Testing Scripts

| Script | Purpose |
|--------|---------|
| [test_site.py](test_site.py) | Test single sites with different configs |
| [test_regression.py](test_regression.py) | Run Tier 1 regression tests |
| [test_production_auth.py](test_production_auth.py) | Validate production authentication |

### Usage Examples

```bash
# Test a single site
python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot

# Test with heavy config (for cookie walls)
python test-aitosoft/test_site.py accountor.com --config heavy

# Run Tier 1 regression
python test-aitosoft/test_regression.py --tier 1
```

---

## Documentation

- **Test Sites Registry**: [../TEST_SITES_REGISTRY.md](../TEST_SITES_REGISTRY.md)
- **Testing Framework**: [../TESTING.md](../TESTING.md)
- **MAS Integration Findings**: [../temp-mas-repo-tests/](../temp-mas-repo-tests/)

---

**Last Updated**: 2026-01-22
