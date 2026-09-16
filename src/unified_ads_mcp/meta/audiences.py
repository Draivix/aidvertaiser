"""Meta Ads Custom Audience Management Tools.

This module provides MCP tools for managing Meta Ads custom audiences including
listing, creating, updating, deleting custom audiences, creating lookalike
audiences, uploading customer lists, and sharing audiences between accounts.
"""

import hashlib
import json
from typing import Any, Optional, Dict, List

from ..server import mcp
from .client import (
    make_api_request,
    meta_api_tool,
    ensure_account_prefix,
    resolve_account_id,
)


AUDIENCE_FIELDS = (
    "id,name,subtype,approximate_count_lower_bound,"
    "approximate_count_upper_bound,delivery_status,"
    "operation_status,permission_for_actions,time_created,"
    "time_updated,description,rule,retention_days,"
    "lookalike_spec,data_source"
)


@mcp.tool()
@meta_api_tool
async def meta_list_custom_audiences(
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """Lists all custom audiences for a Meta Ads account.

    Returns website custom audiences, engagement audiences, customer lists,
    and lookalike audiences with their pool sizes and status.

    Args:
        account_id: Meta Ads account ID (format: act_XXXXXXXXX or just the number).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).
        limit: Maximum number of audiences to return (default: 100).

    Returns:
        Dictionary containing:
            - data: List of audience objects with:
                - id: Audience ID
                - name: Audience name
                - subtype: Audience type (WEBSITE, ENGAGEMENT, CUSTOM, LOOKALIKE)
                - approximate_count_lower_bound: Lower bound of audience size
                - approximate_count_upper_bound: Upper bound of audience size
                - delivery_status: Delivery status info
                - operation_status: Processing status
                - time_created: Creation timestamp
                - time_updated: Last update timestamp

    Example:
        >>> audiences = await meta_list_custom_audiences()
        >>> for aud in audiences["data"]:
        ...     print(f"{aud['name']} ({aud['subtype']}): ~{aud.get('approximate_count', 'N/A')} users")
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }

    account_id = ensure_account_prefix(account_id)
    endpoint = f"{account_id}/customaudiences"
    params = {
        "fields": AUDIENCE_FIELDS,
        "limit": limit,
    }

    return await make_api_request(endpoint, access_token, params)


@mcp.tool()
@meta_api_tool
async def meta_create_custom_audience(
    name: str,
    subtype: str = "WEBSITE",
    description: Optional[str] = None,
    rule: Optional[Dict[str, Any]] = None,
    retention_days: int = 30,
    pixel_id: Optional[str] = None,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Creates a custom audience in Meta Ads.

    Supports creating website custom audiences (pixel-based with URL rules),
    engagement audiences, and customer list audiences.

    Args:
        name: Name for the audience (e.g., "Pricing Page Visitors 30d").
        subtype: Audience type. Options:
            - WEBSITE: Website visitors (pixel-based, most common)
            - ENGAGEMENT: People who engaged with content
            - CUSTOM: Customer list (for uploading email/phone data)
        description: Optional description for the audience.
        rule: Audience rule definition for WEBSITE/ENGAGEMENT subtypes.
            For WEBSITE audiences, the rule defines which visitors to include.
            Example (visitors to URLs containing "/cenik"):
            {
                "inclusions": {
                    "operator": "or",
                    "rules": [{
                        "event_sources": [{"id": "PIXEL_ID", "type": "pixel"}],
                        "retention_seconds": 2592000,
                        "filter": {
                            "operator": "and",
                            "filters": [{
                                "field": "url",
                                "operator": "i_contains",
                                "value": "/cenik"
                            }]
                        }
                    }]
                }
            }
            If not provided for WEBSITE subtype, captures all visitors.
        retention_days: How many days to retain users (default: 30).
            Used to auto-build the rule if rule is not provided.
        pixel_id: Meta Pixel ID for WEBSITE audiences. Required if rule
            is not provided and subtype is WEBSITE.
        account_id: Meta Ads account ID (format: act_XXXXXXXXX or just the number).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing the created audience:
            - id: New audience ID
            - Other fields from the creation response

    Example:
        >>> # All website visitors, 30 days
        >>> aud = await meta_create_custom_audience(
        ...     name="All Visitors 30d",
        ...     pixel_id="123456789",
        ... )
        >>> # Specific page visitors
        >>> aud = await meta_create_custom_audience(
        ...     name="Pricing Visitors",
        ...     pixel_id="123456789",
        ...     rule={
        ...         "inclusions": {"operator": "or", "rules": [{
        ...             "event_sources": [{"id": "123456789", "type": "pixel"}],
        ...             "retention_seconds": 2592000,
        ...             "filter": {"operator": "and", "filters": [
        ...                 {"field": "url", "operator": "i_contains", "value": "/cenik"}
        ...             ]}
        ...         }]}
        ...     },
        ... )
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }

    account_id = ensure_account_prefix(account_id)
    endpoint = f"{account_id}/customaudiences"

    params: Dict[str, Any] = {
        "name": name,
        "subtype": subtype.upper(),
    }

    if description:
        params["description"] = description

    if subtype.upper() == "WEBSITE":
        if rule:
            params["rule"] = rule
        elif pixel_id:
            # Auto-build an "all visitors" rule with the given retention
            retention_seconds = retention_days * 86400
            params["rule"] = {
                "inclusions": {
                    "operator": "or",
                    "rules": [{
                        "event_sources": [{"id": pixel_id, "type": "pixel"}],
                        "retention_seconds": retention_seconds,
                    }],
                }
            }
        else:
            return {
                "error": {
                    "message": "For WEBSITE audiences, provide either 'rule' or 'pixel_id'"
                }
            }
    elif subtype.upper() == "CUSTOM":
        params["customer_file_source"] = "USER_PROVIDED_ONLY"

    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_create_lookalike_audience(
    name: str,
    origin_audience_id: str,
    country: str = "CZ",
    ratio: float = 0.01,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Creates a lookalike audience based on a source custom audience.

    Finds people similar to your existing audience. Smaller ratios (1%)
    are more similar, larger ratios (up to 10%) reach more people.

    Args:
        name: Name for the lookalike audience (e.g., "LAL 1% - Form Submitters CZ").
        origin_audience_id: ID of the source audience to base the lookalike on.
            The source audience should have at least 100 people.
        country: Two-letter country code for the lookalike audience
            (e.g., "CZ", "SK", "DE", "US"). Default: "CZ".
        ratio: Lookalike audience size as a fraction (0.01 = 1%, 0.10 = 10%).
            Range: 0.01 to 0.20. Default: 0.01 (1% - most similar).
        account_id: Meta Ads account ID (format: act_XXXXXXXXX or just the number).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing the created lookalike audience:
            - id: New audience ID
            - Other fields from the creation response

    Example:
        >>> lal = await meta_create_lookalike_audience(
        ...     name="LAL 1% - Converters CZ",
        ...     origin_audience_id="23851234567890",
        ...     country="CZ",
        ...     ratio=0.01,
        ... )
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }

    account_id = ensure_account_prefix(account_id)
    endpoint = f"{account_id}/customaudiences"

    params: Dict[str, Any] = {
        "name": name,
        "subtype": "LOOKALIKE",
        "origin_audience_id": origin_audience_id,
        "lookalike_spec": {
            "country": country.upper(),
            "ratio": ratio,
            "type": "similarity",
        },
    }

    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_get_custom_audience(
    audience_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Gets detailed information about a specific custom audience.

    Returns audience metadata, rule definition, delivery status,
    approximate size, and data source information.

    Args:
        audience_id: The custom audience ID to retrieve.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing audience details:
            - id: Audience ID
            - name: Audience name
            - subtype: Audience type
            - approximate_count_lower_bound: Lower bound of audience size
            - approximate_count_upper_bound: Upper bound of audience size
            - delivery_status: Delivery status info
            - operation_status: Processing status
            - rule: Rule definition (for WEBSITE audiences)
            - retention_days: Retention period
            - data_source: Data source info

    Example:
        >>> aud = await meta_get_custom_audience("23851234567890")
        >>> print(f"{aud['name']}: ~{aud.get('approximate_count', 'N/A')} users")
    """
    endpoint = str(audience_id)
    params = {"fields": AUDIENCE_FIELDS}

    return await make_api_request(endpoint, access_token, params)


@mcp.tool()
@meta_api_tool
async def meta_update_custom_audience(
    audience_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    rule: Optional[Dict[str, Any]] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Updates an existing custom audience.

    Args:
        audience_id: The custom audience ID to update.
        name: New name for the audience.
        description: New description for the audience.
        rule: New rule definition for WEBSITE audiences.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing the update result:
            - success: True if the update succeeded

    Example:
        >>> result = await meta_update_custom_audience(
        ...     audience_id="23851234567890",
        ...     name="Updated Audience Name",
        ... )
    """
    endpoint = str(audience_id)
    params: Dict[str, Any] = {}

    if name is not None:
        params["name"] = name
    if description is not None:
        params["description"] = description
    if rule is not None:
        params["rule"] = rule

    if not params:
        return {"error": {"message": "No fields to update. Provide at least one field."}}

    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_delete_custom_audience(
    audience_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Deletes a custom audience.

    Warning: This permanently removes the audience. Active ad sets
    using this audience will lose their targeting.

    Args:
        audience_id: The custom audience ID to delete.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing:
            - success: True if deletion succeeded

    Example:
        >>> result = await meta_delete_custom_audience("23851234567890")
        >>> print(f"Deleted: {result.get('success')}")
    """
    endpoint = str(audience_id)
    return await make_api_request(endpoint, access_token, method="DELETE")


@mcp.tool()
@meta_api_tool
async def meta_add_users_to_audience(
    audience_id: str,
    emails: Optional[List[str]] = None,
    phones: Optional[List[str]] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Uploads hashed user data to a Customer List custom audience.

    Email and phone values are automatically normalized and SHA-256 hashed
    before upload, as required by the Meta API.

    Args:
        audience_id: The custom audience ID (must be CUSTOM subtype).
        emails: List of email addresses to upload. Will be lowercased,
            trimmed, and SHA-256 hashed automatically.
        phones: List of phone numbers to upload. Should include country
            code (e.g., "+420123456789"). Will be SHA-256 hashed.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing upload result:
            - audience_id: The audience ID
            - num_received: Number of records received
            - num_invalid_entries: Number of invalid entries
            - session_id: Upload session ID

    Example:
        >>> result = await meta_add_users_to_audience(
        ...     audience_id="23851234567890",
        ...     emails=["user@example.com", "user2@example.com"],
        ... )
    """
    if not emails and not phones:
        return {"error": {"message": "Provide at least one of: emails, phones"}}

    endpoint = f"{audience_id}/users"

    schema: List[str] = []
    data: List[List[str]] = []

    if emails and phones:
        schema = ["EMAIL", "PHONE"]
        max_len = max(len(emails), len(phones))
        for i in range(max_len):
            row = []
            if i < len(emails):
                normalized = emails[i].strip().lower()
                row.append(hashlib.sha256(normalized.encode("utf-8")).hexdigest())
            else:
                row.append("")
            if i < len(phones):
                normalized = phones[i].strip().replace(" ", "").replace("-", "")
                row.append(hashlib.sha256(normalized.encode("utf-8")).hexdigest())
            else:
                row.append("")
            data.append(row)
    elif emails:
        schema = ["EMAIL"]
        for email in emails:
            normalized = email.strip().lower()
            hashed = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            data.append([hashed])
    elif phones:
        schema = ["PHONE"]
        for phone in phones:
            normalized = phone.strip().replace(" ", "").replace("-", "")
            hashed = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            data.append([hashed])

    params: Dict[str, Any] = {
        "payload": {
            "schema": schema,
            "data": data,
        },
    }

    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_share_custom_audience(
    audience_id: str,
    target_account_ids: List[str],
    access_token: Optional[str] = None,
) -> dict:
    """Shares a custom audience with other Meta Ads accounts.

    Allows the target accounts to use this audience for ad targeting
    without having to recreate it.

    Args:
        audience_id: The custom audience ID to share.
        target_account_ids: List of Meta Ads account IDs to share with.
            Can be with or without the "act_" prefix.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing sharing result:
            - success: True if sharing succeeded

    Example:
        >>> result = await meta_share_custom_audience(
        ...     audience_id="23851234567890",
        ...     target_account_ids=["act_987654321"],
        ... )
    """
    endpoint = f"{audience_id}/adaccounts"
    params: Dict[str, Any] = {
        "adaccounts": [ensure_account_prefix(aid) for aid in target_account_ids],
    }

    return await make_api_request(endpoint, access_token, params, method="POST")
