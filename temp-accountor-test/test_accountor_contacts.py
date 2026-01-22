#!/usr/bin/env python3
"""
Temporary test script to verify Azure-deployed crawler can retrieve contact information
from Accountor pages.

Run: python temp-accountor-test/test_accountor_contacts.py
"""

import requests
import time
from typing import List, Dict

# Azure deployment credentials
CRAWL4AI_URL = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)
CRAWL4AI_TOKEN = "crawl4ai-d439be7297235edd4bde58b434c0ce82c99001912a47eafd"

# Test cases: URL and contacts we expect to find in the markdown
TEST_CASES = [
    {
        "url": "https://www.accountor.com/fi/finland/suuryritykselle",
        "expected_contacts": [
            "Jani Järvensivu",
            "Myyntijohtaja",
            "jani.jarvensivu@aspia.fi",
            "+358 40 713 3683",
        ],
    },
    {
        "url": "https://www.accountor.com/fi/finland/pk-ja-kasvuyritykselle",
        "expected_contacts": [
            "Kari Putkonen",
            "Myyntijohtaja, pk-yritykset",
            "kari.putkonen@aspia.fi",
            "+358447386009",
        ],
    },
    {
        "url": "https://www.accountor.com/fi/finland/uusi/laura-yla-sulkava-johtamaan-aspia-groupin-ja-accountorin-suomen-hr-toimintoja",
        "expected_contacts": [
            "Laura Ylä-Sulkava",
            "HR-johtaja",
            "Ola Gunnarsson",
            "Toimitusjohtaja",
            "Petteri Heikinheimo",
            "Suomen maajohtaja",
        ],
    },
    {
        "url": "https://www.accountor.com/fi/finland/ura/kirjanpitajasta-talouspaallikoksi-joonaksen-tyossa-yhdistyvat-rutiinit-ja-monipuoliset",
        "expected_contacts": ["Joonas Taskinen", "Talouspäällikkö"],
    },
]


def crawl_url(url: str) -> Dict:
    """Crawl a single URL using the Azure-deployed crawler."""
    print(f"\n📡 Crawling: {url}")

    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": [url]},
            timeout=60,
        )

        response.raise_for_status()
        result = response.json()

        if result.get("success") and result.get("results"):
            return {
                "success": True,
                "markdown": result["results"][0]
                .get("markdown", {})
                .get("raw_markdown", ""),
                "fit_markdown": result["results"][0]
                .get("markdown", {})
                .get("fit_markdown", ""),
            }
        else:
            return {"success": False, "error": result.get("error", "Unknown error")}

    except Exception as e:
        return {"success": False, "error": str(e)}


def check_contacts_in_markdown(markdown: str, expected_contacts: List[str]) -> Dict:
    """Check if expected contact information appears in the markdown."""
    found = []
    missing = []

    for contact in expected_contacts:
        if contact in markdown:
            found.append(contact)
        else:
            missing.append(contact)

    return {
        "found": found,
        "missing": missing,
        "found_count": len(found),
        "total_count": len(expected_contacts),
        "success_rate": len(found) / len(expected_contacts) if expected_contacts else 0,
    }


def main():
    """Run the test suite."""
    print("=" * 80)
    print("🧪 Testing Azure-Deployed Crawl4AI Service")
    print("=" * 80)
    print(f"Endpoint: {CRAWL4AI_URL}")
    print(f"Test Pages: {len(TEST_CASES)}")
    print("=" * 80)

    # First, test health endpoint
    print("\n🏥 Testing health endpoint...")
    try:
        health_response = requests.get(f"{CRAWL4AI_URL}/health", timeout=10)
        if health_response.status_code == 200:
            print("✅ Health check passed!")
        else:
            print(f"⚠️  Health check returned status {health_response.status_code}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return

    # Run tests for each URL
    total_tests = len(TEST_CASES)
    passed_tests = 0
    results = []

    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n{'=' * 80}")
        print(f"Test {i}/{total_tests}")
        print(f"{'=' * 80}")

        url = test_case["url"]
        expected = test_case["expected_contacts"]

        # Crawl the URL
        crawl_result = crawl_url(url)

        if not crawl_result["success"]:
            print(f"❌ Crawl failed: {crawl_result['error']}")
            results.append(
                {"url": url, "crawl_success": False, "error": crawl_result["error"]}
            )
            continue

        # Check for contacts in markdown
        markdown = crawl_result["markdown"]
        contact_check = check_contacts_in_markdown(markdown, expected)

        print("\n📊 Results:")
        found_cnt = contact_check["found_count"]
        total_cnt = contact_check["total_count"]
        print(f"   Contacts found: {found_cnt}/{total_cnt}")
        print(f"   Success rate: {contact_check['success_rate']:.0%}")

        if contact_check["found"]:
            print("\n   ✅ Found:")
            for contact in contact_check["found"]:
                print(f"      - {contact}")

        if contact_check["missing"]:
            print("\n   ❌ Missing:")
            for contact in contact_check["missing"]:
                print(f"      - {contact}")

        # Save markdown preview (first 500 chars)
        print("\n📄 Markdown preview (first 500 chars):")
        print("-" * 80)
        print(markdown[:500] + "..." if len(markdown) > 500 else markdown)
        print("-" * 80)

        # Test passes if we found at least 50% of contacts
        test_passed = contact_check["success_rate"] >= 0.5
        if test_passed:
            passed_tests += 1
            print("\n✅ TEST PASSED")
        else:
            print("\n❌ TEST FAILED (less than 50% contacts found)")

        results.append(
            {
                "url": url,
                "crawl_success": True,
                "contacts_found": contact_check["found_count"],
                "contacts_total": contact_check["total_count"],
                "success_rate": contact_check["success_rate"],
                "test_passed": test_passed,
                "markdown_length": len(markdown),
            }
        )

        # Small delay between requests
        if i < total_tests:
            time.sleep(2)

    # Summary
    print("\n" + "=" * 80)
    print("📈 FINAL SUMMARY")
    print("=" * 80)
    print(f"Tests run: {total_tests}")
    print(f"Tests passed: {passed_tests}")
    print(f"Tests failed: {total_tests - passed_tests}")
    print(f"Success rate: {passed_tests / total_tests:.0%}")
    print("=" * 80)

    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result.get("test_passed") else "❌ FAIL"
        if result.get("crawl_success"):
            found = result["contacts_found"]
            total = result["contacts_total"]
            url = result["url"]
            print(f"{i}. {status} - {found}/{total} contacts - {url}")
        else:
            print(f"{i}. ❌ FAIL - Crawl error - {result['url']}")

    print("=" * 80)

    if passed_tests == total_tests:
        print("\n🎉 All tests passed! The Azure crawler is working correctly.")
    elif passed_tests > 0:
        print(f"\n⚠️  Partial success: {passed_tests}/{total_tests} tests passed.")
    else:
        print("\n❌ All tests failed. Please check the crawler configuration.")


if __name__ == "__main__":
    main()
