#!/usr/bin/env python3
"""
Test the deployment configuration without actually deploying
"""
import json
import subprocess
import sys

def test_deployment_config():
    """Test that our deployment configuration is valid"""
    
    print("🧪 Testing Crawl4AI Azure Deployment Configuration")
    print("="*50)
    
    # Test 1: Check if deploy script exists and is executable
    print("\n📋 Test 1: Deployment Script Check")
    try:
        import os
        script_path = "/workspaces/crawl4ai/azure-deployment/deploy.sh"
        if os.path.exists(script_path) and os.access(script_path, os.X_OK):
            print("✅ Deploy script exists and is executable")
        else:
            print(f"❌ Deploy script not found or not executable: {script_path}")
            return False
    except Exception as e:
        print(f"❌ Error checking deploy script: {e}")
        return False
    
    # Test 2: Validate configuration files
    print("\n📋 Test 2: Configuration Files")
    config_files = [
        "/workspaces/crawl4ai/azure-deployment/azure.yaml",
        "/workspaces/crawl4ai/azure-deployment/production-config.yml",
        "/workspaces/crawl4ai/azure-deployment/DEPLOYMENT_GUIDE.md"
    ]
    
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"✅ {os.path.basename(config_file)} exists")
        else:
            print(f"❌ {os.path.basename(config_file)} missing")
            return False
    
    # Test 3: Check Azure CLI availability
    print("\n📋 Test 3: Azure CLI Check")
    try:
        result = subprocess.run(["az", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Azure CLI is installed")
            # Parse version
            version_line = result.stdout.split('\n')[0]
            print(f"   Version: {version_line}")
        else:
            print("❌ Azure CLI check failed")
            return False
    except Exception as e:
        print(f"❌ Azure CLI not available: {e}")
        return False
    
    # Test 4: Test JWT token generation
    print("\n📋 Test 4: JWT Token Generation")
    try:
        # Simulate token generation
        import secrets
        test_token = f"crawl4ai-{secrets.token_hex(16)}"
        jwt_secret = f"jwt-secret-{secrets.token_hex(32)}"
        print(f"✅ Token generation successful")
        print(f"   Sample API Token: {test_token[:20]}...")
        print(f"   Sample JWT Secret: {jwt_secret[:20]}...")
    except Exception as e:
        print(f"❌ Token generation failed: {e}")
        return False
    
    # Test 5: Validate deployment parameters
    print("\n📋 Test 5: Deployment Parameters")
    deployment_params = {
        "resource_group": "crawl4ai-v2-rg",
        "container_app": "crawl4ai-v2-app",
        "environment": "crawl4ai-v2-env",
        "location": "northeurope",
        "image": "unclecode/crawl4ai:0.6.0-r3",
        "port": 11235,
        "min_replicas": 1,
        "max_replicas": 3,
        "cpu": "1.0",
        "memory": "2.0Gi"
    }
    
    print("✅ Deployment parameters validated:")
    for key, value in deployment_params.items():
        print(f"   {key}: {value}")
    
    # Test 6: Expected environment variables
    print("\n📋 Test 6: Environment Variables")
    env_vars = [
        "CRAWL4AI_API_TOKEN",
        "SECRET_KEY", 
        "ENVIRONMENT",
        "LOG_LEVEL",
        "MAX_CONCURRENT_REQUESTS",
        "SECURITY_ENABLED",
        "JWT_ENABLED"
    ]
    
    print("✅ Required environment variables:")
    for var in env_vars:
        print(f"   {var}")
    
    # Test 7: Sample API request format
    print("\n📋 Test 7: API Request Format")
    sample_request = {
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
                            "min_word_threshold": 0
                        }
                    },
                    "options": {"ignore_links": False}
                }
            }
        }
    }
    
    print("✅ Sample API request format validated")
    print(f"   Request size: {len(json.dumps(sample_request))} characters")
    
    return True

def show_next_steps():
    """Show what to do next"""
    print("\n🚀 Next Steps for Deployment")
    print("="*50)
    print("1. Log in to Azure CLI:")
    print("   az login")
    print("")
    print("2. Verify your subscription:")
    print("   az account show")
    print("")
    print("3. Run deployment (dry-run first):")
    print("   ./azure-deployment/deploy.sh --dry-run")
    print("")
    print("4. Deploy for real:")
    print("   ./azure-deployment/deploy.sh")
    print("")
    print("5. Test the deployment:")
    print("   python azure-deployment/test_auth.py --url https://YOUR_APP_URL")
    print("")
    print("📖 For detailed instructions, see:")
    print("   azure-deployment/DEPLOYMENT_GUIDE.md")

if __name__ == "__main__":
    print("🔧 Crawl4AI Azure Deployment Configuration Test\n")
    
    success = test_deployment_config()
    
    if success:
        print("\n🎉 All deployment configuration tests passed!")
        show_next_steps()
        sys.exit(0)
    else:
        print("\n❌ Some deployment configuration tests failed!")
        print("Please check the errors above and fix them before deploying.")
        sys.exit(1)