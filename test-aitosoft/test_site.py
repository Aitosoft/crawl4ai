#!/usr/bin/env python3
"""
Test a single site with configurable crawler options.

Usage:
    python test-aitosoft/test_site.py talgraf.fi
    python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot
    python test-aitosoft/test_site.py accountor.com --config heavy
    python test-aitosoft/test_site.py monidor.fi --version v11
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
import requests

# Azure deployment credentials
CRAWL4AI_URL = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

if not CRAWL4AI_TOKEN:
    print("❌ Error: CRAWL4AI_API_TOKEN not set in environment")
    print("   Set it in your shell or .env file")
    sys.exit(1)

# Crawler configurations
CONFIGS = {
    # RECOMMENDED: Works on 100% of test sites including cookie consent sites
    "optimal": {
        "wait_until": "domcontentloaded",
        "magic": False,  # Don't use - removes content on cookie sites!
        "scan_full_page": False,
        "remove_overlay_elements": False,  # Don't use - removes page!
        "page_timeout": 60000,
        "delay_before_return_html": 2.0,
    },
    # LEGACY configs - use "optimal" instead
    "fast": {
        "wait_until": "domcontentloaded",
        "magic": True,
        "scan_full_page": True,
        "remove_overlay_elements": True,
        "page_timeout": 30000,
    },
    "heavy": {
        "wait_until": "networkidle",
        "magic": True,
        "scan_full_page": True,
        "remove_overlay_elements": True,
        "page_timeout": 60000,
    },
    "minimal": {
        "wait_until": "domcontentloaded",
        "remove_overlay_elements": True,
        "page_timeout": 30000,
    },
    "magic_only": {
        "wait_until": "domcontentloaded",
        "magic": True,
        "remove_overlay_elements": True,
        "page_timeout": 30000,
    },
    "scan_only": {
        "wait_until": "domcontentloaded",
        "scan_full_page": True,
        "remove_overlay_elements": True,
        "page_timeout": 30000,
    },
    # NEW: Cookie consent handling configs
    "cookie_click": {
        "wait_until": "domcontentloaded",
        "magic": True,
        "scan_full_page": True,
        "remove_overlay_elements": True,
        "page_timeout": 60000,
        "delay_before_return_html": 3.0,  # Wait for consent dialog to clear
        "js_code": """
        (async () => {
            const selectors = [
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                '#onetrust-accept-btn-handler',
                'button[data-cky-tag="accept-button"]',
                '.fc-button.fc-cta-consent',
            ];
            for (const selector of selectors) {
                const btn = document.querySelector(selector);
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    await new Promise(r => setTimeout(r, 1500));
                    return;
                }
            }
        })();
        """,
    },
    "cookie_click_finnish": {
        "wait_until": "networkidle",
        "magic": True,
        "scan_full_page": True,
        "remove_overlay_elements": True,
        "page_timeout": 60000,
        "delay_before_return_html": 3.0,
        "js_code": """
        (async () => {
            const selectors = [
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                '#onetrust-accept-btn-handler',
                'button[data-cky-tag="accept-button"]',
                '.fc-button.fc-cta-consent',
            ];
            // First try standard selectors
            for (const selector of selectors) {
                const btn = document.querySelector(selector);
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    await new Promise(r => setTimeout(r, 1500));
                    return;
                }
            }
            // Then try Finnish text buttons
            const sel = 'button, a.button, [role="button"]';
            const buttons = document.querySelectorAll(sel);
            for (const btn of buttons) {
                const text = btn.textContent.toLowerCase();
                if (text.includes('hyväksy') || text.includes('salli') ||
                    text.includes('accept') || text.includes('allow all')) {
                    btn.click();
                    await new Promise(r => setTimeout(r, 1500));
                    return;
                }
            }
        })();
        """,
    },
    # Wait for Cookiebot dialog, then click accept
    "cookie_wait_click": {
        "wait_until": "domcontentloaded",
        "magic": True,
        "scan_full_page": True,
        "remove_overlay_elements": True,
        "page_timeout": 60000,
        "wait_for": "#CybotCookiebotDialog",  # Wait for dialog to appear
        "wait_for_timeout": 10000,  # 10 seconds max wait
        "delay_before_return_html": 2.0,
        "js_code": """
        (async () => {
            // Wait a moment for button to be clickable
            await new Promise(r => setTimeout(r, 500));

            const selectors = [
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                '#CybotCookiebotDialogBodyButtonAccept',
                '#CybotCookiebotDialogBodyLevelButtonAccept',
                '#onetrust-accept-btn-handler',
            ];
            for (const selector of selectors) {
                const btn = document.querySelector(selector);
                if (btn) {
                    console.log('Clicking:', selector);
                    btn.click();
                    await new Promise(r => setTimeout(r, 2000));
                    return;
                }
            }
            console.log('No consent button found');
        })();
        """,
    },
    # Smart cookie consent - JS polls for button with retries
    "cookie_smart": {
        "wait_until": "networkidle",  # Wait for all JS to finish
        "magic": True,
        "scan_full_page": True,
        "remove_overlay_elements": True,
        "page_timeout": 60000,
        "delay_before_return_html": 5.0,  # Extra time after cookie click
        "js_code": """
        (async () => {
            // Poll for consent button with retries
            const selectors = [
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                '#CybotCookiebotDialogBodyButtonAccept',
                '#CybotCookiebotDialogBodyLevelButtonAccept',
                '#onetrust-accept-btn-handler',
                'button[data-cky-tag="accept-button"]',
                '.fc-button.fc-cta-consent',
            ];

            // Try up to 10 times with 500ms delay
            for (let attempt = 0; attempt < 10; attempt++) {
                for (const selector of selectors) {
                    const btn = document.querySelector(selector);
                    if (btn && btn.offsetParent !== null) {
                        console.log('Found button:', selector, 'on attempt', attempt);
                        btn.click();
                        // Wait for dialog to close and content to render
                        await new Promise(r => setTimeout(r, 2000));
                        return { clicked: true, selector, attempt };
                    }
                }
                // Wait before next attempt
                await new Promise(r => setTimeout(r, 500));
            }
            console.log('No consent button found after 10 attempts');
            return { clicked: false };
        })();
        """,
    },
}


def test_site(
    domain: str,
    page: Optional[str] = None,
    config_type: str = "fast",
    version: str = "manual",
    save_artifacts: bool = True,
):
    """
    Test a single site with specified configuration.

    Args:
        domain: Domain to test (e.g., 'talgraf.fi')
        page: Optional page path (e.g., 'yhteystiedot')
        config_type: One of 'fast', 'heavy', 'minimal', 'magic_only', 'scan_only'
        version: Test version label (e.g., 'v11')
        save_artifacts: Whether to save JSON and markdown artifacts

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
    print(f"{'=' * 80}\n")

    # Get config
    if config_type not in CONFIGS:
        print(f"❌ Unknown config type: {config_type}")
        print(f"   Available: {', '.join(CONFIGS.keys())}")
        return None

    crawler_config = CONFIGS[config_type]

    # Crawl
    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": [url], "crawler_config": crawler_config},
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
        print("   Suggestion: Try --config heavy")

    if "cookiebot" in raw_markdown.lower() or "cookie consent" in raw_markdown.lower():
        print("\n⚠️  Cookie consent detected in content")
        if not crawler_config.get("magic"):
            print("   Suggestion: Try --config fast (includes magic: true)")

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
Examples:
  python test-aitosoft/test_site.py talgraf.fi
  python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot
  python test-aitosoft/test_site.py accountor.com --config heavy
  python test-aitosoft/test_site.py monidor.fi --version v11 --no-save

Configs:
  fast      - domcontentloaded, magic, scan_full_page (default, 2-4s)
  heavy     - networkidle, magic, scan_full_page (for cookie walls, 30-60s)
  minimal   - domcontentloaded only (baseline, no special handling)
  magic_only   - Test magic parameter alone
  scan_only    - Test scan_full_page parameter alone
        """,
    )

    parser.add_argument("domain", help="Domain to test (e.g., talgraf.fi)")
    parser.add_argument("--page", help="Optional page path (e.g., yhteystiedot)")
    parser.add_argument(
        "--config",
        choices=[
            "optimal",
            "fast",
            "heavy",
            "minimal",
            "magic_only",
            "scan_only",
            "cookie_click",
            "cookie_click_finnish",
            "cookie_wait_click",
            "cookie_smart",
        ],
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

    args = parser.parse_args()

    result = test_site(
        domain=args.domain,
        page=args.page,
        config_type=args.config,
        version=args.version,
        save_artifacts=not args.no_save,
    )

    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
