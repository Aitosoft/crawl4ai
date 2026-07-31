"""
Shared pytest configuration for test-aitosoft/.

Two jobs:

1. Register the fixture-origin fixtures for every suite in this directory, so a
   new failure-class test is `def test_x(fixture_origin, production_path)` with
   no import ceremony. See fixture_origin.py.

2. Keep `pytest test-aitosoft/` meaning "the offline suites". The four modules
   below are CLI scripts run as `python test-aitosoft/<name>.py …` against a
   live server; three of their helpers happen to be named `test_*`, so pytest
   collected them and reported three errors on every clean run. A permanently
   red bar trains you to ignore the bar. Nothing here changes how they run from
   the command line.
"""

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
