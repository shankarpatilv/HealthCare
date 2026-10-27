import asyncio
import logging
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_TOKENINFO_URI = "https://www.googleapis.com/oauth2/v3/tokeninfo"
GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]

# Equivalent of jwks-rsa client with cache: true, cacheMaxAge: 86400000 ms
_jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URI, cache_keys=True, lifespan=86400)


def _get_key(token: str) -> Any:
    try:
        return _jwks_client.get_signing_key_from_jwt(token).key
    except Exception as err:
        logger.error("JWKS Error: %s", err)
        raise


def _verify_jwt(token: str) -> dict:
    signing_key = _get_key(token)
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=GOOGLE_ISSUERS,
        options={"verify_aud": False},
    )


async def validate_bearer_token(request: Request) -> dict:
    """FastAPI dependency: verifies a Google bearer token (ID token JWT or opaque access token)."""
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:].strip()
    parts = token.split(".")

    if len(parts) != 3:
        logger.info("Token is not a JWT, checking with Google tokeninfo...")
        return await _validate_access_token(token, request)

    try:
        decoded = await asyncio.to_thread(_verify_jwt, token)
    except Exception as err:
        logger.error("Token verification failed: %s", err)
        raise HTTPException(status_code=401, detail="Invalid token")

    logger.info("JWT Token verified successfully")
    request.state.user = decoded
    return decoded


async def _validate_access_token(token: str, request: Request) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(GOOGLE_TOKENINFO_URI, params={"access_token": token})

        if not response.is_success:
            raise HTTPException(status_code=401, detail="Invalid access token")

        data = response.json()
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Access token validation failed: %s", err)
        raise HTTPException(status_code=401, detail="Invalid token")

    logger.info("Access token verified via Google tokeninfo")
    request.state.user = data
    return data
