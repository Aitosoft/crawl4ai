#!/usr/bin/env python3
"""
Test a single site with configurable crawler options.

Usage:
    python test-aitosoft/test_site.py caverna.fi
    python test-aitosoft/test_site.py solwers.com --page contacts
    python test-aitosoft/test_site.py accountor.com --page fi/finland
    python test-aitosoft/test_site.py jpond.fi --version v12 --render-mode static

Run from the REPO ROOT — artifact/report paths are relative
(test-aitosoft/artifacts/...); running from inside test-aitosoft/ creates a
nested test-aitosoft/test-aitosoft/ clutter directory.

Site safety (CLAUDE.md): never hit the same site more than 1-2 times per
session; rotate across sites.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
import requests

# Azure deployment credentials (override via env for local/staging runs).
CRAWL4AI_URL = os.getenv(
    "CRAWL4AI_API_URL",
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io",
)
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

if not CRAWL4AI_TOKEN:
    print("❌ Error: CRAWL4AI_API_TOKEN not set in environment")
    print("   Set it in your shell or .env file")
    sys.exit(1)

# Crawler configurations
CONFIGS = {
    # RECOMMENDED: Matches MAS production config. Works on 100% of Tier 1 sites
    # including cookie walls (remove_consent_popups handles OneTrust/Cookiebot/Didomi).
    "optimal": {
        "wait_until": "domcontentloaded",
        # NOTE: no "magic" key. Since v0.9.x the server's untrusted-config
        # boundary rejects the field on PRESENCE (even "magic": false) with
        # HTTP 400. It was harmful on cookie sites anyway.
        "scan_full_page": False,
        "remove_overlay_elements": False,  # Don't use - removes page!
        "remove_consent_popups": True,  # Aitosoft: CMP-aware cookie removal (v0.8.5+)
        "page_timeout": 60000,
        "delay_before_return_html": 2.0,
    },
    # Slow-and-thorough fallback for lazy-loading / JS-heavy pages. Contains
    # no forbidden fields, so it is valid against the v0.9.x untrusted-config
    # boundary. (The old fast/heavy/magic_only/cookie_* configs all carried
    # "magic" or "js_code" and were rejected with HTTP 400 — removed 2026-07-17,
    # see git history if you need them for reference.)
    "patient": {
        "wait_until": "networkidle",
        "scan_full_page": True,
        "remove_consent_popups": True,
        "page_timeout": 90000,
        "delay_before_return_html": 3.0,
    },
}


def test_site(
    domain: str,
    page: Optional[str] = None,
    config_type: str = "optimal",
    version: str = "manual",
    save_artifacts: bool = True,
    render_mode: str = "full",
):
    """
    Test a single site with specified configuration.

    Args:
        domain: Domain to test (e.g., 'talgraf.fi')
        page: Optional page path (e.g., 'yhteystiedot')
        config_type: 'optimal' (default, matches MAS production) or 'patient'
        version: Test version label (e.g., 'v11')
        save_artifacts: Whether to save JSON and markdown artifacts
        render_mode: 'full' (Playwright, default) or 'static' (httpx + html2text).
            When 'static', the browser pool is bypassed entirely — useful for
            SPA hosts where Playwright hangs (roadscanners.com pattern).

    Returns:
        dict: Crawl result data
    """
    # Build URL
    url = f"https://{domain}"
    if page:
        # Handle both /page and page formats
        page = page.lstrip("/")
        url = f"{url}/{page}"

    print(f"\n{'=' * 80}")
    print(f"Testing: {url}")
    print(f"Config: {config_type}")
    print(f"Render mode: {render_mode}")
    print(f"{'=' * 80}\n")

    # Get config
    if config_type not in CONFIGS:
        print(f"❌ Unknown config type: {config_type}")
        print(f"   Available: {', '.join(CONFIGS.keys())}")
        return None

    crawler_config = CONFIGS[config_type]

    payload = {"urls": [url], "crawler_config": crawler_config}
    if render_mode != "full":
        payload["render_mode"] = render_mode

    # Crawl
    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
    except requests.Timeout:
        print("❌ Request timeout after 120s")
        return None
    except requests.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None

    # Analyze result
    if not result.get("success"):
        print(f"❌ Crawl failed: {result.get('error', 'Unknown error')}")
        return None

    data = result["results"][0]

    # Extract key metrics
    raw_markdown = data.get("markdown", {}).get("raw_markdown", "")
    fit_markdown = data.get("markdown", {}).get("fit_markdown", "")
    status_code = data.get("status_code", 0)
    redirected = data.get("redirected_url")
    links = data.get("links", {})

    # Estimate tokens (rough: 1 token ≈ 4 chars)
    raw_tokens = len(raw_markdown) // 4
    fit_tokens = len(fit_markdown) // 4

    # Print summary
    print("✅ Success")
    print(f"   Status: {status_code}")
    if redirected and redirected != url:
        print(f"   Redirected: {redirected}")
    print(f"   Raw markdown: {len(raw_markdown)} chars (~{raw_tokens} tokens)")
    print(f"   Fit markdown: {len(fit_markdown)} chars (~{fit_tokens} tokens)")
    print(f"   Internal links: {len(links.get('internal', []))}")
    print(f"   External links: {len(links.get('external', []))}")

    # Check for potential issues
    if raw_tokens < 100:
        print(f"\n⚠️  WARNING: Very short content ({raw_tokens} tokens)")
        print("   Possible causes: cookie wall, login required, bot detection")
        print("   Suggestion: Try --config patient (networkidle + full scroll)")

    if "cookiebot" in raw_markdown.lower() or "cookie consent" in raw_markdown.lower():
        print("\n⚠️  Cookie consent detected in content")
        if not crawler_config.get("remove_consent_popups"):
            print("   Suggestion: Use a config with remove_consent_popups: true")

    # Save artifacts if requested
    if save_artifacts:
        artifacts_dir = Path(f"test-aitosoft/artifacts/{version}")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        filename_base = domain.replace(".", "-").replace("/", "-")
        if page:
            filename_base += f"-{page.replace('/', '-').replace('?', '-')}"

        # Save full JSON
        json_path = artifacts_dir / f"{filename_base}-{config_type}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved JSON: {json_path}")

        # Save raw markdown
        md_path = artifacts_dir / f"{filename_base}-{config_type}-raw.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(raw_markdown)
        print(f"💾 Saved markdown: {md_path}")

        # Save metadata
        meta_path = artifacts_dir / f"{filename_base}-{config_type}-meta.json"
        metadata = {
            "url": url,
            "domain": domain,
            "page": page,
            "config_type": config_type,
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "status_code": status_code,
                "redirected_url": redirected,
                "raw_chars": len(raw_markdown),
                "raw_tokens": raw_tokens,
                "fit_chars": len(fit_markdown),
                "fit_tokens": fit_tokens,
                "internal_links": len(links.get("internal", [])),
                "external_links": len(links.get("external", [])),
            },
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}\n")
    return data


def main():
    parser = argparse.ArgumentParser(
        description="Test crawl4ai on a single site",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples (run from repo root; rotate sites — max 1-2 hits/site/session):
  python test-aitosoft/test_site.py caverna.fi
  python test-aitosoft/test_site.py solwers.com --page contacts
  python test-aitosoft/test_site.py jpond.fi --version v12 --no-save
  python test-aitosoft/test_site.py caverna.fi --render-mode static

Configs:
  optimal  - domcontentloaded + remove_consent_popups (default, 2-4s,
             matches MAS production)
  patient  - networkidle + scan_full_page (lazy-loading pages, 30-60s)
        """,
    )

    parser.add_argument("domain", help="Domain to test (e.g., talgraf.fi)")
    parser.add_argument("--page", help="Optional page path (e.g., yhteystiedot)")
    parser.add_argument(
        "--config",
        choices=["optimal", "patient"],
        default="optimal",
        help="Crawler configuration to use (default: optimal)",
    )
    parser.add_argument(
        "--version",
        default="manual",
        help="Test version label for artifacts (default: manual)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save artifacts (JSON/markdown files)",
    )
    parser.add_argument(
        "--render-mode",
        choices=["full", "static"],
        default="full",
        help=(
            "Rendering strategy. 'full' (default) uses Playwright; 'static' "
            "uses httpx + html2text with no browser — cheap fallback for "
            "hosts where Playwright hangs."
        ),
    )

    args = parser.parse_args()

    result = test_site(
        domain=args.domain,
        page=args.page,
        config_type=args.config,
        version=args.version,
        save_artifacts=not args.no_save,
        render_mode=args.render_mode,
    )

    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
