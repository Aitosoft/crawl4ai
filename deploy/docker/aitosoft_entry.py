"""
Aitosoft wrapper entry point for crawl4ai Docker server.

Loaded by gunicorn/uvicorn instead of server:app. This lets upstream
server.py stay unmodified while we inject:
  1. BrowserConfig class-level defaults from config.yml
  2. Simple static-token auth middleware

See AITOSOFT_CHANGES.md for rationale.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from crawl4ai import BrowserConfig  # noqa: E402
from utils import load_config  # noqa: E402

# ── Apply config.yml browser kwargs as BrowserConfig class defaults ──
# This replaces the old aitosoft_browser_merge.py module. Every
# BrowserConfig.load({}) call in api.py now inherits stealth, chrome
# channel, UA, viewport, etc. from config.yml automatically — upstream's
# own set_defaults() mechanism (async_configs.py @_with_defaults).
_config = load_config()
_yml_browser = (_config.get("crawler", {}) or {}).get("browser", {}) or {}
_yml_kwargs = dict(_yml_browser.get("kwargs", {}) or {})
_yml_extra_args = list(_yml_browser.get("extra_args", []) or [])
if _yml_extra_args:
    _yml_kwargs["extra_args"] = _yml_extra_args
BrowserConfig.set_defaults(**_yml_kwargs)  # type: ignore[attr-defined]

# ── Import the upstream app (server.py is NOT modified) ──
from server import app  # noqa: E402

# ── Add static token auth middleware ──
# Only active when CRAWL4AI_API_TOKEN env var is set. In dev without
# the env var, all endpoints are open (same as upstream default).
if os.environ.get("CRAWL4AI_API_TOKEN"):
    from simple_token_auth import SimpleTokenAuthMiddleware  # noqa: E402

    app.add_middleware(SimpleTokenAuthMiddleware)
