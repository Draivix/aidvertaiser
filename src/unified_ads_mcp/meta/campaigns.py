"""Meta Ads Campaign Management Tools.

This module provides MCP tools for managing Meta Ads campaigns, including
listing, creating, updating, and retrieving campaign details.
"""

import json
from typing import Optional, List

from ..server import mcp, account_listing_tool
from ..config import only_default_account_enabled
from .client import (
    make_api_request,
    meta_api_tool,
    ensure_account_prefix,
    resolve_account_id,
)

ONLY_DEFAULT_ACCOUNT = only_default_account_enabled()


@account_listing_tool()
@meta_api_tool
async def meta_list_accounts(
    access_token: Optional[str] = None, user_id: str = "me", limit: int = 200
) -> dict:
    """List all Meta Ads accounts accessible by the current user.

    Retrieves ad accounts that the authenticated user has access to,
    including account status, spending, currency, and other metadata.

    Args:
        access_token: Meta API access token (uses cached token if not provided).
        user_id: Meta user ID or "me" for the current user.
        limit: Maximum number of accounts to return (default: 200).

    Returns:
        Dictionary containing:
            - data: List of ad account objects with id, name, status, etc.
            - paging: Pagination information if more results are available.

    Example:
        >>> result = await meta_list_accounts()
        >>> for account in result["data"]:
        ...     print(f"{account['name']}: {account['id']}")
    """
    endpoint = f"{user_id}/adaccounts"
    params = {
        "fields": "id,name,account_id,account_status,amount_spent,balance,currency,age,business_city,business_country_code",
        "limit": limit,
    }

    data = await make_api_request(endpoint, access_token, params)
    return data


@mcp.tool()
@meta_api_tool
async def meta_get_account_info(
    account_id: Optional[str] = None, access_token: Optional[str] = None
) -> dict:
    """Get detailed information about a specific Meta Ads account.

    Retrieves comprehensive account details including status, spending,
    timezone, and DSA compliance requirements for European accounts.

    Args:
        account_id: Meta Ads account ID (format: act_XXXXXXXXX or just the number).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing account details:
            - id: Full account ID with act_ prefix
            - name: Account name
            - account_status: Current status (1=ACTIVE, 2=DISABLED, etc.)
            - amount_spent: Total amount spent
            - balance: Current balance
            - currency: Account currency code
            - timezone_name: Account timezone
            - dsa_required: Boolean indicating if DSA compliance is needed
            - dsa_compliance_note: DSA compliance information

    Example:
        >>> info = await meta_get_account_info("act_123456789")
        >>> print(f"Account: {info['name']}, Currency: {info['currency']}")
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        details = "Please specify an account_id parameter or configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
        if ONLY_DEFAULT_ACCOUNT:
            details = "ONLY_DEFAULT_ACCOUNT is set; configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
        return {
            "error": {
                "message": "Account ID is required",
                "details": details,
                "example": "Use account_id='act_123456789' or account_id='123456789'",
            }
        }

    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}"
    params = {
        "fields": "id,name,account_id,account_status,amount_spent,balance,currency,age,business_city,business_country_code,timezone_name"
    }

    data = await make_api_request(endpoint, access_token, params)

    # Check for errors
    if "error" in data:
        if not ONLY_DEFAULT_ACCOUNT and (
            "access" in str(data.get("error", {})).lower()
            or "permission" in str(data.get("error", {})).lower()
        ):
            # Get accessible accounts for helpful error message
            accessible = await make_api_request(
                "me/adaccounts", access_token, {"fields": "id,name", "limit": 10}
            )
            if "data" in accessible:
                return {
                    "error": {
                        "message": f"Account {account_id} is not accessible",
                        "accessible_accounts": [
                            {"id": a["id"], "name": a["name"]}
                            for a in accessible["data"][:10]
                        ],
                        "suggestion": "Try using one of the accessible account IDs listed above",
                    }
                }
        return data

    # Add DSA requirement detection for European accounts
    if "business_country_code" in data:
        european_countries = [
            "DE",
            "FR",
            "IT",
            "ES",
            "NL",
            "BE",
            "AT",
            "IE",
            "DK",
            "SE",
            "FI",
            "NO",
            "PL",
            "CZ",
        ]
        if data["business_country_code"] in european_countries:
            data["dsa_required"] = True
            data["dsa_compliance_note"] = (
                "This account is subject to European DSA requirements"
            )
        else:
            data["dsa_required"] = False
            data["dsa_compliance_note"] = (
                "This account is not subject to European DSA requirements"
            )

    return data


@mcp.tool()
@meta_api_tool
async def meta_list_campaigns(
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 25,
    after: Optional[str] = None,
) -> dict:
    """List campaigns for a Meta Ads account with optional filtering.

    Retrieves campaigns with their configuration including objectives,
    budgets, bid strategies, and status information.

    Args:
        account_id: Meta Ads account ID (format: act_XXXXXXXXX).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).
        status: Filter by effective status (e.g., 'ACTIVE', 'PAUSED', 'ARCHIVED').
        limit: Maximum number of campaigns to return (default: 25).
        after: Pagination cursor for next page of results.

    Returns:
        Dictionary containing:
            - data: List of campaign objects with id, name, objective, status, etc.
            - paging: Pagination cursors for navigating results.

    Example:
        >>> campaigns = await meta_list_campaigns("act_123456789", status="ACTIVE")
        >>> for campaign in campaigns["data"]:
        ...     print(f"{campaign['name']}: {campaign['objective']}")
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }

    account_id = ensure_account_prefix(account_id)

    endpoint = f"{account_id}/campaigns"
    params = {
        "fields": "id,name,objective,status,daily_budget,lifetime_budget,buying_type,start_time,stop_time,created_time,updated_time,bid_strategy,effective_status,special_ad_categories",
        "limit": limit,
    }

    if status:
        params["effective_status"] = json.dumps([status])

    if after:
        params["after"] = after

    data = await make_api_request(endpoint, access_token, params)
    return data


