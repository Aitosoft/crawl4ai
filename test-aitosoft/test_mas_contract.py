"""
MAS request-contract regression test — OFFLINE, no server, no network.

Pins the exact field enumeration the MAS team audited on 2026-07-16 (source:
aitosoft-platform-Claude message via Tero; both /crawl callers —
src/lib/crawl4ai-client.ts and scripts/docs/sync-docs.ts). Validates every
request shape against the v0.9.x untrusted-config boundary WITH our
trusted-client relaxations applied (deploy/docker/aitosoft_trust.py), exactly
as the deployed server does.

Run after every upstream sync (part of the quality gate — see TESTING.md).
If upstream changes its UNTRUSTED_* allowlists, this fails BEFORE deploy
instead of silently breaking a WAA batch.

    pytest test-aitosoft/test_mas_contract.py -q
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
    ),
)

from aitosoft_trust import apply_trust_relaxations  # noqa: E402

apply_trust_relaxations()

from crawl4ai import BrowserConfig, CrawlerRunConfig  # noqa: E402
from crawl4ai.async_configs import (  # noqa: E402
    Provenance,
    UntrustedConfigError,
)


def load_crawler(cfg: dict) -> CrawlerRunConfig:
    return CrawlerRunConfig.load(cfg, provenance=Provenance.UNTRUSTED)


def load_browser(cfg: dict) -> BrowserConfig:
    return BrowserConfig.load(cfg, provenance=Provenance.UNTRUSTED)


# ── MAS payloads, verbatim from the 2026-07-16 field audit ──────────────

V13_CRAWLER_CONFIG = {
    "wait_until": "domcontentloaded",
    "magic": False,
    "remove_overlay_elements": False,
    "remove_consent_popups": True,
    "process_iframes": False,
    "page_timeout": 90000,
    "delay_before_return_html": 2.0,
    "locale": "fi-FI",
    "timezone_id": "Europe/Helsinki",
    "max_retries": 2,
}

PREFETCH_CRAWLER_CONFIG = {
    "prefetch": True,
    "page_timeout": 30000,
    "wait_until": "domcontentloaded",
    "locale": "fi-FI",
    "timezone_id": "Europe/Helsinki",
}

PERSONA_BROWSER_CONFIG = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "viewport_width": 1920,
    "viewport_height": 1080,
    "headers": {
        "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Google Chrome";v="138", "Chromium";v="138"',
        "sec-ch-ua-platform": '"Windows"',
    },
}

SYNC_DOCS_CRAWLER_CONFIG = {
    "wait_until": "domcontentloaded",
    "magic": False,
    "remove_overlay_elements": False,
    "page_timeout": 60000,
    "delay_before_return_html": 2.0,
}


# ── The contract ─────────────────────────────────────────────────────────


def test_v13_full_mode_config_loads_with_values_intact():
    cfg = load_crawler(V13_CRAWLER_CONFIG)
    assert cfg.remove_consent_popups is True
    assert cfg.wait_until == "domcontentloaded"
    assert cfg.locale == "fi-FI"
    assert cfg.timezone_id == "Europe/Helsinki"
    assert cfg.max_retries == 2
    assert cfg.delay_before_return_html == 2.0
    # Upstream clamps page_timeout to 60s; our relaxation raises the cap to
    # 180s so MAS's 90s must survive verbatim.
    assert cfg.page_timeout == 90000


def test_prefetch_links_only_config_loads():
    cfg = load_crawler(PREFETCH_CRAWLER_CONFIG)
    # prefetch is TRUTHY and must survive: it is in UPSTREAM's own
    # UNTRUSTED_FIELD_ALLOWLIST (async_configs.py "misc safe knobs").
    # If this assert ever fails after an upstream sync, upstream removed it —
    # add it to aitosoft_trust.py relaxations before deploying.
    assert cfg.prefetch is True
    assert cfg.page_timeout == 30000


def test_persona_browser_config_loads_with_headers():
    cfg = load_browser(PERSONA_BROWSER_CONFIG)
    # headers is upstream-forbidden; allowed by our relaxation.
    assert cfg.headers.get("Accept-Language", "").startswith("fi-FI")
    assert "sec-ch-ua" in cfg.headers
    assert cfg.viewport_width == 1920
    assert cfg.viewport_height == 1080
    assert "Chrome/138" in cfg.user_agent


def test_sync_docs_config_loads():
    cfg = load_crawler(SYNC_DOCS_CRAWLER_CONFIG)
    assert cfg.page_timeout == 60000


def test_falsy_forbidden_fields_are_dropped_not_rejected():
    # magic:false / proxy_config:null must not 400 (tolerant boundary).
    cfg = load_crawler({**V13_CRAWLER_CONFIG, "proxy_config": None})
    assert cfg.magic is False


def test_truthy_dangerous_fields_still_rejected():
    with pytest.raises(UntrustedConfigError):
        load_crawler({"js_code": "alert(1)"})
    with pytest.raises(UntrustedConfigError):
        load_browser({"cdp_url": "ws://evil:9222"})
    with pytest.raises(UntrustedConfigError):
        load_browser({"extra_args": ["--proxy-server=evil"]})


def test_unknown_fields_silently_dropped():
    cfg = load_crawler({**V13_CRAWLER_CONFIG, "some_future_field": 123})
    assert cfg.remove_consent_popups is True


def test_response_contract_fields_are_documented():
    """The fields MAS parses off every result. `redirected_status_code` is here
    because MAS asked for it explicitly on 2026-07-30: it is absent from their
    CrawlResult interface (crawl4ai-client.ts:33-56) — they found it in a
    forensics reply, not in a contract. `failure_class` is here because it is
    the machine-readable half of the Q2 answer.

    Kept as a literal enumeration on purpose: if a future change drops one of
    these, this test names it before a WAA batch does.
    """
    from aitosoft_failure_class import NONE, ORIGIN_CLASSES, http_status_for

    documented = {
        "url",
        "success",
        "status_code",  # the origin's FINAL status (last redirect hop)
        "redirected_status_code",  # same value when redirected; None otherwise
        "error_message",
        "failure_class",  # "none" on success, never absent
        "render_mode",  # "full" | "static"
        "markdown",
        "links",
    }
    from aitosoft_failure_class import failed_result

    assert documented <= set(failed_result("https://x.fi/", "render_error", "e"))

    # Transport rule: origin-caused never reaches MAS as a 5xx.
    assert all(http_status_for([c]) == 200 for c in ORIGIN_CLASSES)
    assert http_status_for([NONE]) == 200
    assert http_status_for(["render_error"]) == 500
    assert http_status_for(["render_timeout"]) == 504


def _crawl_client_and_app():
    """A TestClient over the real app, with real auth. Imported lazily so the
    pure-config tests above stay independent of server startup."""
    os.environ.setdefault("CRAWL4AI_API_TOKEN", "test-token-for-contract-suite")
    import server
    from fastapi.testclient import TestClient

    return TestClient(server.app), server


def _one_result_response(**fields):
    async def _fake(**kwargs):
        return {
            "success": True,
            "results": [{"url": "https://x.fi/", "render_mode": "full", **fields}],
        }

    return _fake


def test_all_failed_crawl_returns_envelope_for_origin_failures(monkeypatch):
    """The crux of tasks/origin-vs-crawler-failure-classification.md, exercised
    through the real app including the security exception handler.

    server.py's all-failed branch used to raise HTTPException(500)
    unconditionally, and the handler then replaced the body with
    {"error": "Internal server error"} — so under the single-URL contract every
    full-mode failure reached MAS with no status_code, no
    redirected_status_code, no error_message and no crawl_stats. This is the
    deploy gate for the redirect fix: that fix moves redirect-blocked hosts into
    the failed population, so without this they would go from a
    wrong-but-parseable 200 to an opaque, retried 500.
    """
    client, server = _crawl_client_and_app()
    monkeypatch.setattr(
        server,
        "handle_crawl_request",
        _one_result_response(
            success=False,
            status_code=403,
            redirected_status_code=403,
            error_message="Blocked by anti-bot protection: HTTP 403 with HTML content",
            failure_class="origin_blocked",
        ),
    )

    r = client.post(
        "/crawl",
        json={"urls": ["https://konecranes.com/"]},
        headers={"Authorization": f"Bearer {os.environ['CRAWL4AI_API_TOKEN']}"},
    )

    assert r.status_code == 200, "origin failure laundered into our 5xx again"
    result = r.json()["results"][0]
    assert result["success"] is False
    assert result["failure_class"] == "origin_blocked"
    # The whole point: none of this survived the old 500.
    assert result["status_code"] == 403
    assert result["redirected_status_code"] == 403
    assert result["error_message"]


def test_all_failed_crawl_still_5xx_when_the_fault_is_ours(monkeypatch):
    """5xx must keep meaning 'ours, retry may help'. The security handler still
    strips the detail; the envelope-level failure_class is what survives."""
    client, server = _crawl_client_and_app()
    monkeypatch.setattr(
        server,
        "handle_crawl_request",
        _one_result_response(
            success=False,
            status_code=None,
            error_message="browser process died",
            failure_class="render_error",
        ),
    )

    r = client.post(
        "/crawl",
        json={"urls": ["https://example.com/"]},
        headers={"Authorization": f"Bearer {os.environ['CRAWL4AI_API_TOKEN']}"},
    )

    assert r.status_code == 500
    assert r.json()["failure_class"] == "render_error"


def test_multi_url_request_rejected_with_400():
    """Single-URL contract (MAS ack 2026-07-17): a multi-URL /crawl request
    must get HTTP 400 naming the contract, BEFORE seed validation or render
    admission. Exercises api.handle_crawl_request directly, like
    test_admission.py does."""
    import asyncio

    from fastapi import HTTPException

    import api

    async def main():
        with pytest.raises(HTTPException) as exc_info:
            await api.handle_crawl_request(
                urls=["https://example.com", "https://example.org"],
                browser_config={},
                crawler_config={},
                config={
                    "crawler": {
                        "base_config": {},
                        "memory_threshold_percent": 85.0,
                        "rate_limiter": {"enabled": False, "base_delay": [1, 2]},
                    },
                    "limits": {"wall_clock_s": 180},
                },
            )
        assert exc_info.value.status_code == 400
        assert "single-URL" in exc_info.value.detail

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(main())
