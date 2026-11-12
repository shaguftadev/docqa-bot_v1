from urllib.parse import parse_qs, urlparse

import pytest

from frontend.cognito_login import (
    CognitoLoginError,
    CognitoUiConfig,
    consume_pkce_verifier,
    exchange_code,
    new_oauth_state,
    new_pkce_verifier,
    register_pkce_transaction,
    refresh_tokens,
)


def test_blank_ui_settings_keep_local_manual_token_mode():
    config = CognitoUiConfig.from_environment({
        "SUPPORTPILOT_COGNITO_REDIRECT_URI": "http://localhost:8501",
        "SUPPORTPILOT_COGNITO_LOGOUT_URI": "http://localhost:8501",
    })

    assert config is None


def test_hosted_ui_authorization_uses_code_flow_and_pkce():
    config = CognitoUiConfig(
        "https://example.auth.us-east-1.amazoncognito.com",
        "public-client",
        "http://localhost:8501",
        "http://localhost:8501",
    )
    state = new_oauth_state()
    verifier = new_pkce_verifier()
    url = config.authorization_url(state, verifier)
    query = parse_qs(urlparse(url).query)

    assert urlparse(url).path == "/oauth2/authorize"
    assert query["response_type"] == ["code"]
    assert query["state"] == [state]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) == 43
    assert "client_secret" not in query


def test_partial_hosted_ui_configuration_fails_closed():
    with pytest.raises(CognitoLoginError, match="requires domain"):
        CognitoUiConfig.from_environment({"SUPPORTPILOT_COGNITO_CLIENT_ID": "client"})


def test_sign_out_url_uses_registered_client_and_logout_uri():
    config = CognitoUiConfig(
        "https://example.auth.us-east-1.amazoncognito.com",
        "public-client",
        "http://localhost:8501",
        "http://localhost:8501",
    )
    query = parse_qs(urlparse(config.logout_url()).query)

    assert urlparse(config.logout_url()).path == "/logout"
    assert query == {"client_id": ["public-client"], "logout_uri": ["http://localhost:8501"]}


def test_pkce_verifier_is_server_side_and_single_use():
    state = new_oauth_state()
    verifier = new_pkce_verifier()
    register_pkce_transaction(state, verifier)

    assert consume_pkce_verifier(state) == verifier
    assert consume_pkce_verifier(state) is None


def test_code_exchange_and_refresh_keep_session_refresh_token(monkeypatch):
    config = CognitoUiConfig(
        "https://example.auth.us-east-1.amazoncognito.com",
        "public-client",
        "http://localhost:8501",
        "http://localhost:8501",
    )

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "new-access", "expires_in": 3600}

    monkeypatch.setattr("frontend.cognito_login.httpx.post", lambda *args, **kwargs: Response())
    exchanged = exchange_code(config, "auth-code", "pkce-verifier")
    refreshed = refresh_tokens(config, "existing-refresh")

    assert exchanged["access_token"] == "new-access"
    assert exchanged["expires_at"] > 0
    assert refreshed["refresh_token"] == "existing-refresh"


def test_confidential_client_secret_is_sent_only_as_basic_auth(monkeypatch):
    config = CognitoUiConfig(
        "https://example.auth.us-east-1.amazoncognito.com",
        "confidential-client",
        "http://localhost:8501",
        "http://localhost:8501",
        client_secret="local-test-secret",
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "access", "expires_in": 3600}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("frontend.cognito_login.httpx.post", fake_post)
    exchange_code(config, "code", "verifier")

    assert captured["auth"] == ("confidential-client", "local-test-secret")
    assert "local-test-secret" not in captured["data"].values()
