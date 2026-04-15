#!/usr/bin/env python3
"""
Test script to verify authentication is working correctly
"""
import requests
import os


def test_authentication(base_url="http://localhost:11235", api_token=None):
    """Test the authentication system"""

    print("🔐 Testing Authentication System")
    print(f"🌐 Base URL: {base_url}")
    print(f"🔑 API Token: {'***' + api_token[-8:] if api_token else 'None'}")
    print("=" * 50)

    # Test 1: Health check (should work without auth)
    print("\n📋 Test 1: Health Check (No Auth Required)")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.text}")
    except Exception as e:
        print(f"❌ Health check error: {str(e)}")

    # Test 2: Crawl without authentication (should fail)
    print("\n📋 Test 2: Crawl Without Authentication (Should Fail)")
    try:
        payload = {
            "urls": ["https://example.com"],
            "browser_config": {"headless": True},
            "crawler_config": {},
        }
        response = requests.post(f"{base_url}/crawl", json=payload, timeout=30)
        print(f"Status: {response.status_code}")
        if response.status_code == 401:
            print("✅ Correctly rejected unauthorized request")
        else:
            print(f"❌ Should have returned 401, got {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Request error: {str(e)}")

    # Test 3: Crawl with authentication (should work)
    if api_token:
        print("\n📋 Test 3: Crawl With Authentication (Should Work)")
        try:
            headers = {"Authorization": f"Bearer {api_token}"}
            payload = {
                "urls": ["https://example.com"],
                "browser_config": {"headless": True},
                "crawler_config": {
                    "markdown_generator": {
                        "type": "DefaultMarkdownGenerator",
                        "params": {
                            "content_filter": {
                                "type": "PruningContentFilter",
                                "params": {
                                    "threshold": 0.6,
                                    "threshold_type": "fixed",
                                    "min_word_threshold": 0,
                                },
                            },
                            "options": {"ignore_links": False},
                        },
                    }
                },
            }
            response = requests.post(
                f"{base_url}/crawl", json=payload, headers=headers, timeout=30
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("results"):
                    result = data["results"][0]
                    print("✅ Authenticated crawl successful")
                    print(f"🔗 URL: {result.get('url')}")
                    print(
                        f"📝 Title: {result.get('metadata', {}).get('title', 'No title')}"
                    )
                    print(
                        f"📄 Markdown Length: {len(result.get('markdown', {}).get('raw_markdown', ''))}"
                    )
                    print(
                        f"✂️  Fit Markdown Length: {len(result.get('markdown', {}).get('fit_markdown', ''))}"
                    )
                    print(
                        f"🔗 Links: {len(result.get('links', {}).get('external', []))} external"
                    )
                else:
                    print(f"❌ Crawl failed: {data}")
            else:
                print(f"❌ Crawl failed with status {response.status_code}")
                print(f"Response: {response.text}")
        except Exception as e:
            print(f"❌ Authenticated request error: {str(e)}")
    else:
        print("\n📋 Test 3: Skipped (No API Token Provided)")

    # Test 4: Test token endpoint if available
    if api_token:
        print("\n📋 Test 4: Token Endpoint Test")
        try:
            headers = {"Authorization": f"Bearer {api_token}"}
            response = requests.get(f"{base_url}/token", headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Token endpoint working")
                print(f"Response: {response.json()}")
            else:
                print(
                    f"ℹ️  Token endpoint not available or different response: {response.status_code}"
                )
        except Exception as e:
            print(f"ℹ️  Token endpoint test: {str(e)}")


def generate_test_token():
    """Generate a test token for local testing"""
    import secrets

    return f"crawl4ai-test-{secrets.token_hex(16)}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Crawl4AI authentication")
    parser.add_argument(
        "--url", default="http://localhost:11235", help="Base URL of the API"
    )
    parser.add_argument("--token", help="API token to test with")
    parser.add_argument(
        "--generate-token", action="store_true", help="Generate a test token"
    )

    args = parser.parse_args()

    if args.generate_token:
        token = generate_test_token()
        print(f"Generated test token: {token}")
        print(f"Set environment variable: export CRAWL4AI_API_TOKEN={token}")
        exit(0)

    api_token = args.token or os.environ.get("CRAWL4AI_API_TOKEN")

    test_authentication(args.url, api_token)

    print("\n🎉 Authentication tests completed!")
