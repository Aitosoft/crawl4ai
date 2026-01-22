#!/usr/bin/env python3
"""
Isolation test to understand the talgraf.fi yhteystiedot bug.

Questions to answer:
1. Does /yhteystiedot/ fail consistently when requested alone?
2. Does /yritys/ always succeed?
3. Is there a difference between first request vs subsequent requests?
4. Does adding delay between requests help?
"""

import os
import sys
import time
import requests

CRAWL4AI_URL = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

if not CRAWL4AI_TOKEN:
    print("❌ Error: CRAWL4AI_API_TOKEN not set")
    sys.exit(1)

CRAWL4AI_V10_CONFIG = {
    "wait_until": "domcontentloaded",
    "remove_overlay_elements": True,
    "page_timeout": 60000,
    "magic": True,
    "scan_full_page": True,
}


def crawl_url(url: str, label: str) -> dict:
    """Crawl a single URL and return result."""
    start_time = time.time()

    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": [url], "crawler_config": CRAWL4AI_V10_CONFIG},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()

        elapsed = time.time() - start_time

        if result.get("success"):
            data = result["results"][0]
            raw_len = len(data.get("markdown", {}).get("raw_markdown", ""))
            return {
                "label": label,
                "url": url,
                "success": True,
                "chars": raw_len,
                "elapsed": elapsed,
            }
        else:
            return {
                "label": label,
                "url": url,
                "success": False,
                "error": result.get("error"),
                "elapsed": elapsed,
            }

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "label": label,
            "url": url,
            "success": False,
            "error": str(e),
            "elapsed": elapsed,
        }


def print_result(iteration: int, result: dict):
    """Print a test result."""
    if result["success"]:
        status = "✅" if result["chars"] > 100 else "❌"
        print(
            f"  [{iteration:2d}] {status} {result['chars']:6,} chars in {result['elapsed']:.1f}s"
        )
    else:
        print(f"  [{iteration:2d}] ❌ Error: {result.get('error', 'Unknown')}")


print("\n" + "=" * 80)
print("ISOLATION TESTS: Understanding the talgraf.fi bug")
print("=" * 80)

# Test 1: yhteystiedot alone, 10 times
print("\n📋 TEST 1: /yhteystiedot/ alone (10 iterations)")
print("-" * 80)
print("Testing if the page fails consistently when requested alone...\n")

yhteystiedot_results = []
for i in range(10):
    result = crawl_url("https://www.talgraf.fi/yhteystiedot/", "yhteystiedot")
    yhteystiedot_results.append(result)
    print_result(i + 1, result)
    time.sleep(1)  # 1 second between requests

failures = [r for r in yhteystiedot_results if r["success"] and r["chars"] < 100]
successes = [r for r in yhteystiedot_results if r["success"] and r["chars"] > 100]

print("\n📊 Summary:")
print(f"   Successes: {len(successes)}/10 ({len(successes)*10}%)")
print(f"   Failures:  {len(failures)}/10 ({len(failures)*10}%)")
if successes:
    avg_chars = sum(r["chars"] for r in successes) / len(successes)
    print(f"   Success avg: {avg_chars:,.0f} chars")
if failures:
    avg_chars = sum(r["chars"] for r in failures) / len(failures)
    print(f"   Failure avg: {avg_chars:,.0f} chars")

# Test 2: yritys alone, 10 times
print("\n📋 TEST 2: /yritys/ alone (10 iterations)")
print("-" * 80)
print("Testing if /yritys/ is consistently successful...\n")

yritys_results = []
for i in range(10):
    result = crawl_url("https://www.talgraf.fi/yritys/", "yritys")
    yritys_results.append(result)
    print_result(i + 1, result)
    time.sleep(1)

failures = [r for r in yritys_results if r["success"] and r["chars"] < 100]
successes = [r for r in yritys_results if r["success"] and r["chars"] > 100]

print("\n📊 Summary:")
print(f"   Successes: {len(successes)}/10 ({len(successes)*10}%)")
print(f"   Failures:  {len(failures)}/10 ({len(failures)*10}%)")
if successes:
    avg_chars = sum(r["chars"] for r in successes) / len(successes)
    print(f"   Success avg: {avg_chars:,.0f} chars")

