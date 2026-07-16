"""
Aitosoft wrapper entry point for the crawl4ai Docker server.

Loaded by gunicorn instead of server:app (see supervisord.conf). This lets
upstream server.py stay (nearly) unmodified while we inject deployment
behavior at import time:

  1. BrowserConfig class-level defaults from config.yml (stealth, real
     Chrome, UA, viewport) — upstream's own set_defaults() mechanism.
  2. Trusted-client relaxations of the v0.9.0 untrusted-config boundary.

Auth note: our old SimpleTokenAuthMiddleware was removed in the v0.9.2
upgrade — upstream's AuthGateMiddleware now provides the same contract
(Authorization: Bearer $CRAWL4AI_API_TOKEN) with constant-time comparison,
fail-closed startup, and coverage of every route/mount/WebSocket.

See AITOSOFT_CHANGES.md for rationale.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import crawl4ai.async_configs as _ac  # noqa: E402
from crawl4ai import BrowserConfig  # noqa: E402
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
# Upstream v0.9.0 treats every network request body as untrusted and rejects
# or clamps "power fields". This service is single-tenant: the only client is
# MAS, authenticated with a bearer token. Two upstream defaults break MAS's
# existing request contract, so we relax exactly those and nothing else
# (js_code, proxies, extra_args, cdp_url etc. all stay forbidden —
# defense-in-depth against a leaked token):
#
#  1. browser_config.headers — MAS sends per-company persona headers
#     (Accept-Language, sec-ch-ua). Header values only shape outbound
#     requests to crawl targets; they cannot execute code or reroute
#     traffic, and egress is still pinned by the SSRF broker.
_ac.UNTRUSTED_FORBIDDEN_FIELDS["BrowserConfig"].discard("headers")
_ac.UNTRUSTED_FIELD_ALLOWLIST["BrowserConfig"].add("headers")

#  2. page_timeout clamp — upstream caps it at 60s; MAS legitimately sends
#     90s for slow SPA sites. Raise the cap to our wall-clock deadline
#     (config.yml limits.wall_clock_s = 180s) so the per-page timeout can
#     never exceed the request deadline anyway.
_ac._MAX_TIMEOUT_MS = 180_000

# ── Import the upstream app (auth gate + middleware come with it) ──
from server import app  # noqa: E402, F401
