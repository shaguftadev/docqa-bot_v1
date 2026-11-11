"""Cognito V2 trigger: add tenant claim and admin-group-gated approval scope."""

from __future__ import annotations

import os
import re
from typing import Any

_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
_APPROVAL_SCOPE = os.getenv("COGNITO_APPROVAL_SCOPE", "support/approve").strip()
_REVIEWER_GROUP = os.getenv("COGNITO_REVIEWER_GROUP", "SupportReviewers").strip()


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

    group_config = event.get("request", {}).get("groupConfiguration", {})
    groups = group_config.get("groupsToOverride", []) if isinstance(group_config, dict) else []
    if not isinstance(groups, list):
        groups = []
    scope_key = "scopesToAdd" if _REVIEWER_GROUP in groups else "scopesToSuppress"
    scopes = access_token.get(scope_key)
    if not isinstance(scopes, list):
        scopes = []
        access_token[scope_key] = scopes
    if _APPROVAL_SCOPE not in scopes:
        scopes.append(_APPROVAL_SCOPE)
    return event
