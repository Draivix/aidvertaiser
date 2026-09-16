"""Bing Webmaster Tools HTTP API client.

This module provides a simple HTTP client for the Bing Webmaster Tools API.
Configuration is loaded via BingWebmasterAuth from ~/bing-webmaster.yaml
or the path in BING_WEBMASTER_CREDENTIALS env var.

Configuration (bing-webmaster.yaml):
    api_key: your_bing_webmaster_api_key
    default_site_url: https://yoursite.com  # optional

API Details:
    Base URL: https://ssl.bing.com/webmaster/api.svc/json/
    Auth: ?apikey=API_KEY query parameter
    Responses: wrapped in {"d": ...} envelope
    Dates: ASP.NET format /Date(1399100400000-0700)/
"""

import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from unified_ads_mcp.auth.bing_auth import get_bing_auth

BASE_URL = "https://ssl.bing.com/webmaster/api.svc/json/"

_client: Optional[httpx.Client] = None

# Pattern for ASP.NET date format: /Date(1399100400000)/ or /Date(1399100400000-0700)/
_DATE_PATTERN = re.compile(r"/Date\((\d+)([+-]\d{4})?\)/")


def _get_client() -> httpx.Client:
    """Get or create the HTTP client singleton."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=30.0)
    return _client


def _parse_date(date_str: str) -> str:
    """Convert ASP.NET date format to ISO datetime string.

    ASP.NET dates look like: /Date(1399100400000)/ or /Date(1399100400000-0700)/
    The number is milliseconds since Unix epoch.

    Args:
        date_str: ASP.NET date string.

    Returns:
        ISO 8601 datetime string, or original string if not a date.
    """
    match = _DATE_PATTERN.search(date_str)
    if not match:
        return date_str

    timestamp_ms = int(match.group(1))
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.isoformat()


def _process_response(data: Any) -> Any:
    """Recursively unwrap {"d": ...} envelope and parse ASP.NET dates.

    Args:
        data: Raw response data from the API.

    Returns:
        Processed data with envelope unwrapped and dates parsed.
    """
    # Unwrap {"d": ...} envelope
    if isinstance(data, dict) and "d" in data and len(data) == 1:
        data = data["d"]

    if isinstance(data, dict):
        return {k: _process_response(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_process_response(item) for item in data]
    elif isinstance(data, str) and "/Date(" in data:
        return _parse_date(data)

    return data


def bing_request(
    method: str,
    params: Optional[dict[str, Any]] = None,
    body: Optional[dict[str, Any]] = None,
    http_method: str = "GET",
) -> Any:
    """Make a Bing Webmaster Tools API request.

    Args:
        method: API method name (e.g., "GetUserSites", "GetRankAndTrafficStats").
        params: Query parameters (used for GET requests).
        body: JSON body (used for POST requests).
        http_method: HTTP method - GET or POST (Bing JSON API uses POST for all writes).

    Returns:
        Parsed and unwrapped JSON response.

    Raises:
        httpx.HTTPStatusError: If the API returns an error status code.
        RuntimeError: If the API returns an error in the response body.
    """
    auth = get_bing_auth()
    client = _get_client()

    url = BASE_URL + method

    # Always include API key as query parameter
    query_params: dict[str, Any] = {"apikey": auth.api_key}

    if http_method.upper() == "GET":
        if params:
            query_params.update(params)
        response = client.get(url, params=query_params)
    elif http_method.upper() in ("POST", "PUT", "DELETE"):
        response = client.request(
            http_method.upper(),
            url,
            params=query_params,
            json=body or {},
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    else:
        raise ValueError(f"Unsupported HTTP method: {http_method}")

    response.raise_for_status()

    # Some endpoints return empty responses (204 No Content)
    if response.status_code == 204 or not response.content:
        return None

    data = response.json()

    # Check for error responses
    if isinstance(data, dict) and "ErrorCode" in data:
        error_msg = data.get("Message", "Unknown error")
        error_code = data.get("ErrorCode", -1)
        raise RuntimeError(
            f"Bing Webmaster API error (code {error_code}): {error_msg}"
        )

    result = _process_response(data)
    # FastMCP validates the declared `-> dict` return; Bing list endpoints
    # (GetUserSites, GetRankAndTrafficStats, GetCrawlIssues, GetUrlLinks…)
    # return a bare JSON array and every tool then failed with
    # "structured_content must be a dict or None". Wrap lists once, here.
    if isinstance(result, list):
        return {"result": result}
    return result


def resolve_site_url(site_url: Optional[str] = None) -> str:
    """Resolve site URL from parameter or default config.

    Args:
        site_url: Explicit site URL, or None to use default.

    Returns:
        Resolved site URL.

    Raises:
        ValueError: If no site_url provided and no default configured.
    """
    if site_url is not None:
        return site_url

    auth = get_bing_auth()
    default = auth.default_site_url
    if default is not None:
        return default

    raise ValueError(
        "No site_url provided and no default_site_url configured "
        "in bing-webmaster.yaml."
    )


def reset_client() -> None:
    """Reset client (for testing)."""
    global _client
    if _client:
        _client.close()
    _client = None
