"""
Custom server configuration for Azure deployment
This modifies the existing server to use simple header authentication
"""
import os
import sys
from pathlib import Path

# Add the docker directory to the path so we can import from it
docker_dir = Path(__file__).parent.parent / "deploy" / "docker"
sys.path.insert(0, str(docker_dir))

# Import the original server components
from server import *  # Import everything from the original server
from simple_auth import verify_api_token, get_auth_dependency

# Override the auth configuration
def get_custom_auth_dependency():
    """Return our custom auth dependency"""
    return verify_api_token

# Create a custom app instance with our auth
def create_custom_app():
    """Create the FastAPI app with custom authentication"""
    
    # Get the original config
    original_config = load_config()
    
    # Enable authentication
    original_config["security"]["auth_enabled"] = True
    
    # Create the app (this will use the original server's create_app logic)
    # But we'll override the auth dependency
    
    # Import the main app creation
    from server import app
    
    # Override the token dependency for all routes that need it
    # We'll need to modify the route dependencies
    
    return app

# Health check endpoint (no auth required)
@app.get("/health")
async def health_check():
    """Health check endpoint for Azure Container Apps"""
    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": time.time(),
        "environment": os.environ.get("ENVIRONMENT", "unknown")
    }

# Add authenticated version info endpoint
@app.get("/version")
async def version_info(auth: dict = Depends(verify_api_token)):
    """Get version information (requires authentication)"""
    return {
        "version": __version__,
        "crawl4ai_version": _c4.__version__,
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
        "authenticated_user": auth.get("user", "unknown")
    }

# Update the main crawl endpoint to use our auth
# We need to find the original endpoint and update it
for route in app.routes:
    if hasattr(route, 'path') and route.path == "/crawl":
        # Add our auth dependency to the crawl route
        if hasattr(route, 'dependant') and route.dependant:
            # This is a bit tricky - we need to modify the existing route
            # For now, we'll create a new route that overrides it
            break

# Create a new authenticated crawl endpoint
@app.post("/crawl")
async def authenticated_crawl(
    request: CrawlRequest,
    auth: dict = Depends(verify_api_token),
    req: Request = None
):
    """Crawl endpoint with authentication"""
    
    # Call the original crawl handler
    from api import handle_crawl_request
    
    # Convert request to the format expected by the handler
    urls = request.urls if isinstance(request.urls, list) else [request.urls]
    browser_config = request.browser_config or {}
    crawler_config = request.crawler_config or {}
    
    # Load the global config
    global_config = load_config()
    
    try:
        result = await handle_crawl_request(
            urls=urls,
            browser_config=browser_config,
            crawler_config=crawler_config,
            config=global_config
        )
        
        # Add authentication info to the result
        result["auth"] = {
            "user": auth.get("user", "unknown"),
            "authenticated": True
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Crawl request failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Export the app
__all__ = ["app"]