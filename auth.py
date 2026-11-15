import os
from functools import lru_cache
from typing import Iterable

import jwt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError
from jwt.exceptions import InvalidTokenError


KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER",
    "http://localhost:8081/realms/soa",
)
KEYCLOAK_JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL",
    "http://keycloak:8080/realms/soa/protocol/openid-connect/certs",
)
API_AUDIENCE = os.getenv("API_AUDIENCE", "todo-api")


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(KEYCLOAK_JWKS_URL, cache_keys=True, timeout=5)


def decode_access_token(token: str) -> dict:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Identity provider is unavailable",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    except PyJWKClientError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER,
            audience=API_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return claims


def verify_authorization(
    authorization: str | None,
    required_scopes: Iterable[str] = (),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")

    claims = decode_access_token(token)
    granted_scopes = set(claims.get("scope", "").split())
    missing_scopes = set(required_scopes) - granted_scopes
    if missing_scopes:
        raise HTTPException(
            status_code=403,
            detail="Insufficient OAuth scope",
            headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
        )
    return claims


def require_bearer_token(
    authorization: str | None,
    required_scopes: Iterable[str] = (),
) -> str:
    verify_authorization(authorization, required_scopes)
    return authorization[len("Bearer "):].strip()


def cors_origins() -> list[str]:
    configured = os.getenv(
        "CORS_ORIGINS",
        "https://cad.kpi.ua,http://localhost:3000,http://localhost:6274,http://127.0.0.1:6274",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def install_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "A2A-Version"],
    )