# Test 3: Alternating requests with delays
print("\n📋 TEST 3: Alternating /yhteystiedot/ and /yritys/ with 5s delay")
print("-" * 80)
print("Testing if order or timing affects success...\n")

urls = [
    ("https://www.talgraf.fi/yhteystiedot/", "yhteystiedot"),
    ("https://www.talgraf.fi/yritys/", "yritys"),
]

alternating_results = []
for i in range(6):  # 3 pairs
    url, label = urls[i % 2]
    print(f"Request {i+1}: {label}")
    result = crawl_url(url, label)
    alternating_results.append(result)
    print_result(i + 1, result)

    if i < 5:  # Don't sleep after last request
        print("   (waiting 5 seconds...)")
        time.sleep(5)

yhteystiedot_alt = [
    r for r in alternating_results if "yhteystiedot" in r["label"] and r["success"]
]
yritys_alt = [r for r in alternating_results if "yritys" in r["label"] and r["success"]]

print("\n📊 Summary:")
print(
    f"   yhteystiedot: {len([r for r in yhteystiedot_alt if r['chars'] > 100])}/{len(yhteystiedot_alt)} succeeded"
)
print(
    f"   yritys: {len([r for r in yritys_alt if r['chars'] > 100])}/{len(yritys_alt)} succeeded"
)

# Test 4: Fresh request after 30 second break
print("\n📋 TEST 4: Fresh request after 30-second break")
print("-" * 80)
print("Testing if service state affects the result...\n")
print("Waiting 30 seconds for service to settle...")
time.sleep(30)

fresh_result = crawl_url("https://www.talgraf.fi/yhteystiedot/", "yhteystiedot")
print_result(1, fresh_result)

print("\n" + "=" * 80)
print("ANALYSIS")
print("=" * 80)

# Analyze results
total_yhteystiedot = yhteystiedot_results + yhteystiedot_alt + [fresh_result]
total_yhteystiedot_success = len(
    [r for r in total_yhteystiedot if r["success"] and r["chars"] > 100]
)
total_yhteystiedot_fail = len(
    [r for r in total_yhteystiedot if r["success"] and r["chars"] < 100]
)

total_yritys = yritys_results + yritys_alt
total_yritys_success = len(
    [r for r in total_yritys if r["success"] and r["chars"] > 100]
)
total_yritys_fail = len([r for r in total_yritys if r["success"] and r["chars"] < 100])

print("\n📊 Overall Results:")
print(f"\n/yhteystiedot/ ({len(total_yhteystiedot)} requests):")
print(
    f"   ✅ Success: {total_yhteystiedot_success} ({total_yhteystiedot_success/len(total_yhteystiedot)*100:.1f}%)"
)
print(
    f"   ❌ Failure: {total_yhteystiedot_fail} ({total_yhteystiedot_fail/len(total_yhteystiedot)*100:.1f}%)"
)

print(f"\n/yritys/ ({len(total_yritys)} requests):")
print(
    f"   ✅ Success: {total_yritys_success} ({total_yritys_success/len(total_yritys)*100:.1f}%)"
)
print(
    f"   ❌ Failure: {total_yritys_fail} ({total_yritys_fail/len(total_yritys)*100:.1f}%)"
)

print("\n🔍 Conclusions:")

if total_yhteystiedot_fail > 0:
    print(
        f"   • /yhteystiedot/ is INTERMITTENTLY FAILING ({total_yhteystiedot_fail}/{len(total_yhteystiedot)} failures)"
    )
    print("   • This is NOT about concurrency (happens even alone)")
    print("   • This is NOT about timing (happens even with delays)")
    print("   • This appears to be PAGE-SPECIFIC or service-state related")
else:
    print("   • /yhteystiedot/ succeeded in ALL tests")
    print("   • Bug may be less frequent than initially thought")

if total_yritys_fail > 0:
    print(f"   • /yritys/ also has failures ({total_yritys_fail}/{len(total_yritys)})")
    print("   • Bug is not specific to /yhteystiedot/")
else:
    print("   • /yritys/ succeeded in ALL tests")
    print("   • /yritys/ appears more reliable than /yhteystiedot/")

print("\n" + "=" * 80)
