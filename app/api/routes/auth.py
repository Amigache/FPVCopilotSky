"""Authentication status endpoint (always reachable)."""

from fastapi import APIRouter, Request

from app.security.auth import (
    AUTH_HEADER,
    extract_bearer_token,
    is_auth_enabled,
    verify_token,
)

router = APIRouter()


@router.get("/status")
async def auth_status(request: Request):
    """Report whether auth is required and whether the caller is authenticated.

    This endpoint is public so the frontend can discover the auth mode and
    validate a stored token before loading the rest of the application.
    """
    enabled = is_auth_enabled()
    token = extract_bearer_token(request.headers.get(AUTH_HEADER))
    authenticated = (not enabled) or verify_token(token)
    return {"auth_required": enabled, "authenticated": authenticated}
