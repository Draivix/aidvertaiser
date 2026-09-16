"""Meta Ads Conversion Management Tools.

This module provides MCP tools for managing Meta Ads conversions including:
- Pixel management (create, list, get, update)
- Custom conversions (CRUD)
- Conversions API (CAPI) - server-side event sending
- Offline conversion management
"""

import json
import time
import hashlib
from typing import Any, Optional, List, Dict

from ..server import mcp
from .client import (
    make_api_request,
    meta_api_tool,
    ensure_account_prefix,
    resolve_account_id,
)


def _hash_user_data(value: str) -> str:
    """SHA-256 hash user data for Meta CAPI (normalize + lowercase + hash)."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


# ── Pixel Management ──


@mcp.tool()
@meta_api_tool
async def meta_list_pixels(
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Lists all Meta Pixels for an ad account.

    A Meta Pixel is a piece of JavaScript code that tracks visitor
    activity on your website. Each account can have multiple pixels.

    Args:
        account_id: Meta Ads account ID. Uses default if not provided.
        access_token: Meta API access token.

    Returns:
        Dictionary with pixel data including id, name, code,
        last_fired_time, and is_unavailable status.
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {"error": {"message": "account_id is required"}}
    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}/adspixels"
    params = {
        "fields": "id,name,code,last_fired_time,is_unavailable,creation_time,data_use_setting,is_created_by_business",
    }
    return await make_api_request(endpoint, access_token, params)


@mcp.tool()
@meta_api_tool
async def meta_create_pixel(
    name: str,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Creates a new Meta Pixel for an ad account.

    A Meta Pixel tracks visitor activity on your website. Most accounts
    only need one pixel. The pixel JavaScript code is returned in the
    response's 'code' field from meta_get_pixel after creation.

    Note: Pixels cannot be deleted via the API, only shared/unshared.

    Args:
        name: Name for the pixel (e.g., "My Website Pixel").
        account_id: Meta Ads account ID. Uses default if not provided.
        access_token: Meta API access token.

    Returns:
        Dictionary with the created pixel's ID.
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {"error": {"message": "account_id is required"}}
    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}/adspixels"
    params = {"name": name}
    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_update_pixel(
    pixel_id: str,
    access_token: Optional[str] = None,
    name: Optional[str] = None,
    enable_automatic_matching: Optional[bool] = None,
    automatic_matching_fields: Optional[List[str]] = None,
    data_use_setting: Optional[str] = None,
    first_party_cookie_status: Optional[str] = None,
) -> dict:
    """Updates a Meta Pixel's settings.

    Args:
        pixel_id: The Meta Pixel ID to update.
        access_token: Meta API access token.
        name: New pixel name.
        enable_automatic_matching: Enable/disable Advanced Matching,
            which auto-detects user data on your site for better attribution.
        automatic_matching_fields: Fields for Advanced Matching. Options:
            em (email), ph (phone), fn (first name), ln (last name),
            ct (city), st (state), zp (zip), country, db (date of birth),
            ge (gender), external_id.
        data_use_setting: How collected data can be used. Options:
            - ADVERTISING_AND_ANALYTICS (default)
            - ANALYTICS_ONLY
        first_party_cookie_status: First-party cookie setting. Options:
            - FIRST_PARTY_COOKIE_ENABLED (default)
            - FIRST_PARTY_COOKIE_DISABLED

    Returns:
        Dictionary with success status.
    """
    params = {}
    if name is not None:
        params["name"] = name
    if enable_automatic_matching is not None:
        params["enable_automatic_matching"] = str(enable_automatic_matching).lower()
    if automatic_matching_fields is not None:
        params["automatic_matching_fields"] = json.dumps(automatic_matching_fields)
    if data_use_setting is not None:
        params["data_use_setting"] = data_use_setting
    if first_party_cookie_status is not None:
        params["first_party_cookie_status"] = first_party_cookie_status

    if not params:
        return {"error": {"message": "No update parameters provided"}}

    endpoint = f"{pixel_id}"
    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_get_pixel(
    pixel_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Gets detailed information about a specific Meta Pixel.

    Args:
        pixel_id: The Meta Pixel ID.
        access_token: Meta API access token.

    Returns:
        Dictionary with pixel details and recent event statistics.
    """
    endpoint = f"{pixel_id}"
    params = {
        "fields": "id,name,code,last_fired_time,is_unavailable,creation_time,data_use_setting",
    }
    return await make_api_request(endpoint, access_token, params)


