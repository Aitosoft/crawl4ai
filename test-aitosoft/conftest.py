"""
Shared pytest configuration for test-aitosoft/.

Three jobs:

1. Register the fixture-origin fixtures for every suite in this directory, so a
   new failure-class test is `def test_x(fixture_origin, production_path)` with
   no import ceremony. See fixture_origin.py.

2. Keep `pytest test-aitosoft/` meaning "the offline suites". The four modules
   below are CLI scripts run as `python test-aitosoft/<name>.py …` against a
   live server; three of their helpers happen to be named `test_*`, so pytest
   collected them and reported three errors on every clean run. A permanently
   red bar trains you to ignore the bar. Nothing here changes how they run from
   the command line.

3. Let CI run the suite without the stored corpus. `test-aitosoft/artifacts/`
   is gitignored (real customer captures, 35 MB), so the four tests marked
   `requires_corpus` have nothing to read on a fresh clone. **Only under CI**
   (GitHub Actions sets `CI=true`) do they skip; on a developer machine without
   the corpus they still fail, loudly, because there a missing corpus means
   the thresholds they guard are not being re-derived, and you should know.
   See `tasks/guard-corpus-is-not-in-the-repo.md`.
"""

import glob
import os

import pytest

from fixture_origin import (  # noqa: F401  (imported to register the fixtures)
    fixture_origin,
    production_path,
)

collect_ignore = [
    "test_regression.py",  # python test-aitosoft/test_regression.py --tier 1
    "test_site.py",  # python test-aitosoft/test_site.py <domain>
    "test_fingerprint.py",  # python test-aitosoft/test_fingerprint.py --label
    "test_soak.py",  # python test-aitosoft/test_soak.py --duration-min 30
]

ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")


def _corpus_present() -> bool:
    pattern = os.path.join(ARTIFACTS, "**", "*.json")
    return any(True for _ in glob.iglob(pattern, recursive=True))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_corpus: reads the gitignored test-aitosoft/artifacts/ corpus; "
        "skipped under CI when it is absent, fails elsewhere",
    )


def pytest_collection_modifyitems(config, items):
    if _corpus_present() or not os.environ.get("CI"):
        return
    skip = pytest.mark.skip(
        reason="test-aitosoft/artifacts/ corpus is gitignored and absent under CI"
    )
    for item in items:
        if "requires_corpus" in item.keywords:
            item.add_marker(skip)
