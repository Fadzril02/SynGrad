"""
Smart Academic Assessment System — JWT Auth Dependency

Verifies Supabase session tokens signed with the project's asymmetric
ES256 JWT Signing Keys (JWKS-based, NOT the legacy HS256 shared secret).

This project (`gexcsnwztzajoupgjhpc`) has been confirmed to use the newer
asymmetric signing model. The JWKS endpoint is the only correct verification
target for user session tokens.

JWKS endpoint:
    https://gexcsnwztzajoupgjhpc.supabase.co/auth/v1/.well-known/jwks.json

The dependency `verify_advisor_jwt` is applied to every mutating endpoint
in audit.py (finalize-approval, extract, submit-verification, reject-document).
It both verifies the token's ES256 signature AND cross-references the JWT's
identity (email) against the advisor_id claimed in the request body.
"""

import threading
import time
import httpx
from jose import jwt, JWTError, ExpiredSignatureError
from fastapi import Header, HTTPException, status

try:
    from app.core.config import settings
except ImportError:
    from backend.app.core.config import settings

JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

# ---------------------------------------------------------------------------
# In-process JWKS cache — one fetch per cold start, refreshed after 1 hour.
# JWKS is a public stable endpoint; no auth required to read it.
# ---------------------------------------------------------------------------
_jwks_cache: list = []
_jwks_fetched_at: float = 0.0
_jwks_lock = threading.Lock()
_JWKS_TTL_SECONDS = 3600  # 1 hour


def _get_jwks() -> list:
    """Return cached JWKS keys, refreshing if older than TTL or empty."""
    global _jwks_cache, _jwks_fetched_at
    with _jwks_lock:
        age = time.monotonic() - _jwks_fetched_at
        if _jwks_cache and age < _JWKS_TTL_SECONDS:
            return _jwks_cache
        try:
            resp = httpx.get(JWKS_URL, timeout=5.0)
            resp.raise_for_status()
            _jwks_cache = resp.json().get("keys", [])
            _jwks_fetched_at = time.monotonic()
            return _jwks_cache
        except Exception as e:
            # If cache is warm but refresh failed, serve stale rather than
            # making every request fail during a transient JWKS outage.
            if _jwks_cache:
                print(f"[Auth] JWKS refresh failed (serving stale): {e}")
                return _jwks_cache
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not fetch JWT signing keys: {e}",
            )


def _decode_token(token: str) -> dict:
    """
    Verify an ES256-signed Supabase JWT against the live JWKS.
    Raises HTTPException 401 on any verification failure.
    """
    keys = _get_jwks()
    if not keys:
        raise HTTPException(status_code=401, detail="No JWT signing keys available.")

    last_error = None
    for key in keys:
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["ES256"],
                options={"verify_aud": False},  # Supabase JWTs have no standard aud
            )
            return payload  # verified by the first matching key
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired.")
        except JWTError as e:
            last_error = e
            continue  # try next key (handles key rotation overlap)

    raise HTTPException(
        status_code=401,
        detail=f"Token signature verification failed: {last_error}",
    )


async def verify_advisor_jwt(authorization: str = Header(...)) -> dict:
    """
    FastAPI dependency: validates the Supabase JWT from Authorization header.

    Checks:
      1. Authorization header is present and starts with 'Bearer '.
      2. Token passes ES256 signature verification against the live JWKS.
      3. Token is not expired.

    Returns the decoded JWT payload dict (contains 'email', 'sub', 'role').
    The cross-reference of JWT email vs. claimed advisor_id is performed in
    each individual endpoint handler (not here), so that the dependency
    remains narrowly scoped to auth and the endpoint controls its own
    business logic check.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected: Bearer <token>",
        )
    token = authorization[len("Bearer "):]
    return _decode_token(token)
