from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core import auth
from app.core.auth import (
    CognitoTokenError,
    Principal,
    enforce_tenant_access,
    get_current_principal,
    verify_cognito_access_token,
)
from app.core.config import Settings
from app.core.config import get_settings
from app.db.session import get_db
from app.embeddings.provider import get_embedder
from app.main import app
from app.rag.qdrant_store import get_vector_store
from app.agent.checkpointer import get_checkpointer
from infra.cognito.pre_token_generation import lambda_handler


@pytest.fixture
def signing_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture
def cognito_settings():
    return Settings(
        _env_file=None,
        app_env="local",
        auth_enabled=True,
        cognito_issuer="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
        cognito_app_client_id="client-123",
    )


def make_token(private_key, **overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
        "sub": "user-123",
        "client_id": "client-123",
        "token_use": "access",
        "tenant_id": "tenant-a",
        "scope": "support/read",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def install_test_jwks(monkeypatch, public_key):
    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(auth, "_jwks_client", lambda issuer: FakeJwksClient())


def test_valid_cognito_access_token_yields_principal(monkeypatch, signing_keys, cognito_settings):
    private_key, public_key = signing_keys
    install_test_jwks(monkeypatch, public_key)

    principal = verify_cognito_access_token(make_token(private_key), cognito_settings)

    assert principal == Principal("user-123", "tenant-a", frozenset({"support/read"}))


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"token_use": "id"},
        {"client_id": "another-client"},
        {"iss": "https://attacker.example"},
        {"tenant_id": ""},
        {"aud": "https://unconfigured-resource.example"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_invalid_cognito_claims_are_rejected(
    monkeypatch, signing_keys, cognito_settings, claim_overrides
):
    private_key, public_key = signing_keys
    install_test_jwks(monkeypatch, public_key)

    with pytest.raises(CognitoTokenError):
        verify_cognito_access_token(make_token(private_key, **claim_overrides), cognito_settings)


def test_tenant_claim_enforces_request_scope():
    enforce_tenant_access(Principal("user-123", "tenant-a"), "tenant-a")

    with pytest.raises(HTTPException) as exc_info:
        enforce_tenant_access(Principal("user-123", "tenant-a"), "tenant-b")

    assert exc_info.value.status_code == 403


def test_auth_enabled_rejects_missing_bearer_token(cognito_settings):
    with pytest.raises(HTTPException) as exc_info:
        get_current_principal(None, cognito_settings)

    assert exc_info.value.status_code == 401


def test_auth_disabled_returns_local_demo_principal():
    settings = Settings(_env_file=None, app_env="local", auth_enabled=False)

    assert get_current_principal(None, settings) == Principal("local-demo", None)


def test_protected_api_requires_bearer_token(cognito_settings):
    app.dependency_overrides[get_settings] = lambda: cognito_settings
    app.dependency_overrides[get_db] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.get("/documents", params={"tenant_id": "tenant-a"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/documents?tenant_id=tenant-b", None),
        ("POST", "/knowledge/search", {"tenant_id": "tenant-b", "query": "returns"}),
        ("POST", "/agent/run", {"tenant_id": "tenant-b", "message": "Where is my order?"}),
        ("GET", "/agent/00000000-0000-0000-0000-000000000001?tenant_id=tenant-b", None),
        (
            "POST",
            "/agent/00000000-0000-0000-0000-000000000001/decision",
            {"tenant_id": "tenant-b", "decision": "approve"},
        ),
    ],
)
def test_sensitive_routes_reject_other_tenant(method, path, body):
    app.dependency_overrides[get_current_principal] = lambda: Principal("user-123", "tenant-a")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_embedder] = lambda: object()
    app.dependency_overrides[get_vector_store] = lambda: object()
    app.dependency_overrides[get_checkpointer] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.request(method, path, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_nonlocal_settings_require_authentication():
    with pytest.raises(ValueError, match="AUTH_ENABLED"):
        Settings(_env_file=None, app_env="production", auth_enabled=False)


def test_cognito_trigger_adds_only_trusted_access_token_tenant_claim():
    event = {
        "version": "2",
        "request": {"userAttributes": {"custom:tenant_id": "tenant-a"}},
        "response": {"claimsAndScopeOverrideDetails": []},
    }

    result = lambda_handler(event, None)

    assert result["response"]["claimsAndScopeOverrideDetails"] == {
        "accessTokenGeneration": {"claimsToAddOrOverride": {"tenant_id": "tenant-a"}}
    }


@pytest.mark.parametrize(
    "event",
    [
        {"version": "1", "request": {"userAttributes": {"custom:tenant_id": "tenant-a"}}},
        {"version": "2", "request": {"userAttributes": {}}},
        {"version": "2", "request": {"userAttributes": {"custom:tenant_id": "bad tenant"}}},
    ],
)
def test_cognito_trigger_fails_closed_for_untrusted_tenant_state(event):
    with pytest.raises(ValueError):
        lambda_handler(event, None)
