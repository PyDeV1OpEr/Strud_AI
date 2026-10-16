# auth.py
#
# Strud AI — server-side authentication boundary.
#
# When SUPABASE_URL is configured, every protected /api route requires a
# valid Supabase Auth access token (the browser session JWT from Google
# sign-in). The verified `sub` (auth.uid) becomes the ONLY accepted user
# identity: request-supplied user_id values are overridden centrally so
# no caller can act on another user's account by changing an ID.
#
# Token signing:
#   • Preferred: RS256 via Supabase's JWKS endpoint (asymmetric keys) —
#     verification needs only the public keys.
#   • Fallback: HS256 with SUPABASE_JWT_SECRET for deployments still on
#     legacy symmetric JWT secrets.
#
# Local development (no SUPABASE_URL) keeps the original open behavior.

from __future__ import annotations

import os
import threading

import jwt
from fastapi import HTTPException

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""
JWT_ISSUER = f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else ""

AUTH_CONFIGURED = bool(SUPABASE_URL)

_jwk_client = None
_client_lock = threading.Lock()


def _jwks():
    global _jwk_client
    with _client_lock:
        if _jwk_client is None:
            _jwk_client = jwt.PyJWKClient(JWKS_URL, cache_keys=True)
        return _jwk_client


def verify_access_token(token: str) -> str:
    """Validate a Supabase access token and return the verified subject."""
    if not AUTH_CONFIGURED:
        raise RuntimeError("Auth is not configured")
    try:
        decode_options = {"require": ["exp", "sub", "aud", "iss"]}
        if SUPABASE_JWT_SECRET:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=JWT_ISSUER,
                options=decode_options,
            )
        else:
            signing_key = _jwks().get_signing_key_from_jwt(token)
            # PyJWKClient selects a trusted key by kid.  Constrain the
            # algorithm to that key's declared asymmetric algorithm instead
            # of accepting an attacker-controlled JWT header.
            algorithm = signing_key.algorithm_name
            if algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
                raise jwt.InvalidAlgorithmError("Unsupported signing algorithm")
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=JWT_ISSUER,
                options=decode_options,
            )
    except jwt.InvalidTokenError as error:  # noqa: BLE001 — single 401 shape
        raise HTTPException(status_code=401, detail="Unauthorized") from error
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(subject)
