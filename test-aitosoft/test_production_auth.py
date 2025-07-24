#!/usr/bin/env python3
"""
Test production authentication with the simplified Bearer token approach
"""
import requests
import json
import os

def test_production_auth():
    """Test the production authentication setup"""
    
    base_url = "https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io"
    
    print("🧪 Testing Production Authentication")
    print(f"🌐 Base URL: {base_url}")
    print("="*60)
    
    # Test 1: Health check (should always work)
    print("\n📋 Test 1: Health Check (No Auth Required)")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            print("✅ Health check passed")
            data = response.json()
            print(f"   Version: {data.get('version', 'unknown')}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
    
    # Test 2: Crawl with correct Bearer token
    print("\n📋 Test 2: Crawl with Correct Bearer Token")
    try:
        bearer_token = os.environ.get('C4AI_TOKEN', '')
        if not bearer_token:
            print("❌ C4AI_TOKEN environment variable not set")
            return
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}"
        }
        
        payload = {
            "urls": ["https://example.com"],
            "browser_config": {"headless": True, "verbose": False},
            "crawler_config": {
                "markdown_generator": {
                    "type": "DefaultMarkdownGenerator",
                    "params": {
                        "content_filter": {
                            "type": "PruningContentFilter",
                            "params": {
                                "threshold": 0.6,
                                "threshold_type": "fixed",
                                "min_word_threshold": 0
                            }
                        },
                        "options": {"ignore_links": False}
                    }
                }
            }
        }
        
        response = requests.post(f"{base_url}/crawl", json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("results"):
                result = data["results"][0]
                print("✅ Authenticated crawl successful")
                print(f"   URL: {result.get('url')}")
                print(f"   Title: {result.get('metadata', {}).get('title', 'No title')}")
                print(f"   Raw Markdown: {len(result.get('markdown', {}).get('raw_markdown', ''))} chars")
                print(f"   Fit Markdown: {len(result.get('markdown', {}).get('fit_markdown', ''))} chars")
                print(f"   External Links: {len(result.get('links', {}).get('external', []))}")
                
                # Check if fit_markdown is working
                if result.get('markdown', {}).get('fit_markdown'):
                    print("✅ fit_markdown is working correctly")
                else:
                    print("⚠️  fit_markdown is empty")
            else:
                print(f"❌ Crawl failed: {data}")
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"❌ Authenticated request error: {e}")
    
    # Test 3: Crawl with wrong Bearer token
    print("\n📋 Test 3: Crawl with Wrong Bearer Token")
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer wrong-token"
        }
        
        payload = {
            "urls": ["https://example.com"],
            "browser_config": {"headless": True}
        }
        
        response = requests.post(f"{base_url}/crawl", json=payload, headers=headers, timeout=30)
        
        if response.status_code == 401:
            print("✅ Correctly rejected wrong token")
        elif response.status_code == 200:
            print("⚠️  Request succeeded - authentication may not be enforced")
        else:
            print(f"❓ Unexpected status: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"❌ Wrong token test error: {e}")
    
    # Test 4: Crawl without Bearer token
    print("\n📋 Test 4: Crawl Without Bearer Token")
    try:
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "urls": ["https://example.com"],
            "browser_config": {"headless": True}
        }
        
        response = requests.post(f"{base_url}/crawl", json=payload, headers=headers, timeout=30)
        
        if response.status_code == 401:
            print("✅ Correctly rejected request without token")
        elif response.status_code == 200:
            print("⚠️  Request succeeded - authentication may not be enforced")
        else:
            print(f"❓ Unexpected status: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"❌ No token test error: {e}")
    
    print("\n🎯 Summary:")
    print("For internal application use, you should:")
    print('1. Set C4AI_TOKEN environment variable with the bearer token')
    print('2. Always include: "Authorization: Bearer $C4AI_TOKEN"')
    print("3. The token is securely stored in Azure Key Vault")
    print("4. Your application can use this same token for all requests")
    print("5. No token expiration to worry about")

if __name__ == "__main__":
    test_production_auth()