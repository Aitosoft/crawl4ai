"""
Simple static token authentication middleware
Checks Authorization: Bearer <token> against CRAWL4AI_API_TOKEN env var
"""
import os
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SimpleTokenAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check Bearer token against CRAWL4AI_API_TOKEN"""

    BYPASS_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks and docs
        if request.url.path in self.BYPASS_PATHS:
            return await call_next(request)

        # Get expected token from environment
        expected_token = os.environ.get("CRAWL4AI_API_TOKEN")
        if not expected_token:
            # If no token configured, allow all (development mode)
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Missing or invalid Authorization header."
                    " Use: Authorization: Bearer <token>"
                },
            )

        provided_token = auth_header[7:]  # Remove "Bearer " prefix

        if provided_token != expected_token:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})

        # Token is valid, proceed
        return await call_next(request)