@mcp.tool()
@meta_api_tool
async def meta_get_campaign_details(
    campaign_id: str, access_token: Optional[str] = None
) -> dict:
    """Get detailed information about a specific campaign.

    Retrieves comprehensive campaign details including objectives,
    budgets, bid strategy, special ad categories, and timing information.

    Args:
        campaign_id: Meta Ads campaign ID.
        access_token: Meta API access token (uses cached token if not provided).

    Returns:
        Dictionary containing campaign details:
            - id: Campaign ID
            - name: Campaign name
            - objective: Campaign objective (e.g., OUTCOME_LEADS)
            - status: Campaign status
            - daily_budget/lifetime_budget: Budget configuration
            - bid_strategy: Bidding strategy
            - special_ad_categories: List of special categories
            - start_time/stop_time: Campaign schedule
            - created_time/updated_time: Timestamps

    Example:
        >>> details = await meta_get_campaign_details("23842588888640185")
        >>> print(f"Objective: {details['objective']}, Budget: {details.get('daily_budget')}")
    """
    if not campaign_id:
        return {"error": {"message": "campaign_id is required"}}

    endpoint = f"{campaign_id}"
    params = {
        "fields": "id,name,objective,status,daily_budget,lifetime_budget,buying_type,start_time,stop_time,created_time,updated_time,bid_strategy,special_ad_categories,special_ad_category_country,budget_remaining,configured_status,effective_status"
    }

    data = await make_api_request(endpoint, access_token, params)
    return data