@mcp.tool()
@meta_api_tool
async def meta_get_pixel_stats(
    pixel_id: str,
    access_token: Optional[str] = None,
    aggregation: str = "event",
) -> dict:
    """Gets event statistics for a Meta Pixel.

    Shows which events the pixel is receiving and their counts,
    useful for verifying tracking is working correctly.

    Args:
        pixel_id: The Meta Pixel ID.
        access_token: Meta API access token.
        aggregation: How to aggregate stats. Options:
            - "event": Group by event name (default)
            - "domain": Group by domain
            - "device_type": Group by device

    Returns:
        Dictionary with event statistics including counts per event type.
    """
    endpoint = f"{pixel_id}/stats"
    params = {"aggregation": aggregation}
    return await make_api_request(endpoint, access_token, params)


# ── Custom Conversions ──


@mcp.tool()
@meta_api_tool
async def meta_list_custom_conversions(
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Lists all custom conversions for an ad account.

    Custom conversions let you create conversion rules based on
    URL patterns or event parameters without modifying pixel code.

    Args:
        account_id: Meta Ads account ID. Uses default if not provided.
        access_token: Meta API access token.

    Returns:
        Dictionary with custom conversion data including rules,
        pixel associations, and last_fired_time.
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {"error": {"message": "account_id is required"}}
    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}/customconversions"
    params = {
        "fields": "id,name,description,pixel,rule,default_conversion_value,custom_event_type,event_source_type,first_fired_time,last_fired_time,is_archived,retention_days,creation_time",
    }
    return await make_api_request(endpoint, access_token, params)


