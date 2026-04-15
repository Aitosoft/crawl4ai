#!/usr/bin/env python3
"""
Get a JWT token for testing the API
"""
import requests
import sys


def get_api_token(base_url="http://localhost:11235", email="internal@company.com"):
    """Get a JWT token from the API"""

    print(f"🔑 Getting API token from {base_url}")
    print(f"📧 Email: {email}")

    try:
        # Request a token
        response = requests.post(f"{base_url}/token", json={"email": email}, timeout=10)

        print(f"📡 Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print("✅ Token retrieved successfully")
            print(f"🔑 Token: {token}")
            print(f"📧 Email: {data.get('email')}")
            print(f"🔒 Token Type: {data.get('token_type')}")
            print("\n💡 Usage:")
            print(f"   export CRAWL4AI_API_TOKEN={token}")
            print(f'   curl -H "Authorization: Bearer {token}" {base_url}/health')
            return token
        else:
            print(f"❌ Failed to get token: {response.status_code}")
            print(f"📄 Response: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Get JWT token for Crawl4AI API")
    parser.add_argument(
        "--url", default="http://localhost:11235", help="Base URL of the API"
    )
    parser.add_argument(
        "--email", default="internal@company.com", help="Email for token request"
    )

    args = parser.parse_args()

    token = get_api_token(args.url, args.email)

    if token:
        print("\n🎉 Token ready for use!")
        sys.exit(0)
    else:
        print("\n❌ Failed to get token")
        sys.exit(1)