@mcp.tool()
@meta_api_tool
async def meta_create_campaign(
    name: str,
    objective: str,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    status: str = "PAUSED",
    daily_budget: Optional[int] = None,
    lifetime_budget: Optional[int] = None,
    special_ad_categories: Optional[List[str]] = None,
    buying_type: Optional[str] = None,
    bid_strategy: Optional[str] = None,
    spend_cap: Optional[int] = None,
) -> dict:
    """Create a new campaign in a Meta Ads account.

    Creates a campaign with the specified configuration. New campaigns
    are created in PAUSED status by default for review before activation.

    Args:
        name: Campaign name (required).
        objective: Campaign objective (required). Must be one of:
            - OUTCOME_AWARENESS: Brand awareness and reach
            - OUTCOME_TRAFFIC: Drive traffic to a destination
            - OUTCOME_ENGAGEMENT: Get more engagement
            - OUTCOME_LEADS: Generate leads
            - OUTCOME_SALES: Drive conversions/sales
            - OUTCOME_APP_PROMOTION: App installs
        account_id: Meta Ads account ID (format: act_XXXXXXXXX).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).
        status: Initial status (default: PAUSED). Options: ACTIVE, PAUSED.
        daily_budget: Daily budget in cents (e.g., 1000 = $10.00).
        lifetime_budget: Lifetime budget in cents.
        special_ad_categories: List of special categories if applicable
            (e.g., ['HOUSING', 'EMPLOYMENT', 'CREDIT']).
        buying_type: Buying type (e.g., 'AUCTION').
        bid_strategy: Bid strategy. Options:
            - LOWEST_COST_WITHOUT_CAP
            - LOWEST_COST_WITH_BID_CAP
            - COST_CAP
            - LOWEST_COST_WITH_MIN_ROAS
        spend_cap: Campaign spending limit in cents.

    Returns:
        Dictionary containing:
            - id: Created campaign ID
            - success: True if created successfully

    Example:
        >>> result = await meta_create_campaign(
        ...     account_id="act_123456789",
        ...     name="Summer Sale 2025",
        ...     objective="OUTCOME_SALES",
        ...     daily_budget=5000  # $50/day
        ... )
        >>> print(f"Created campaign: {result['id']}")
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }
    if not name:
        return {"error": {"message": "name is required"}}
    if not objective:
        return {"error": {"message": "objective is required"}}

    account_id = ensure_account_prefix(account_id)

    # Special ad categories defaults to empty list
    if special_ad_categories is None:
        special_ad_categories = []

    # Set default budget if none provided
    if not daily_budget and not lifetime_budget:
        daily_budget = 1000  # Default $10/day

    endpoint = f"{account_id}/campaigns"

    params = {
        "name": name,
        "objective": objective,
        "status": status,
        "special_ad_categories": json.dumps(special_ad_categories),
    }

    if daily_budget is not None:
        params["daily_budget"] = str(daily_budget)

    if lifetime_budget is not None:
        params["lifetime_budget"] = str(lifetime_budget)

    if buying_type:
        params["buying_type"] = buying_type

    if bid_strategy:
        params["bid_strategy"] = bid_strategy

    if spend_cap is not None:
        params["spend_cap"] = str(spend_cap)

    try:
        data = await make_api_request(endpoint, access_token, params, method="POST")
        return data
    except Exception as e:
        return {"error": {"message": "Failed to create campaign", "details": str(e)}}


@mcp.tool()
@meta_api_tool
async def meta_update_campaign(
    campaign_id: str,
    access_token: Optional[str] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    daily_budget: Optional[int] = None,
    lifetime_budget: Optional[int] = None,
    bid_strategy: Optional[str] = None,
    spend_cap: Optional[int] = None,
) -> dict:
    """Update an existing campaign's settings.

    Updates specified fields of a campaign. Only provided parameters
    will be updated; others remain unchanged.

    Args:
        campaign_id: Meta Ads campaign ID (required).
        access_token: Meta API access token (uses cached token if not provided).
        name: New campaign name.
        status: New status. Options: ACTIVE, PAUSED, DELETED.
        daily_budget: New daily budget in cents. Set to 0 to remove.
        lifetime_budget: New lifetime budget in cents.
        bid_strategy: New bid strategy.
        spend_cap: New spending limit in cents.

    Returns:
        Dictionary containing:
            - success: True if update was successful

    Example:
        >>> result = await meta_update_campaign(
        ...     campaign_id="23842588888640185",
        ...     status="ACTIVE",
        ...     daily_budget=7500  # Increase to $75/day
        ... )
    """
    if not campaign_id:
        return {"error": {"message": "campaign_id is required"}}

    params = {}

    if name is not None:
        params["name"] = name

    if status is not None:
        params["status"] = status

    if daily_budget is not None:
        params["daily_budget"] = str(daily_budget) if daily_budget > 0 else ""

    if lifetime_budget is not None:
        params["lifetime_budget"] = str(lifetime_budget) if lifetime_budget > 0 else ""

    if bid_strategy is not None:
        params["bid_strategy"] = bid_strategy

    if spend_cap is not None:
        params["spend_cap"] = str(spend_cap)

    if not params:
        return {"error": {"message": "No update parameters provided"}}

    endpoint = f"{campaign_id}"

    try:
        data = await make_api_request(endpoint, access_token, params, method="POST")
        return data
    except Exception as e:
        return {
            "error": {
                "message": f"Failed to update campaign {campaign_id}",
                "details": str(e),
            }
        }