@mcp.tool()
@meta_api_tool
async def meta_get_custom_conversion(
    custom_conversion_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Gets detailed information about a specific custom conversion.

    Args:
        custom_conversion_id: The custom conversion ID.
        access_token: Meta API access token.

    Returns:
        Dictionary with custom conversion details including rule,
        pixel info, and activity data.
    """
    endpoint = f"{custom_conversion_id}"
    params = {
        "fields": "id,name,description,pixel,rule,default_conversion_value,custom_event_type,event_source_type,first_fired_time,last_fired_time,is_archived,retention_days,creation_time",
    }
    return await make_api_request(endpoint, access_token, params)


@mcp.tool()
@meta_api_tool
async def meta_create_custom_conversion(
    name: str,
    pixel_id: str,
    rule: str,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    custom_event_type: str = "OTHER",
    default_conversion_value: Optional[float] = None,
    description: Optional[str] = None,
) -> dict:
    """Creates a new custom conversion rule.

    Custom conversions let you track specific actions without modifying
    your pixel code. Define rules based on URLs or event parameters.

    Args:
        name: Custom conversion name (e.g., "Thank You Page Visit").
        pixel_id: Meta Pixel ID to associate with.
        rule: JSON rule string defining when conversion fires. Examples:
            - URL contains: '{"and":[{"url":{"i_contains":"thank-you"}}]}'
            - URL equals: '{"and":[{"url":{"eq":"https://example.com/thanks"}}]}'
            - Event + URL: '{"and":[{"event":{"eq":"Purchase"}},{"url":{"i_contains":"checkout"}}]}'
        account_id: Meta Ads account ID. Uses default if not provided.
        access_token: Meta API access token.
        custom_event_type: Event type. Options:
            - ADD_PAYMENT_INFO, ADD_TO_CART, ADD_TO_WISHLIST,
              COMPLETE_REGISTRATION, CONTACT, CUSTOMIZE_PRODUCT,
              DONATE, FIND_LOCATION, INITIATED_CHECKOUT, LEAD,
              LISTING_INTERACTION, OTHER, PURCHASE, SCHEDULE,
              SEARCH, START_TRIAL, SUBMIT_APPLICATION, SUBSCRIBE
        default_conversion_value: Default monetary value per conversion.
        description: Optional description.

    Returns:
        Dictionary with created custom conversion ID.
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {"error": {"message": "account_id is required"}}
    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}/customconversions"
    params = {
        "name": name,
        "pixel": pixel_id,
        "rule": rule,
        "custom_event_type": custom_event_type,
    }

    if default_conversion_value is not None:
        params["default_conversion_value"] = str(default_conversion_value)
    if description:
        params["description"] = description

    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_update_custom_conversion(
    custom_conversion_id: str,
    access_token: Optional[str] = None,
    name: Optional[str] = None,
    default_conversion_value: Optional[float] = None,
    description: Optional[str] = None,
) -> dict:
    """Updates an existing custom conversion.

    Note: The rule and pixel_id cannot be changed after creation.

    Args:
        custom_conversion_id: The custom conversion ID.
        access_token: Meta API access token.
        name: New name.
        default_conversion_value: New default value.
        description: New description.

    Returns:
        Dictionary with success status.
    """
    params = {}
    if name is not None:
        params["name"] = name
    if default_conversion_value is not None:
        params["default_conversion_value"] = str(default_conversion_value)
    if description is not None:
        params["description"] = description

    if not params:
        return {"error": {"message": "No update parameters provided"}}

    endpoint = f"{custom_conversion_id}"
    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_delete_custom_conversion(
    custom_conversion_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Deletes (archives) a custom conversion.

    Args:
        custom_conversion_id: The custom conversion ID to delete.
        access_token: Meta API access token.

    Returns:
        Dictionary with success status.
    """
    endpoint = f"{custom_conversion_id}"
    return await make_api_request(endpoint, access_token, method="DELETE")


# ── Conversions API (CAPI) - Server-Side Events ──


@mcp.tool()
@meta_api_tool
async def meta_send_conversion_event(
    pixel_id: str,
    event_name: str,
    access_token: Optional[str] = None,
    event_time: Optional[int] = None,
    event_source_url: Optional[str] = None,
    action_source: str = "website",
    user_data: Optional[Dict[str, str]] = None,
    custom_data: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
    opt_out: bool = False,
) -> dict:
    """Sends a server-side conversion event via the Conversions API (CAPI).

    The Conversions API lets you send conversion events directly from
    your server, providing more reliable tracking than browser-based
    pixels (not affected by ad blockers or cookie restrictions).

    Best practice: Send events via both Pixel AND CAPI with matching
    event_id for deduplication.

    Args:
        pixel_id: Meta Pixel ID to send the event to.
        event_name: Standard or custom event name. Standard events:
            - AddPaymentInfo, AddToCart, AddToWishlist,
              CompleteRegistration, Contact, CustomizeProduct,
              Donate, FindLocation, InitiateCheckout, Lead,
              PageView, Purchase, Schedule, Search,
              StartTrial, SubmitApplication, Subscribe, ViewContent
        access_token: Meta API access token.
        event_time: Unix timestamp of the event. Defaults to now.
            Events can be sent up to 7 days after they occurred.
        event_source_url: URL where the event happened.
        action_source: Where the event originated. Options:
            - website (default), app, phone_call, chat,
              physical_store, system_generated, email, other
        user_data: User identification data for matching (auto-hashed):
            - em: Email address
            - ph: Phone number (E.164 format)
            - fn: First name
            - ln: Last name
            - ct: City
            - st: State/province (2-letter code)
            - zp: Zip/postal code
            - country: Country (2-letter ISO code)
            - external_id: Your unique user ID
            - client_ip_address: User's IP address (NOT hashed)
            - client_user_agent: User's browser user agent (NOT hashed)
            - fbc: Facebook click ID cookie (_fbc)
            - fbp: Facebook browser ID cookie (_fbp)
        custom_data: Event-specific data:
            - value: Monetary value (required for Purchase)
            - currency: Currency code (required for Purchase)
            - content_name: Product/content name
            - content_ids: List of product IDs
            - content_type: "product" or "product_group"
            - contents: List of product objects
            - num_items: Number of items
            - order_id: Unique order/transaction ID
            - search_string: Search query
            - status: Registration/subscription status
        event_id: Unique event ID for deduplication with browser pixel.
        opt_out: If True, event is used only for attribution, not targeting.

    Returns:
        Dictionary with events_received count and fbtrace_id for debugging.

    Example:
        >>> await meta_send_conversion_event(
        ...     pixel_id="123456789",
        ...     event_name="Purchase",
        ...     user_data={"em": "user@example.com", "ph": "+420123456789"},
        ...     custom_data={"value": 1500.0, "currency": "CZK", "order_id": "ORD-001"}
        ... )
    """
    if not event_time:
        event_time = int(time.time())

    # Build user_data with hashing
    hashed_user_data = {}
    if user_data:
        # Fields that should be hashed
        hash_fields = {
            "em",
            "ph",
            "fn",
            "ln",
            "ct",
            "st",
            "zp",
            "country",
            "external_id",
        }
        # Fields that should NOT be hashed
        no_hash_fields = {"client_ip_address", "client_user_agent", "fbc", "fbp"}

        for key, value in user_data.items():
            if key in hash_fields and value:
                hashed_user_data[key] = _hash_user_data(value)
            elif key in no_hash_fields and value:
                hashed_user_data[key] = value
            elif value:
                hashed_user_data[key] = value

    event = {
        "event_name": event_name,
        "event_time": event_time,
        "action_source": action_source,
        "user_data": hashed_user_data,
    }

    if event_source_url:
        event["event_source_url"] = event_source_url
    if custom_data:
        event["custom_data"] = custom_data
    if event_id:
        event["event_id"] = event_id
    if opt_out:
        event["opt_out"] = True

    endpoint = f"{pixel_id}/events"
    params = {
        "data": json.dumps([event]),
    }

    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_send_conversion_events_batch(
    pixel_id: str,
    events: List[Dict[str, Any]],
    access_token: Optional[str] = None,
) -> dict:
    """Sends multiple conversion events in a single batch via CAPI.

    More efficient than sending events one by one. Supports up to
    1000 events per batch. Each event follows the same format as
    meta_send_conversion_event.

    Args:
        pixel_id: Meta Pixel ID.
        events: List of event dictionaries. Each must contain:
            - event_name: Standard or custom event name
            - event_time: Unix timestamp (optional, defaults to now)
            - action_source: Where event originated (default: "website")
            - user_data: Dict of user identifiers (auto-hashed)
            - custom_data: Optional event-specific data
            - event_id: Optional deduplication ID
        access_token: Meta API access token.

    Returns:
        Dictionary with events_received count and fbtrace_id.
    """
    now = int(time.time())
    processed_events = []

    for event in events:
        processed = {
            "event_name": event["event_name"],
            "event_time": event.get("event_time", now),
            "action_source": event.get("action_source", "website"),
        }

        # Hash user data
        user_data = event.get("user_data", {})
        hashed = {}
        hash_fields = {
            "em",
            "ph",
            "fn",
            "ln",
            "ct",
            "st",
            "zp",
            "country",
            "external_id",
        }
        no_hash_fields = {"client_ip_address", "client_user_agent", "fbc", "fbp"}

        for key, value in user_data.items():
            if key in hash_fields and value:
                hashed[key] = _hash_user_data(value)
            elif key in no_hash_fields and value:
                hashed[key] = value
            elif value:
                hashed[key] = value

        processed["user_data"] = hashed

        if "event_source_url" in event:
            processed["event_source_url"] = event["event_source_url"]
        if "custom_data" in event:
            processed["custom_data"] = event["custom_data"]
        if "event_id" in event:
            processed["event_id"] = event["event_id"]

        processed_events.append(processed)

    endpoint = f"{pixel_id}/events"
    params = {
        "data": json.dumps(processed_events),
    }

    return await make_api_request(endpoint, access_token, params, method="POST")


# ── Offline Conversions ──


@mcp.tool()
@meta_api_tool
async def meta_list_offline_conversion_sets(
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Lists offline conversion data sets for an ad account.

    Offline conversion data sets are used to upload offline events
    (store visits, phone sales, CRM data) for attribution.

    Args:
        account_id: Meta Ads account ID. Uses default if not provided.
        access_token: Meta API access token.

    Returns:
        Dictionary with offline conversion set data.
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {"error": {"message": "account_id is required"}}
    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}/offline_conversion_data_sets"
    params = {
        "fields": "id,name,description,creation_time,last_upload_app,last_upload_app_changed_time,event_stats,usage,is_restricted_use,auto_assign_to_new_accounts_only",
    }
    return await make_api_request(endpoint, access_token, params)


@mcp.tool()
@meta_api_tool
async def meta_create_offline_conversion_set(
    name: str,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    description: Optional[str] = None,
    auto_assign_to_new_accounts_only: bool = False,
) -> dict:
    """Creates an offline conversion data set.

    Use this to create a container for uploading offline conversion
    events (CRM data, phone sales, in-store purchases).

    Args:
        name: Name for the offline conversion set.
        account_id: Meta Ads account ID. Uses default if not provided.
        access_token: Meta API access token.
        description: Optional description.
        auto_assign_to_new_accounts_only: If True, only auto-assign
            to newly created ad accounts.

    Returns:
        Dictionary with created offline conversion set ID.
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {"error": {"message": "account_id is required"}}
    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}/offline_conversion_data_sets"
    params = {
        "name": name,
        "auto_assign_to_new_accounts_only": str(
            auto_assign_to_new_accounts_only
        ).lower(),
    }
    if description:
        params["description"] = description

    return await make_api_request(endpoint, access_token, params, method="POST")


