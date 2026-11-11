"""Cognito V2 pre-token trigger: copy an admin-managed tenant attribute to access tokens."""

from __future__ import annotations

import re
from typing import Any

_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Add a trusted ``tenant_id`` claim to the Cognito access token."""
    if event.get("version") != "2":
        raise ValueError("Configure the Cognito pre-token trigger event version as V2_0")

    attributes = event.get("request", {}).get("userAttributes", {})
    tenant_id = attributes.get("custom:tenant_id")
    if not isinstance(tenant_id, str) or not _TENANT_PATTERN.fullmatch(tenant_id):
        raise ValueError("The user must have a valid administrator-assigned custom:tenant_id")

    response = event.setdefault("response", {})
    overrides = response.get("claimsAndScopeOverrideDetails")
    if not isinstance(overrides, dict):
        overrides = {}
        response["claimsAndScopeOverrideDetails"] = overrides

    access_token = overrides.get("accessTokenGeneration")
    if not isinstance(access_token, dict):
        access_token = {}
        overrides["accessTokenGeneration"] = access_token

    claims = access_token.get("claimsToAddOrOverride")
    if not isinstance(claims, dict):
        claims = {}
        access_token["claimsToAddOrOverride"] = claims
    claims["tenant_id"] = tenant_id
    return event
