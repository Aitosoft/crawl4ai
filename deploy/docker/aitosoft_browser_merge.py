"""
Aitosoft: merge config.yml browser.kwargs into per-request BrowserConfig.

Upstream crawl4ai's deploy/docker/api.py calls BrowserConfig.load(request_dict)
directly, which produces a BrowserConfig with class defaults (Chrome 116,
no stealth, bundled Chromium) when the request omits browser_config fields.
This means config.yml.crawler.browser.kwargs only affects the PERMANENT
browser, which is rarely hit because its signature differs from the
all-defaults signature used by bare requests.

This helper merges config.yml defaults underneath the user's browser_config
so that:
  - config.yml becomes the real baseline for every request
  - per-request overrides in browser_config win over the baseline
  - extra_args uses the user's list if provided, else falls back to config.yml

Used by: api.handle_crawl_request, api.handle_stream_crawl_request.

This is an Aitosoft modification — see AITOSOFT_CHANGES.md "Stealth Package
(2026-04-11)" for the why.
"""

from typing import Any, Dict, Optional

from crawl4ai import BrowserConfig


def merge_browser_config(
    user_browser_config: Optional[Dict[str, Any]],
    config: Dict[str, Any],
) -> BrowserConfig:
    """Build a BrowserConfig from config.yml defaults with user overrides on top."""
    user = dict(user_browser_config or {})

    # If user sent a fully serialized BrowserConfig ({type, params} shape),
    # respect the complete object and skip the merge. Aitosoft clients don't
    # use this shape today, but upstream tests and playground requests do.
    if "type" in user and "params" in user:
        return BrowserConfig.load(user)

    yml_browser = (config.get("crawler", {}) or {}).get("browser", {}) or {}
    yml_kwargs = dict(yml_browser.get("kwargs", {}) or {})
    yml_extra_args = list(yml_browser.get("extra_args", []) or [])

    merged: Dict[str, Any] = {**yml_kwargs, **user}

    if "extra_args" not in merged:
        merged["extra_args"] = yml_extra_args

    return BrowserConfig.load(merged)
