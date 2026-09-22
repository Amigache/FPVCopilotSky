"""
Opt-in API authentication.

Behaviour:
  - If the environment variable ``FPV_API_TOKEN`` is set (non-empty), every
    ``/api/*`` request must carry ``Authorization: Bearer <token>``. The
    WebSocket endpoint ``/ws`` must pass ``?token=<token>`` (or an
    ``Authorization`` header).
  - If ``FPV_API_TOKEN`` is not set, authentication is disabled (development /
    backwards-compatible mode) and a warning is logged once.

The token is compared in constant time (``hmac.compare_digest``).

This intentionally does not implement user accounts, sessions or RBAC: it is a
single shared secret meant to keep an unauthenticated appliance off the network
until a full auth layer is designed.
"""

import hmac
import logging
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

AUTH_TOKEN_ENV = "FPV_API_TOKEN"
AUTH_HEADER = "Authorization"
BEARER_PREFIX = "bearer "

# Paths reachable without a token even when auth is enabled (needed by the
# frontend to discover whether a token must be provided).
PUBLIC_PATHS = {"/api/auth/status"}

_warned_disabled = False


def get_api_token() -> Optional[str]:
    """Return the configured API token, or None if auth is disabled."""
    token = os.getenv(AUTH_TOKEN_ENV, "").strip()
    return token or None


def is_auth_enabled() -> bool:
    """Whether API authentication is enforced."""
    return get_api_token() is not None


def extract_bearer_token(header_value: Optional[str]) -> Optional[str]:
    """Extract the token from an Authorization header value."""
    if not header_value:
        return None
    if header_value.lower().startswith(BEARER_PREFIX):
        return header_value[len(BEARER_PREFIX) :].strip()
    # Accept a raw token too (useful for CLI clients).
    return header_value.strip()


def verify_token(candidate: Optional[str]) -> bool:
    """Constant-time check of *candidate* against the configured token."""
    expected = get_api_token()
    if expected is None:
        return True
    if not candidate:
        return False
    return hmac.compare_digest(candidate, expected)


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS


def extract_subprotocol_token(subprotocols) -> Optional[str]:
    """Extract the API token from WebSocket subprotocols (``token.<value>``).

    Browsers cannot set custom headers on a WebSocket, so the token can be sent
    as a subprotocol instead of a query string (which leaks into logs/history).
    """
    for subprotocol in subprotocols or []:
        if isinstance(subprotocol, str) and subprotocol.startswith("token."):
            return subprotocol[len("token.") :]
    return None


async def require_auth(request: Request, call_next):
    """HTTP middleware enforcing the token on ``/api/*`` when enabled."""
    global _warned_disabled

    if not is_auth_enabled():
        if not _warned_disabled:
            logger.warning(
                "API authentication is DISABLED (no %s). The API is open — set " "%s to enable bearer-token auth.",
                AUTH_TOKEN_ENV,
                AUTH_TOKEN_ENV,
            )
            _warned_disabled = True
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api/") or _is_public_path(path):
        return await call_next(request)

    token = extract_bearer_token(request.headers.get(AUTH_HEADER))
    if not verify_token(token):
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await call_next(request)