@mcp.tool()
@meta_api_tool
async def meta_upload_offline_conversions(
    offline_set_id: str,
    events: List[Dict[str, Any]],
    access_token: Optional[str] = None,
) -> dict:
    """Uploads offline conversion events to an offline conversion set.

    Use this to push CRM data (leads that became customers, phone
    call outcomes, in-store purchases) back to Meta for attribution.

    Args:
        offline_set_id: The offline conversion data set ID.
        events: List of offline event records. Each must contain:
            - match_keys: Dict of user identifiers for matching:
                - email: Email address (auto-hashed)
                - phone: Phone number (auto-hashed)
                - fn: First name (auto-hashed)
                - ln: Last name (auto-hashed)
                - extern_id: Your unique customer ID
                - lead_id: Meta lead ad ID (if from lead form)
            - event_name: Event type (e.g., "Purchase", "Lead")
            - event_time: Unix timestamp of the event
            - value: Monetary value
            - currency: Currency code (e.g., "CZK")
            - order_id: Optional unique transaction ID
            - custom_data: Optional additional data dict
        access_token: Meta API access token.

    Returns:
        Dictionary with upload status and any errors.

    Example:
        >>> await meta_upload_offline_conversions(
        ...     offline_set_id="123456789",
        ...     events=[{
        ...         "match_keys": {"email": "customer@example.com"},
        ...         "event_name": "Purchase",
        ...         "event_time": 1706000000,
        ...         "value": 5000,
        ...         "currency": "CZK"
        ...     }]
        ... )
    """
    processed_events = []

    for event in events:
        processed = {
            "event_name": event["event_name"],
            "event_time": event["event_time"],
        }

        # Hash match keys
        match_keys = event.get("match_keys", {})
        hashed_keys = {}
        hash_fields = {"email", "phone", "fn", "ln"}

        for key, value in match_keys.items():
            if key in hash_fields and value:
                hashed_keys[key] = _hash_user_data(value)
            elif value:
                hashed_keys[key] = value

        processed["match_keys"] = hashed_keys

        if "value" in event:
            processed["value"] = event["value"]
        if "currency" in event:
            processed["currency"] = event["currency"]
        if "order_id" in event:
            processed["order_id"] = event["order_id"]
        if "custom_data" in event:
            processed["custom_data"] = event["custom_data"]

        processed_events.append(processed)

    endpoint = f"{offline_set_id}/events"
    params = {
        "upload_tag": f"mcp_upload_{int(time.time())}",
        "data": json.dumps(processed_events),
    }

    return await make_api_request(endpoint, access_token, params, method="POST")
