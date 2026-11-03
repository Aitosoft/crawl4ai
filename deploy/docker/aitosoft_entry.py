"""
Aitosoft wrapper entry point for the crawl4ai Docker server.

Loaded by gunicorn instead of server:app (see supervisord.conf). This lets
upstream server.py stay (nearly) unmodified while we inject deployment
behavior at import time:

  1. BrowserConfig class-level defaults from config.yml (stealth, real
     Chrome, UA, viewport) — upstream's own set_defaults() mechanism.
  2. Trusted-client relaxations of the v0.9.0 untrusted-config boundary
     (see aitosoft_trust.py; contract pinned by test_mas_contract.py),
     including the page_timeout cap and TLS tolerance.
  3. Upstream's cloud-notice console banner switched off.

Auth note: our old SimpleTokenAuthMiddleware was removed in the v0.9.2
upgrade — upstream's AuthGateMiddleware now provides the same contract
(Authorization: Bearer $CRAWL4AI_API_TOKEN) with constant-time comparison,
fail-closed startup, and coverage of every route/mount/WebSocket.

See AITOSOFT_CHANGES.md for rationale.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from crawl4ai import BrowserConfig  # noqa: E402
from aitosoft_trust import apply_trust_relaxations  # noqa: E402
from utils import load_config  # noqa: E402

# ── Apply config.yml browser kwargs as BrowserConfig class defaults ──
# Every BrowserConfig.load({}) call in api.py inherits stealth, chrome
# channel, UA, viewport, etc. from config.yml automatically — upstream's
# own set_defaults() mechanism (async_configs.py @_with_defaults).
_config = load_config()
_yml_browser = (_config.get("crawler", {}) or {}).get("browser", {}) or {}
_yml_kwargs = dict(_yml_browser.get("kwargs", {}) or {})
_yml_extra_args = list(_yml_browser.get("extra_args", []) or [])
if _yml_extra_args:
    _yml_kwargs["extra_args"] = _yml_extra_args
BrowserConfig.set_defaults(**_yml_kwargs)  # type: ignore[attr-defined]

# ── Trusted-client relaxations of the untrusted-config boundary ──
apply_trust_relaxations()

# ── Upstream's "Crawl4AI Cloud" console banner, off ──
# crawl4ai/cloud_notice.py (v0.9.5) prints a multi-line rich banner to stderr
# once a day per container until 2027-01-01, and again on the first block of
# the day. Every new ACA replica is a new container, and the console logger
# wraps it across Log Analytics rows. Read at call time, so setting it here,
# before the server imports, covers every crawler this process starts.
os.environ.setdefault("CRAWL4AI_NO_CLOUD_NOTICE", "1")

# ── Import the upstream app (auth gate + middleware come with it) ──
from server import app  # noqa: E402, F401
