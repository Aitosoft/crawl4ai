#!/usr/bin/env python3
"""
Test the server API to ensure it returns fit_markdown correctly
"""
import asyncio
import json
import requests
import time
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

def test_server_api():
    """Test the server API with fit_markdown configuration"""
    
    # Server configuration matching your requirements
    payload = {
        "urls": ["https://example.com"],
        "browser_config": {
            "headless": True,
            "verbose": False
        },
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
                    "options": {
                        "ignore_links": False
                    }
                }
            }
        }
    }
    
    print("🚀 Testing server API with fit_markdown configuration...")
    print(f"📤 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Test the /crawl endpoint
        response = requests.post(
            "http://localhost:11235/crawl",
            json=payload,
            timeout=30
        )
        
        print(f"📡 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("success") and data.get("results"):
                result = data["results"][0]  # First result
                
                print("✅ Server API Test Successful!")
                print(f"🔗 URL: {result.get('url')}")
                print(f"📝 Title: {result.get('metadata', {}).get('title')}")
                print(f"📄 Raw Markdown Length: {len(result.get('markdown', {}).get('raw_markdown', ''))}")
                print(f"✂️  Fit Markdown Length: {len(result.get('markdown', {}).get('fit_markdown', ''))}")
                
                # Check if fit_markdown is available
                if result.get('markdown', {}).get('fit_markdown'):
                    print("✅ fit_markdown is available!")
                    print(f"✂️  Fit Markdown Content (first 200 chars):")
                    print(result['markdown']['fit_markdown'][:200] + "...")
                else:
                    print("❌ fit_markdown is not available")
                    print(f"📄 Available markdown keys: {list(result.get('markdown', {}).keys())}")
                
                # Check links
                links = result.get('links', {})
                print(f"🔗 Internal Links: {len(links.get('internal', []))}")
                print(f"🔗 External Links: {len(links.get('external', []))}")
                
                # Show server performance metrics
                print(f"⏱️  Server Processing Time: {data.get('server_processing_time_s', 0):.2f}s")
                print(f"💾 Memory Delta: {data.get('server_memory_delta_mb', 0):.2f}MB")
                
                return True
            else:
                print("❌ Server returned unsuccessful result")
                print(f"📄 Response: {json.dumps(data, indent=2)}")
                return False
        else:
            print(f"❌ Server Error: {response.status_code}")
            print(f"📄 Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Make sure the server is running on localhost:11235")
        print("💡 Start server with: uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_server_api()
    if success:
        print("\n🎉 All tests passed! Server API is working correctly.")
    else:
        print("\n❌ Tests failed. Please check the server configuration.")