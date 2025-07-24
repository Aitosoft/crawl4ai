#!/usr/bin/env python3
"""
Orchestration script for running Crawl4AI validation tests
Runs the specific tests needed after crawl4ai updates
"""
import subprocess
import sys
import os
import time
import argparse
from datetime import datetime

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 60)
    print(f"🧪 {title}")
    print("=" * 60)

def print_status(message):
    """Print status message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] ℹ️  {message}")

def print_success(message):
    """Print success message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] ✅ {message}")

def print_error(message):
    """Print error message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] ❌ {message}")

def run_test_script(script_path, description, timeout=300):
    """Run a test script and return success status"""
    print_status(f"Running {description}...")
    
    if not os.path.exists(script_path):
        print_error(f"Test script not found: {script_path}")
        return False
    
    try:
        # Run the test script
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Print output
        if result.stdout:
            print("📄 Output:")
            print(result.stdout)
        
        if result.stderr:
            print("⚠️  Stderr:")
            print(result.stderr)
        
        if result.returncode == 0:
            print_success(f"{description} passed")
            return True
        else:
            print_error(f"{description} failed with exit code {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        print_error(f"{description} timed out after {timeout} seconds")
        return False
    except Exception as e:
        print_error(f"{description} failed with exception: {str(e)}")
        return False

def wait_for_server(host="localhost", port=11235, max_attempts=30, delay=2):
    """Wait for local server to be ready"""
    import socket
    
    print_status(f"Waiting for server at {host}:{port}...")
    
    for attempt in range(max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                print_success(f"Server is ready at {host}:{port}")
                return True
            else:
                if attempt < max_attempts - 1:
                    print_status(f"Server not ready, retrying in {delay}s... (attempt {attempt + 1}/{max_attempts})")
                    time.sleep(delay)
                
        except Exception as e:
            if attempt < max_attempts - 1:
                print_status(f"Connection failed, retrying in {delay}s... (attempt {attempt + 1}/{max_attempts})")
                time.sleep(delay)
    
    print_error(f"Server at {host}:{port} is not responding after {max_attempts} attempts")
    return False

def run_local_tests(skip_server=False):
    """Run local validation tests"""
    print_section("LOCAL VALIDATION TESTS")
    
    results = {}
    
    # Test 1: Basic crawling with fit_markdown
    results['fit_markdown'] = run_test_script(
        'test-aitosoft/test_fit_markdown.py', 
        'Basic crawling with fit_markdown validation',
        timeout=120
    )
    
    if not skip_server:
        # Test 2: Server API tests (requires server to be running)
        print_status("Checking if local server is running...")
        if wait_for_server():
            results['server_api'] = run_test_script(
                'test-aitosoft/test_server_api.py',
                'Local server API functionality',
                timeout=120
            )
        else:
            print_error("Local server is not running. Skipping server API tests.")
            print_status("Start server with: uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235")
            results['server_api'] = False
    else:
        print_status("Skipping server API tests (--skip-server flag)")
        results['server_api'] = None
    
    # Test 3: Authentication system test (local)
    results['auth_system'] = run_test_script(
        'test-aitosoft/test_production_auth.py',
        'Authentication system validation',
        timeout=60
    )
    
    return results

def run_production_tests(production_url, bearer_token):
    """Run production validation tests"""
    print_section("PRODUCTION VALIDATION TESTS")
    
    results = {}
    
    # Set environment variables for production test
    os.environ['PRODUCTION_URL'] = production_url
    os.environ['BEARER_TOKEN'] = bearer_token
    
    # Production authentication and crawl test
    results['production_auth'] = run_test_script(
        'azure-deployment/test_auth.py',
        f'Production deployment validation ({production_url})',
        timeout=180
    )
    
    return results

def print_summary(local_results, production_results=None):
    """Print test summary"""
    print_section("TEST SUMMARY")
    
    total_tests = 0
    passed_tests = 0
    
    print("📋 Local Tests:")
    for test_name, result in local_results.items():
        total_tests += 1
        if result is True:
            passed_tests += 1
            print(f"  ✅ {test_name}")
        elif result is False:
            print(f"  ❌ {test_name}")
        else:
            print(f"  ⏭️  {test_name} (skipped)")
            total_tests -= 1
    
    if production_results:
        print("\n📋 Production Tests:")
        for test_name, result in production_results.items():
            total_tests += 1
            if result:
                passed_tests += 1
                print(f"  ✅ {test_name}")
            else:
                print(f"  ❌ {test_name}")
    
    print(f"\n📊 Results: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print_success("All tests passed! 🎉")
        return True
    else:
        print_error(f"{total_tests - passed_tests} tests failed")
        return False

def main():
    parser = argparse.ArgumentParser(description='Run Crawl4AI validation tests')
    parser.add_argument('--local-only', action='store_true', 
                       help='Run only local tests')
    parser.add_argument('--production-only', action='store_true',
                       help='Run only production tests')
    parser.add_argument('--production-url', 
                       help='Production URL for testing')
    parser.add_argument('--bearer-token', 
                       default=os.environ.get('C4AI_TOKEN', ''),
                       help='Bearer token for authentication (defaults to C4AI_TOKEN env var)')
    parser.add_argument('--skip-server', action='store_true',
                       help='Skip server API tests that require local server')
    
    args = parser.parse_args()
    
    # Validation
    if args.production_only and not args.production_url:
        print_error("--production-url is required when using --production-only")
        sys.exit(1)
    
    print_section("CRAWL4AI VALIDATION TEST SUITE")
    print_status("Starting validation tests...")
    
    local_results = {}
    production_results = {}
    
    # Run local tests
    if not args.production_only:
        local_results = run_local_tests(skip_server=args.skip_server)
    
    # Run production tests
    if not args.local_only and args.production_url:
        production_results = run_production_tests(args.production_url, args.bearer_token)
    elif not args.local_only:
        print_status("No production URL provided, skipping production tests")
    
    # Print summary and determine exit code
    success = print_summary(local_results, production_results if production_results else None)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()