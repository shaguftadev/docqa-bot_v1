"""Cognito Hosted UI authorization-code flow with PKCE for Streamlit."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

_pending_oauth: dict[str, tuple[str, float]] = {}
_pending_oauth_lock = threading.Lock()


class CognitoLoginError(RuntimeError):
    """Safe-to-display Cognito sign-in error."""


@dataclass(frozen=True)
class CognitoUiConfig:
    domain: str
    client_id: str
    redirect_uri: str
    logout_uri: str
    scopes: tuple[str, ...] = ("openid", "email", "support/approve")

    @classmethod
    def from_environment(cls, environ: dict[str, str]) -> CognitoUiConfig | None:
        values = (
            environ.get("SUPPORTPILOT_COGNITO_DOMAIN", "").strip().rstrip("/"),
            environ.get("SUPPORTPILOT_COGNITO_CLIENT_ID", "").strip(),
            environ.get("SUPPORTPILOT_COGNITO_REDIRECT_URI", "").strip(),
            environ.get("SUPPORTPILOT_COGNITO_LOGOUT_URI", "").strip(),
        )
        if not values[0] and not values[1]:
            return None
        if not all(values):
            raise CognitoLoginError("Cognito UI requires domain, client ID, callback URL, and logout URL")
        if not values[0].startswith("https://"):
            raise CognitoLoginError("The Cognito Hosted UI domain must use HTTPS")
        scopes = tuple(environ.get(
            "SUPPORTPILOT_COGNITO_SCOPES", "openid email support/approve"
        ).split())
        if "openid" not in scopes:
            raise CognitoLoginError("Cognito sign-in scopes must include openid")
        return cls(*values, scopes=scopes)

    def authorization_url(self, state: str, verifier: str) -> str:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = urlencode({
            "client_id": self.client_id,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "redirect_uri": self.redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        return f"{self.domain}/oauth2/authorize?{query}"

    def logout_url(self) -> str:
        query = urlencode({"client_id": self.client_id, "logout_uri": self.logout_uri})
        return f"{self.domain}/logout?{query}"

    @property
    def token_endpoint(self) -> str:
        return f"{self.domain}/oauth2/token"


def new_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def register_pkce_transaction(state: str, verifier: str) -> None:
    """Keep the verifier server-side across the browser's Hosted UI round trip."""
    now = time.time()
    with _pending_oauth_lock:
        for old_state, (_, expires_at) in list(_pending_oauth.items()):
            if expires_at <= now:
                _pending_oauth.pop(old_state, None)
        if len(_pending_oauth) >= 1024:
            oldest = min(_pending_oauth, key=lambda key: _pending_oauth[key][1])
            _pending_oauth.pop(oldest, None)
        _pending_oauth[state] = (verifier, now + 600)


def consume_pkce_verifier(state: str) -> str | None:
    """Return and remove a non-expired, single-use PKCE verifier."""
    with _pending_oauth_lock:
        pending = _pending_oauth.pop(state, None)
    if pending is None or pending[1] <= time.time():
        return None
    return pending[0]


def _token_request(config: CognitoUiConfig, data: dict[str, str]) -> dict:
    try:
        response = httpx.post(
            config.token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
            trust_env=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CognitoLoginError("Cognito sign-in failed. Check the user-pool app client and callback configuration.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise CognitoLoginError("Cognito did not return an access token")
    return payload


def exchange_code(config: CognitoUiConfig, code: str, verifier: str) -> dict:
    tokens = _token_request(config, {
        "grant_type": "authorization_code",
        "client_id": config.client_id,
        "code": code,
        "redirect_uri": config.redirect_uri,
        "code_verifier": verifier,
    })
    tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600))
    return tokens


def refresh_tokens(config: CognitoUiConfig, refresh_token: str) -> dict:
    tokens = _token_request(config, {
        "grant_type": "refresh_token",
        "client_id": config.client_id,
        "refresh_token": refresh_token,
    })
    tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600))
    # Cognito normally does not return a refresh token unless rotation is enabled.
    tokens.setdefault("refresh_token", refresh_token)
    return tokens


def valid_token_set(tokens: dict | None) -> bool:
    return bool(tokens and tokens.get("access_token") and float(tokens.get("expires_at", 0)) > time.time() + 60)
