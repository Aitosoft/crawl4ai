#!/usr/bin/env python3
"""
Run regression tests across test site tiers.

Usage:
    python test-aitosoft/test_regression.py --version v11
    python test-aitosoft/test_regression.py --tier 1 --version v11
    python test-aitosoft/test_regression.py --all --version v12
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List
from test_site import test_site, CRAWL4AI_TOKEN

if not CRAWL4AI_TOKEN:
    print("❌ Error: CRAWL4AI_API_TOKEN not set in environment")
    sys.exit(1)

# Test site registry (see TEST_SITES_REGISTRY.md)
TIER_1_SITES: List[Dict[str, Any]] = [
    {
        "domain": "talgraf.fi",
        "page": "yhteystiedot",
        "expected_decision_makers": [
            "Toni Kemppinen",
            "Sanna Kemppinen",
            "Renne Pöysä",
        ],
        "expected_min_contacts": 15,
    },
    {
        "domain": "tilitoimistovahtivuori.fi",
        "page": "?page_id=77",
        "expected_decision_makers": ["Jaana Toppinen", "Kirsi Haltia"],
        "expected_min_contacts": 10,
    },
    {
        "domain": "accountor.com/fi/finland",
        "page": "suuryritykselle",
        "expected_decision_makers": ["Jani Järvensivu"],
        "expected_min_contacts": 1,
        "requires_heavy": True,  # Cookie wall
    },
    {
        "domain": "monidor.fi",
        "page": "fi/fi-yritys/yritys/",
        "expected_decision_makers": ["Mikko Savola"],
        "expected_min_contacts": 1,
    },
]

TIER_2_SITES: List[Dict[str, Any]] = [
    {
        "domain": "jpond.fi",
        "page": "yhteystiedot/",
        "expected_decision_makers": ["Janne Lampi"],
        "expected_min_contacts": 10,
    },
    {
        "domain": "neuroliitto.fi",
        "page": "yhteystiedot/hallinto-ja-tukipalvelut/",
        "expected_decision_makers": ["Helena Ylikylä-Leiva"],
        "expected_min_contacts": 5,
    },
    {
        "domain": "solwers.com",
        "page": "sijoittajat/hallinnointi/#johtoryhma",
        "expected_decision_makers": ["Johan Ehrnrooth"],
        "expected_min_contacts": 5,
    },
    {
        "domain": "caverna.fi",
        "page": None,  # Homepage
        "expected_decision_makers": [],  # Restaurant, no decision makers
        "expected_min_contacts": 1,
    },
    {
        "domain": "showell.com",
        "page": None,
        "expected_decision_makers": [],  # SaaS homepage
        "expected_min_contacts": 0,
    },
]


def check_contacts(markdown: str, expected_names: list) -> dict:
    """
    Check if expected contact names appear in markdown.

    Args:
        markdown: Raw markdown content
        expected_names: List of names to find

    Returns:
        dict with 'found', 'missing', 'found_count'
    """
    found = []
    missing = []

    for name in expected_names:
        if name.lower() in markdown.lower():
            found.append(name)
        else:
            missing.append(name)

    return {
        "found": found,
        "missing": missing,
        "found_count": len(found),
        "total_expected": len(expected_names),
    }


def test_site_with_fallback(site_config: dict, version: str) -> dict:
    """
    Test a site, with fallback to heavy config if needed.

    Args:
        site_config: Site configuration dict
        version: Test version label

    Returns:
        dict with test results
    """
    domain = site_config["domain"]
    page = site_config.get("page")
    requires_heavy = site_config.get("requires_heavy", False)

    print(f"\n{'=' * 80}")
    print(f"Testing: {domain}/{page or 'homepage'}")
    print(f"{'=' * 80}")

    # Try fast config first (unless we know it needs heavy)
    config = "heavy" if requires_heavy else "fast"

    result = test_site(
        domain=domain,
        page=page,
        config_type=config,
        version=version,
        save_artifacts=True,
    )

    if result is None:
        return {
            "site": domain,
            "page": page,
            "success": False,
            "error": "Crawl failed",
            "config_used": config,
        }

    raw_markdown = result.get("markdown", {}).get("raw_markdown", "")
    raw_tokens = len(raw_markdown) // 4

    # If blocked and we haven't tried heavy yet, retry
    if raw_tokens < 100 and config != "heavy":
        print(f"\n⚠️  Blocked ({raw_tokens} tokens), retrying with heavy config...")
        result = test_site(
            domain=domain,
            page=page,
            config_type="heavy",
            version=version,
            save_artifacts=True,
        )
        if result:
            raw_markdown = result.get("markdown", {}).get("raw_markdown", "")
            raw_tokens = len(raw_markdown) // 4
            config = "heavy"

    # Check for expected contacts
    expected_names = site_config.get("expected_decision_makers", [])
    contact_check = check_contacts(raw_markdown, expected_names)

    # Determine pass/fail
    passed = (
        result is not None
        and raw_tokens >= 100
        and contact_check["found_count"]
        >= len(expected_names) * 0.5  # At least 50% found
    )

    return {
        "site": domain,
        "page": page or "homepage",
        "success": result is not None,
        "passed": passed,
        "config_used": config,
        "metrics": {
            "status_code": result.get("status_code", 0) if result else 0,
            "raw_tokens": raw_tokens,
            "contacts_expected": len(expected_names),
            "contacts_found": contact_check["found_count"],
            "contacts_missing": contact_check["missing"],
        },
    }


def run_regression(tier: int, version: str):
    """
    Run regression tests for specified tier.

    Args:
        tier: 1 for Tier 1, 2 for Tier 2, 0 for all
        version: Test version label
    """
    print(f"\n{'=' * 80}")
    print(f"Regression Test Suite - Version {version}")
    print(f"Tier: {tier if tier > 0 else 'All'}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'=' * 80}\n")

    # Select sites
    sites: List[Dict[str, Any]] = []
    if tier == 1 or tier == 0:
        sites.extend(TIER_1_SITES)
    if tier == 2 or tier == 0:
        sites.extend(TIER_2_SITES)

    print(f"Testing {len(sites)} sites...\n")

    # Run tests
    results = []
    for site_config in sites:
        result = test_site_with_fallback(site_config, version)
        results.append(result)

    # Generate report
    report_dir = Path("test-aitosoft/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = (
        report_dir / f"{version}-regression-tier{tier if tier > 0 else 'all'}.md"
    )

    with open(report_path, "w", encoding="utf-8") as f:
        # Header
        f.write(f"# {version} Regression Test Results\n\n")
        f.write(f"**Tier:** {tier if tier > 0 else 'All'}\n")
        f.write(f"**Date:** {datetime.now().isoformat()}\n")
        f.write(f"**Sites Tested:** {len(sites)}\n\n")

        # Summary
        passed = sum(1 for r in results if r.get("passed"))
        failed = len(results) - passed
        success_rate = (passed / len(results) * 100) if results else 0

        f.write("## Summary\n\n")
        f.write(f"- **Passed:** {passed}/{len(results)} ({success_rate:.0f}%)\n")
        f.write(f"- **Failed:** {failed}/{len(results)}\n\n")

        # Results table
        f.write("## Results\n\n")
        f.write("| Site | Page | Status | Tokens | Contacts | Config |\n")
        f.write("|------|------|--------|--------|----------|--------|\n")

        for r in results:
            status = "✅ PASS" if r.get("passed") else "❌ FAIL"
            tokens = r.get("metrics", {}).get("raw_tokens", 0)
            metrics = r.get("metrics", {})
            found = metrics.get("contacts_found", 0)
            expected = metrics.get("contacts_expected", 0)
            contacts = f"{found}/{expected}"
            config = r.get("config_used", "unknown")

            site = r["site"]
            page = r["page"]
            line = f"| {site} | {page} | {status} | {tokens} |"
            line += f" {contacts} | {config} |\n"
            f.write(line)

        # Detailed results
        f.write("\n## Detailed Results\n\n")
        for r in results:
            f.write(f"### {r['site']}/{r['page']}\n\n")
            f.write(f"- **Status:** {'✅ PASS' if r.get('passed') else '❌ FAIL'}\n")
            f.write(f"- **Config:** {r.get('config_used')}\n")

            metrics = r.get("metrics", {})
            f.write(f"- **Tokens:** {metrics.get('raw_tokens', 0)}\n")
            found = metrics.get("contacts_found", 0)
            expected = metrics.get("contacts_expected", 0)
            f.write(f"- **Contacts found:** {found}/{expected}\n")

            if metrics.get("contacts_missing"):
                missing = ", ".join(metrics["contacts_missing"])
                f.write(f"- **Missing contacts:** {missing}\n")

            f.write("\n")

        # Quality gates
        f.write("## Quality Gates\n\n")
        gate_all_tier1 = all(
            r.get("passed")
            for r in results
            if r["site"] in [s["domain"] for s in TIER_1_SITES]
        )
        gate_success_rate = success_rate >= 95
        gate_no_timeouts = all(r.get("success") for r in results)

        tier1_check = "✅" if gate_all_tier1 else "❌"
        f.write(f"- {tier1_check} All Tier 1 sites pass\n")
        rate_check = "✅" if gate_success_rate else "❌"
        f.write(f"- {rate_check} Success rate ≥95% ({success_rate:.0f}%)\n")
        timeout_check = "✅" if gate_no_timeouts else "❌"
        f.write(f"- {timeout_check} No timeouts\n\n")

        if gate_all_tier1 and gate_success_rate and gate_no_timeouts:
            f.write("**✅ All quality gates passed - safe to deploy**\n")
        else:
            f.write("**❌ Quality gates failed - do not deploy**\n")

    print(f"\n{'=' * 80}")
    print(f"📊 Report generated: {report_path}")
    print(f"{'=' * 80}\n")

    # Print summary to console
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"Passed: {passed}/{len(results)} ({success_rate:.0f}%)")
    print(f"Failed: {failed}/{len(results)}")
    print(f"{'=' * 80}\n")

    # Exit with error code if tests failed
    if failed > 0:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Run regression tests on crawl4ai test sites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test-aitosoft/test_regression.py --version v11
  python test-aitosoft/test_regression.py --tier 1 --version v11
  python test-aitosoft/test_regression.py --all --version v12

Tiers:
  1 - Core test sites (4 sites, always test before deploy)
  2 - Extended test sites (5 sites, test for major changes)
  all - All tiers (9 sites, comprehensive validation)
        """,
    )

    parser.add_argument(
        "--tier", type=int, choices=[1, 2], help="Test tier to run (default: 1)"
    )
    parser.add_argument("--all", action="store_true", help="Test all tiers")
    parser.add_argument(
        "--version", required=True, help="Test version label (e.g., v11)"
    )

    args = parser.parse_args()

    # Determine tier
    if args.all:
        tier = 0  # All tiers
    elif args.tier:
        tier = args.tier
    else:
        tier = 1  # Default to Tier 1

    run_regression(tier, args.version)


if __name__ == "__main__":
    main()
