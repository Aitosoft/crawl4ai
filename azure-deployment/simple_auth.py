"""
Simple header-based authentication for internal use
This replaces the JWT system with a simple API key check
"""
import os
from typing import Optional, Dict
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Simple bearer token security
security = HTTPBearer(auto_error=False)

def get_api_token() -> str:
    """Get the API token from environment variable"""
    token = os.environ.get("CRAWL4AI_API_TOKEN")
    if not token:
        raise RuntimeError("CRAWL4AI_API_TOKEN environment variable not set")
    return token

def verify_api_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Verify the API token from Authorization header"""
    
    # For internal use, we also allow bypassing auth in development
    if os.environ.get("ENVIRONMENT") == "development":
        if credentials is None:
            return {"authenticated": False, "user": "development"}
    
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required. Use 'Authorization: Bearer <your-token>'"
        )
    
    expected_token = get_api_token()
    provided_token = credentials.credentials
    
    if provided_token != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid API token"
        )
    
    return {"authenticated": True, "user": "internal"}

def get_auth_dependency(config: Dict):
    """Return the auth dependency based on configuration"""
    
    # Check if auth is enabled
    if config.get("security", {}).get("auth_enabled", True):
        return verify_api_token
    else:
        # Return a function that always passes (for development)
        return lambda: {"authenticated": False, "user": "bypass"}

# Alternative: Simple header-based auth without Bearer token
def verify_simple_header(request: Request) -> Dict:
    """Check for X-API-Key header"""
    
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="X-API-Key header is required"
        )
    
    expected_token = get_api_token()
    if api_key != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return {"authenticated": True, "user": "internal"}

# Export the main verification function
__all__ = ["verify_api_token", "verify_simple_header", "get_auth_dependency"]