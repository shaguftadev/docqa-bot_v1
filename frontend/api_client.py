"""Small HTTP client for the local SupportPilot FastAPI service."""

from typing import Any

import httpx


class ApiError(RuntimeError):
    pass


def request_json(
    api_base_url: str,
    method: str,
    path: str,
    *,
    timeout: float = 45.0,
    **kwargs,
) -> Any:
    url = f"{api_base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.request(method, url, **kwargs)
    except httpx.ConnectError as exc:
        raise ApiError(f"Cannot reach SupportPilot API at {api_base_url}. Start the API and retry.") from exc
    except httpx.TimeoutException as exc:
        raise ApiError("The API request timed out. Check API logs and try again.") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text[:1000] or "The API returned an empty response."}
    if response.is_error:
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        raise ApiError(f"API returned HTTP {response.status_code}: {detail}")
    return payload
