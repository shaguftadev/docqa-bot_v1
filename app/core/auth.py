"""Cognito access-token verification and tenant authorization helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)
_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant_id: str | None
    scopes: frozenset[str] = frozenset()


class CognitoTokenError(ValueError):
    """Raised when a Cognito access token cannot be trusted."""


@lru_cache(maxsize=8)
def _jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer.rstrip('/')}/.well-known/jwks.json", timeout=5)


def verify_cognito_access_token(token: str, settings: Settings) -> Principal:
    """Verify Cognito signature and access-token claims, then extract tenant scope."""
    if not settings.auth_enabled or not settings.cognito_issuer or not settings.cognito_app_client_id:
        raise CognitoTokenError("Cognito authentication is not configured")
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise CognitoTokenError("Unsupported token signing algorithm")
        signing_key = _jwks_client(settings.cognito_issuer).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.cognito_issuer,
            audience=settings.cognito_resource_audience,
            options={
                "require": ["exp", "iat", "iss", "sub", "token_use", "client_id"],
                "verify_aud": settings.cognito_resource_audience is not None,
            },
        )
    except CognitoTokenError:
        raise
    except Exception as exc:
        # Do not return token, key, or provider error details to the caller.
        raise CognitoTokenError("Access token verification failed") from exc

    if claims.get("token_use") != "access":
        raise CognitoTokenError("A Cognito access token is required")
    if claims.get("client_id") != settings.cognito_app_client_id:
        raise CognitoTokenError("Access token was issued to a different app client")
    if claims.get("aud") is not None and settings.cognito_resource_audience is None:
        raise CognitoTokenError("A resource audience must be configured for this access token")
    subject = claims.get("sub")
    tenant_id = claims.get(settings.cognito_tenant_claim)
    if not isinstance(subject, str) or not subject:
        raise CognitoTokenError("Access token has no subject")
    if not isinstance(tenant_id, str) or not _TENANT_PATTERN.fullmatch(tenant_id):
        raise CognitoTokenError("Access token has no valid tenant claim")
    raw_scopes = claims.get("scope", "")
    scopes = frozenset(raw_scopes.split()) if isinstance(raw_scopes, str) else frozenset()
    return Principal(subject=subject, tenant_id=tenant_id, scopes=scopes)


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Authenticate requests when enabled; local development remains token-free."""
    if not settings.auth_enabled:
        return Principal(subject="local-demo", tenant_id=None)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Cognito access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verify_cognito_access_token(credentials.credentials, settings)
    except CognitoTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Cognito access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def enforce_tenant_access(principal: Principal, requested_tenant_id: str) -> None:
    """Reject caller-selected tenant IDs that differ from verified identity claims."""
    if principal.tenant_id is not None and principal.tenant_id != requested_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
