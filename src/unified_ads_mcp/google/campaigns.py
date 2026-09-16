"""Campaign management tools for Google Ads API.

This module provides MCP tools for managing Google Ads campaigns including
listing, creating, updating, and deleting campaigns.
"""

import time
from typing import Any, Optional

from google.ads.googleads.errors import GoogleAdsException
from mcp.server.fastmcp.exceptions import ToolError

from ..server import mcp, account_listing_tool
from .client import (
    get_google_ads_client,
    format_error,
    resolve_customer_id,
    get_enum_name,
    get_enum_value,
    micros_to_currency,
    currency_to_micros,
)


def _get_campaign_bidding_strategy_type(
    client: Any,
    customer_id: str,
    campaign_id: str,
) -> str:
    """Read the campaign's current bidding_strategy_type as an enum name."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign.bidding_strategy_type
        FROM campaign
        WHERE campaign.id = {campaign_id}
        LIMIT 1
    """
    response = ga_service.search_stream(
        customer_id=customer_id,
        query=query,
    )
    for batch in response:
        for row in batch.results:
            return get_enum_name(
                client,
                "BiddingStrategyTypeEnum",
                row.campaign.bidding_strategy_type,
            )
    raise ToolError(f"Campaign {campaign_id} not found")


def _verify_network_settings(
    client: Any,
    customer_id: str,
    campaign_id: str,
) -> dict[str, bool]:
    """Read back campaign network_settings from the API to verify mutations."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            campaign.network_settings.target_google_search,
            campaign.network_settings.target_search_network,
            campaign.network_settings.target_content_network,
            campaign.network_settings.target_partner_search_network
        FROM campaign
        WHERE campaign.id = {campaign_id}
        LIMIT 1
    """
    response = ga_service.search_stream(
        customer_id=customer_id,
        query=query,
    )
    for batch in response:
        for row in batch.results:
            ns = row.campaign.network_settings
            return {
                "target_google_search": ns.target_google_search,
                "target_search_network": ns.target_search_network,
                "target_content_network": ns.target_content_network,
                "target_partner_search_network": ns.target_partner_search_network,
            }
    raise ToolError(f"Campaign {campaign_id} not found during verification")


def _mutate_network_settings(
    client: Any,
    customer_id: str,
    campaign_id: str,
    target_content_network: Optional[bool] = None,
    target_search_network: Optional[bool] = None,
    target_partner_search_network: Optional[bool] = None,
) -> str:
    """Send a focused network_settings mutation and return the resource name."""
    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("CampaignOperation")
    campaign = operation.update
    campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

    # Read current network_settings first so we can set ALL fields
    # (sending partial network_settings can cause Google to reset others)
    current = _verify_network_settings(client, customer_id, campaign_id)

    # Apply all network_settings fields — use new value if provided, else current
    campaign.network_settings.target_google_search = current["target_google_search"]
    campaign.network_settings.target_search_network = (
        target_search_network if target_search_network is not None
        else current["target_search_network"]
    )
    campaign.network_settings.target_content_network = (
        target_content_network if target_content_network is not None
        else current["target_content_network"]
    )
    campaign.network_settings.target_partner_search_network = (
        target_partner_search_network if target_partner_search_network is not None
        else current["target_partner_search_network"]
    )

    # Include ALL network_settings fields in the mask
    operation.update_mask.paths.extend([
        "network_settings.target_google_search",
        "network_settings.target_search_network",
        "network_settings.target_content_network",
        "network_settings.target_partner_search_network",
    ])

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[operation],
    )
    return response.results[0].resource_name


@account_listing_tool()
def google_list_accounts() -> list[dict[str, Any]]:
    """Lists all Google Ads customer accounts accessible by the authenticated user.

    These accounts can be used as customer_id or login_customer_id parameters
    in other Google Ads tools.

    Returns:
        list[dict]: List of accessible accounts with id field.

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client()
        customer_service = client.get_service("CustomerService")
        accounts = customer_service.list_accessible_customers().resource_names

        return [{"id": account.split("/")[-1]} for account in accounts]
    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_list_campaigns(
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists campaigns for a Google Ads customer with performance metrics.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        status: Optional filter by status - ENABLED, PAUSED, or REMOVED.
            If not specified, returns all campaigns.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of campaigns with:
            - id: Campaign ID
            - name: Campaign name
            - status: Campaign status (ENABLED, PAUSED, REMOVED)
            - channel_type: Advertising channel (SEARCH, DISPLAY, etc.)
            - budget: Daily budget in account currency
            - start_date: Campaign start date
            - end_date: Campaign end date
            - impressions: Total impressions
            - clicks: Total clicks
            - cost: Total cost in account currency

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.campaign_budget,
                campaign.start_date,
                campaign.end_date,
                campaign_budget.amount_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros
            FROM campaign
        """

        if status:
            query += f" WHERE campaign.status = '{status.upper()}'"

        query += " ORDER BY campaign.id"

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        campaigns = []
        for batch in response:
            for row in batch.results:
                campaigns.append(
                    {
                        "id": str(row.campaign.id),
                        "name": row.campaign.name,
                        "status": get_enum_name(
                            client, "CampaignStatusEnum", row.campaign.status
                        ),
                        "channel_type": get_enum_name(
                            client,
                            "AdvertisingChannelTypeEnum",
                            row.campaign.advertising_channel_type,
                        ),
                        "budget": micros_to_currency(row.campaign_budget.amount_micros),
                        "start_date": row.campaign.start_date or None,
                        "end_date": row.campaign.end_date or None,
                        "impressions": row.metrics.impressions,
                        "clicks": row.metrics.clicks,
                        "cost": micros_to_currency(row.metrics.cost_micros),
                    }
                )

        return campaigns

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_get_campaign(
    campaign_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Gets detailed information about a specific Google Ads campaign.

    Args:
        campaign_id: The campaign ID to retrieve.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Campaign details including:
            - id: Campaign ID
            - name: Campaign name
            - status: Campaign status
            - channel_type: Advertising channel type
            - channel_sub_type: Advertising channel sub-type
            - budget: Daily budget in account currency
            - budget_delivery_method: Budget delivery method
            - start_date: Campaign start date
            - end_date: Campaign end date
            - target_google_search: Whether targeting Google Search
            - target_search_network: Whether targeting Search Network
            - target_content_network: Whether targeting Display Network
            - impressions: Total impressions
            - clicks: Total clicks
            - cost: Total cost in account currency
            - conversions: Total conversions
            - conversions_value: Total conversion value

    Raises:
        ToolError: If the campaign is not found or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.advertising_channel_sub_type,
                campaign.campaign_budget,
                campaign.start_date,
                campaign.end_date,
                campaign.network_settings.target_google_search,
                campaign.network_settings.target_search_network,
                campaign.network_settings.target_content_network,
                campaign_budget.amount_micros,
                campaign_budget.delivery_method,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        for batch in response:
            for row in batch.results:
                return {
                    "id": str(row.campaign.id),
                    "name": row.campaign.name,
                    "status": get_enum_name(
                        client, "CampaignStatusEnum", row.campaign.status
                    ),
                    "channel_type": get_enum_name(
                        client,
                        "AdvertisingChannelTypeEnum",
                        row.campaign.advertising_channel_type,
                    ),
                    "channel_sub_type": get_enum_name(
                        client,
                        "AdvertisingChannelSubTypeEnum",
                        row.campaign.advertising_channel_sub_type,
                    ),
                    "budget": micros_to_currency(row.campaign_budget.amount_micros),
                    "budget_delivery_method": get_enum_name(
                        client,
                        "BudgetDeliveryMethodEnum",
                        row.campaign_budget.delivery_method,
                    ),
                    "start_date": row.campaign.start_date or None,
                    "end_date": row.campaign.end_date or None,
                    "target_google_search": row.campaign.network_settings.target_google_search,
                    "target_search_network": row.campaign.network_settings.target_search_network,
                    "target_content_network": row.campaign.network_settings.target_content_network,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": micros_to_currency(row.metrics.cost_micros),
                    "conversions": row.metrics.conversions,
                    "conversions_value": row.metrics.conversions_value,
                }

        raise ToolError(f"Campaign {campaign_id} not found")

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_campaign(
    name: str,
    budget: float,
    customer_id: Optional[str] = None,
    channel_type: str = "SEARCH",
    status: str = "PAUSED",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    target_spend: bool = True,
    location_ids: Optional[list[str]] = None,
    language_ids: Optional[list[str]] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a new Google Ads campaign with a daily budget.

    Args:
        name: The campaign name.
        budget: Daily budget in account currency (e.g., 10.00 for $10 USD).
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        channel_type: Advertising channel type. Options:
            - SEARCH: Search Network campaigns
            - DISPLAY: Display Network campaigns
            - SHOPPING: Shopping campaigns
            - VIDEO: YouTube video campaigns
            - PERFORMANCE_MAX: Performance Max campaigns
            - DISCOVERY: Discovery campaigns
            - LOCAL: Local campaigns
            - SMART: Smart campaigns
            - HOTEL: Hotel campaigns
        status: Initial campaign status - ENABLED or PAUSED (default).
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
        target_spend: If True, uses Target Spend bidding to maximize clicks.
        location_ids: Optional list of geo target constant IDs for location targeting.
            Common IDs: "2203" (Czech Republic), "2703" (Slovakia), "2276" (Germany),
            "2840" (United States), "2826" (United Kingdom).
            Without this, ads show worldwide!
        language_ids: Optional list of language criterion IDs.
            Common IDs: "1021" (Czech), "1000" (English), "1001" (German),
            "1033" (Slovak), "1002" (French), "1004" (Italian), "1003" (Spanish),
            "1030" (Polish).
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created campaign details:
            - campaign_id: The new campaign ID
            - campaign_resource_name: Full resource name
            - budget_resource_name: Budget resource name
            - status: Creation status

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        # Create budget first
        campaign_budget_service = client.get_service("CampaignBudgetService")
        campaign_budget_operation = client.get_type("CampaignBudgetOperation")
        campaign_budget = campaign_budget_operation.create
        campaign_budget.name = f"{name} Budget"
        campaign_budget.amount_micros = currency_to_micros(budget)
        campaign_budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        # Performance Max campaigns require non-shared budgets
        if channel_type.upper() == "PERFORMANCE_MAX":
            campaign_budget.explicitly_shared = False

        budget_response = campaign_budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[campaign_budget_operation],
        )
        budget_resource_name = budget_response.results[0].resource_name

        # Create campaign
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.create
        campaign.name = name
        campaign.campaign_budget = budget_resource_name
        campaign.advertising_channel_type = get_enum_value(
            client, "AdvertisingChannelTypeEnum", channel_type
        )
        campaign.status = get_enum_value(client, "CampaignStatusEnum", status)

        # EU accounts require this field
        campaign.contains_eu_political_advertising = get_enum_value(
            client,
            "EuPoliticalAdvertisingStatusEnum",
            "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
        )

        if start_date:
            campaign.start_date = start_date.replace("-", "")
        if end_date:
            campaign.end_date = end_date.replace("-", "")

        # Set bidding strategy based on campaign type
        # Performance Max campaigns require maximize_conversions or maximize_conversion_value
        # target_spend is only valid for Search, Display, and some other campaign types
        if channel_type.upper() == "PERFORMANCE_MAX":
            # Performance Max requires maximize_conversions bidding
            campaign.maximize_conversions.target_cpa_micros = 0
        elif target_spend:
            campaign.target_spend.target_spend_micros = 0  # Maximize clicks

        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation],
        )

        campaign_resource_name = campaign_response.results[0].resource_name
        campaign_id = campaign_resource_name.split("/")[-1]

        # Add location targeting criteria
        if location_ids or language_ids:
            criterion_service = client.get_service("CampaignCriterionService")
            criterion_ops = []

            for loc_id in (location_ids or []):
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.create
                criterion.campaign = campaign_resource_name
                criterion.location.geo_target_constant = f"geoTargetConstants/{loc_id}"
                criterion_ops.append(op)

            for lang_id in (language_ids or []):
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.create
                criterion.campaign = campaign_resource_name
                criterion.language.language_constant = f"languageConstants/{lang_id}"
                criterion_ops.append(op)

            if criterion_ops:
                criterion_service.mutate_campaign_criteria(
                    customer_id=customer_id,
                    operations=criterion_ops,
                )

        return {
            "campaign_id": campaign_id,
            "campaign_resource_name": campaign_resource_name,
            "budget_resource_name": budget_resource_name,
            "locations_set": len(location_ids) if location_ids else 0,
            "languages_set": len(language_ids) if language_ids else 0,
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_pmax_campaign(
    name: str,
    budget: float,
    business_name: str,
    logo_image_data: str,
    customer_id: Optional[str] = None,
    status: str = "PAUSED",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a Performance Max campaign with brand assets atomically.

    This function creates the campaign, budget, business name asset, logo asset,
    and links them all in a single atomic API call. This is required for accounts
    with Brand Guidelines enabled, which mandate BUSINESS_NAME and LOGO assets
    be linked at campaign creation time.

    Args:
        name: The campaign name.
        budget: Daily budget in account currency (e.g., 10.00 for $10 USD).
        business_name: Business name text (required for Brand Guidelines).
        logo_image_data: Base64 encoded square logo image (1:1 ratio, min 128x128,
            recommended 1200x1200). PNG, JPG, or GIF format.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        status: Initial campaign status - ENABLED or PAUSED (default).
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created campaign details:
            - campaign_id: The new campaign ID
            - campaign_resource_name: Full resource name
            - budget_resource_name: Budget resource name
            - business_name_asset_resource_name: Business name asset resource name
            - logo_asset_resource_name: Logo asset resource name
            - status: Creation status

    Raises:
        ToolError: If the API request fails.

    Note:
        After creating the campaign, you need to create an Asset Group with
        headlines, descriptions, and marketing images using google_create_asset_group
        before the campaign can serve ads.
    """
    import base64

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        # Decode logo image
        try:
            logo_bytes = base64.b64decode(logo_image_data)
        except Exception as e:
            raise ToolError(f"Invalid base64 logo image data: {e}")

        # Services
        ga_service = client.get_service("GoogleAdsService")
        campaign_budget_service = client.get_service("CampaignBudgetService")
        campaign_service = client.get_service("CampaignService")
        asset_service = client.get_service("AssetService")

        # Temporary resource IDs for atomic creation
        BUDGET_TEMP_ID = -1
        CAMPAIGN_TEMP_ID = -2
        BUSINESS_NAME_ASSET_TEMP_ID = -3
        LOGO_ASSET_TEMP_ID = -4

        mutate_operations = []

        # 1. Create campaign budget
        budget_op = client.get_type("MutateOperation")
        campaign_budget = budget_op.campaign_budget_operation.create
        campaign_budget.resource_name = campaign_budget_service.campaign_budget_path(
            customer_id, BUDGET_TEMP_ID
        )
        campaign_budget.name = f"{name} Budget"
        campaign_budget.amount_micros = currency_to_micros(budget)
        campaign_budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        campaign_budget.explicitly_shared = False  # Required for P-Max
        mutate_operations.append(budget_op)

        # 2. Create campaign
        campaign_op = client.get_type("MutateOperation")
        campaign = campaign_op.campaign_operation.create
        campaign.resource_name = campaign_service.campaign_path(
            customer_id, CAMPAIGN_TEMP_ID
        )
        campaign.name = name
        campaign.campaign_budget = campaign_budget_service.campaign_budget_path(
            customer_id, BUDGET_TEMP_ID
        )
        campaign.advertising_channel_type = (
            client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
        )
        campaign.status = get_enum_value(client, "CampaignStatusEnum", status)
        # Enable brand guidelines for P-Max with brand assets at campaign level
        campaign.brand_guidelines_enabled = True
        # Performance Max requires maximize_conversions bidding
        campaign.maximize_conversions.target_cpa_micros = 0
        # EU accounts require this field
        campaign.contains_eu_political_advertising = get_enum_value(
            client,
            "EuPoliticalAdvertisingStatusEnum",
            "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
        )
        if start_date:
            campaign.start_date = start_date.replace("-", "")
        if end_date:
            campaign.end_date = end_date.replace("-", "")
        mutate_operations.append(campaign_op)

        # 3. Create business name text asset
        bn_asset_op = client.get_type("MutateOperation")
        bn_asset = bn_asset_op.asset_operation.create
        bn_asset.resource_name = asset_service.asset_path(
            customer_id, BUSINESS_NAME_ASSET_TEMP_ID
        )
        bn_asset.text_asset.text = business_name
        bn_asset.name = f"{name} - Business Name"
        mutate_operations.append(bn_asset_op)

        # 4. Create logo image asset
        logo_asset_op = client.get_type("MutateOperation")
        logo_asset = logo_asset_op.asset_operation.create
        logo_asset.resource_name = asset_service.asset_path(
            customer_id, LOGO_ASSET_TEMP_ID
        )
        logo_asset.image_asset.data = logo_bytes
        logo_asset.name = f"{name} - Logo"
        mutate_operations.append(logo_asset_op)

        # 5. Link business name asset to campaign
        bn_link_op = client.get_type("MutateOperation")
        bn_campaign_asset = bn_link_op.campaign_asset_operation.create
        bn_campaign_asset.campaign = campaign_service.campaign_path(
            customer_id, CAMPAIGN_TEMP_ID
        )
        bn_campaign_asset.asset = asset_service.asset_path(
            customer_id, BUSINESS_NAME_ASSET_TEMP_ID
        )
        bn_campaign_asset.field_type = client.enums.AssetFieldTypeEnum.BUSINESS_NAME
        mutate_operations.append(bn_link_op)

        # 6. Link logo asset to campaign
        logo_link_op = client.get_type("MutateOperation")
        logo_campaign_asset = logo_link_op.campaign_asset_operation.create
        logo_campaign_asset.campaign = campaign_service.campaign_path(
            customer_id, CAMPAIGN_TEMP_ID
        )
        logo_campaign_asset.asset = asset_service.asset_path(
            customer_id, LOGO_ASSET_TEMP_ID
        )
        logo_campaign_asset.field_type = client.enums.AssetFieldTypeEnum.LOGO
        mutate_operations.append(logo_link_op)

        # Execute atomic bulk mutate
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=mutate_operations,
        )

        # Extract resource names from response
        result = {
            "status": "created",
        }

        for op_response in response.mutate_operation_responses:
            if op_response.HasField("campaign_budget_result"):
                result["budget_resource_name"] = (
                    op_response.campaign_budget_result.resource_name
                )
            elif op_response.HasField("campaign_result"):
                result["campaign_resource_name"] = (
                    op_response.campaign_result.resource_name
                )
                result["campaign_id"] = op_response.campaign_result.resource_name.split(
                    "/"
                )[-1]
            elif op_response.HasField("asset_result"):
                resource_name = op_response.asset_result.resource_name
                # We can't easily distinguish which asset is which from the response,
                # but we track the order
                if "business_name_asset_resource_name" not in result:
                    result["business_name_asset_resource_name"] = resource_name
                else:
                    result["logo_asset_resource_name"] = resource_name

        return result

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_update_campaign(
    campaign_id: str,
    customer_id: Optional[str] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    target_content_network: Optional[bool] = None,
    target_search_network: Optional[bool] = None,
    target_partner_search_network: Optional[bool] = None,
    geo_target_type: Optional[str] = None,
    bidding_strategy_type: Optional[str] = None,
    target_cpa_micros: Optional[int] = None,
    target_roas: Optional[float] = None,
    enhanced_cpc: Optional[bool] = None,
    cpc_bid_ceiling_micros: Optional[int] = None,
    target_spend_micros: Optional[int] = None,
    budget_amount_micros: Optional[int] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Updates an existing Google Ads campaign.

    Args:
        campaign_id: The campaign ID to update.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        name: Optional new campaign name.
        status: Optional new status - ENABLED, PAUSED, or REMOVED.
        start_date: Optional new start date in YYYY-MM-DD format.
        end_date: Optional new end date in YYYY-MM-DD format.
        target_content_network: Optional bool to enable/disable Display Network.
            Set to False to disable Display Network (recommended for Search campaigns).
        target_search_network: Optional bool to enable/disable Search Partners.
        target_partner_search_network: Optional bool to enable/disable partner search network.
        geo_target_type: Optional location targeting mode. Options:
            - PRESENCE: Only people physically IN your targeted location (RECOMMENDED)
            - SEARCH_INTEREST: People searching for or interested in your location
            - PRESENCE_OR_INTEREST: Both presence and interest (DEFAULT but NOT recommended —
              this is the #1 source of irrelevant/fraudulent clicks)
        bidding_strategy_type: Optional bidding strategy to set. Options:
            - MAXIMIZE_CLICKS: Maximize clicks within budget
            - MAXIMIZE_CONVERSIONS: Maximize conversions (optionally with target CPA)
            - TARGET_CPA: Target cost per acquisition
            - TARGET_ROAS: Target return on ad spend
            - MANUAL_CPC: Manual CPC bidding (optionally with enhanced CPC)
        target_cpa_micros: Optional target CPA in micros for MAXIMIZE_CONVERSIONS
            or TARGET_CPA strategies (e.g., 5000000 = 5.00 in account currency).
        target_roas: Optional target ROAS for TARGET_ROAS strategy
            (e.g., 2.0 = 200% return on ad spend).
        enhanced_cpc: Optional bool to enable enhanced CPC for MANUAL_CPC strategy.
        cpc_bid_ceiling_micros: Optional max CPC bid ceiling in micros for
            MAXIMIZE_CLICKS (TARGET_SPEND) bidding strategy. CRITICAL for budget
            control — without it, Google can bid very high per click and blow
            the budget quickly. Example: 60000000 = 60.00 in account currency.
            Only valid when the campaign's bidding strategy is (or is being set
            to) MAXIMIZE_CLICKS. Raises ToolError otherwise.
        target_spend_micros: Optional daily target spend in micros for the
            TARGET_SPEND (MAXIMIZE_CLICKS) bidding strategy. DEPRECATED by
            Google — prefer updating the campaign budget via
            ``budget_amount_micros``. Only valid when the campaign's bidding
            strategy is (or is being set to) MAXIMIZE_CLICKS.
        budget_amount_micros: Optional new daily budget in micros
            (e.g., 10000000 = 10.00 in account currency). Updates the campaign's
            linked budget resource.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Updated campaign details:
            - campaign_resource_name: Full resource name
            - updated_fields: List of fields that were updated
            - budget_updated: Whether the budget was also updated
            - status: Update status

    Raises:
        ToolError: If no fields to update or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.update
        campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

        field_mask: list[str] = []

        if name is not None:
            campaign.name = name
            field_mask.append("name")

        if status is not None:
            campaign.status = get_enum_value(client, "CampaignStatusEnum", status)
            field_mask.append("status")

        if start_date is not None:
            campaign.start_date = start_date.replace("-", "")
            field_mask.append("start_date")

        if end_date is not None:
            campaign.end_date = end_date.replace("-", "")
            field_mask.append("end_date")

        # Network settings are handled separately with verification
        has_network_changes = any(v is not None for v in [
            target_content_network, target_search_network, target_partner_search_network,
        ])

        if geo_target_type is not None:
            campaign.geo_target_type_setting.positive_geo_target_type = get_enum_value(
                client, "PositiveGeoTargetTypeEnum", geo_target_type.upper()
            )
            field_mask.append("geo_target_type_setting.positive_geo_target_type")

        if bidding_strategy_type is not None:
            strategy = bidding_strategy_type.upper()
            # Google Ads API requires clearing old bidding strategy fields
            # when switching to a new one — include all strategy fields in
            # the field mask so the old one gets unset.
            all_bidding_fields = [
                "target_spend.target_spend_micros",
                "maximize_conversions.target_cpa_micros",
                "maximize_conversion_value.target_roas",
                "target_cpa.target_cpa_micros",
                "target_roas.target_roas",
                "manual_cpc.enhanced_cpc_enabled",
            ]
            if strategy == "MAXIMIZE_CLICKS":
                campaign.target_spend.target_spend_micros = target_spend_micros or 0
                if cpc_bid_ceiling_micros is not None:
                    campaign.target_spend.cpc_bid_ceiling_micros = cpc_bid_ceiling_micros
            elif strategy == "MAXIMIZE_CONVERSIONS":
                campaign.maximize_conversions.target_cpa_micros = target_cpa_micros or 0
            elif strategy == "TARGET_CPA":
                campaign.target_cpa.target_cpa_micros = target_cpa_micros or 0
            elif strategy == "TARGET_ROAS":
                campaign.target_roas.target_roas = target_roas or 0.0
            elif strategy == "MANUAL_CPC":
                campaign.manual_cpc.enhanced_cpc_enabled = enhanced_cpc or False
            else:
                raise ToolError(
                    f"Invalid bidding_strategy_type '{bidding_strategy_type}'. "
                    "Options: MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS, TARGET_CPA, "
                    "TARGET_ROAS, MANUAL_CPC"
                )
            field_mask.extend(all_bidding_fields)

        # Handle target_spend sub-fields independently of a full strategy switch.
        # These only apply to MAXIMIZE_CLICKS (TARGET_SPEND). If the caller did
        # not also provide bidding_strategy_type, validate against the current
        # strategy on the server so we fail fast with a clear message instead
        # of letting Google Ads return a confusing error.
        if (
            cpc_bid_ceiling_micros is not None or target_spend_micros is not None
        ) and bidding_strategy_type is None:
            current_strategy = _get_campaign_bidding_strategy_type(
                client, customer_id, campaign_id
            )
            if current_strategy != "TARGET_SPEND":
                raise ToolError(
                    "cpc_bid_ceiling_micros / target_spend_micros only apply to "
                    "MAXIMIZE_CLICKS (TARGET_SPEND) bidding strategy. "
                    f"Current strategy: {current_strategy}. "
                    "Switch the campaign to MAXIMIZE_CLICKS first by passing "
                    "bidding_strategy_type='MAXIMIZE_CLICKS' in the same call."
                )
            if cpc_bid_ceiling_micros is not None:
                campaign.target_spend.cpc_bid_ceiling_micros = cpc_bid_ceiling_micros
                field_mask.append("target_spend.cpc_bid_ceiling_micros")
            if target_spend_micros is not None:
                campaign.target_spend.target_spend_micros = target_spend_micros
                field_mask.append("target_spend.target_spend_micros")
        elif (
            cpc_bid_ceiling_micros is not None or target_spend_micros is not None
        ) and bidding_strategy_type is not None:
            # bidding_strategy_type was supplied — must be MAXIMIZE_CLICKS or
            # these fields are meaningless. Reject the mismatch up front.
            if bidding_strategy_type.upper() != "MAXIMIZE_CLICKS":
                raise ToolError(
                    "cpc_bid_ceiling_micros / target_spend_micros only apply to "
                    "MAXIMIZE_CLICKS (TARGET_SPEND) bidding strategy. "
                    f"Requested strategy: {bidding_strategy_type.upper()}."
                )
            # Switching TO MAXIMIZE_CLICKS — the bidding_strategy_type block
            # above already wrote target_spend.target_spend_micros and (if
            # given) cpc_bid_ceiling_micros. We still need to extend the mask
            # with cpc_bid_ceiling_micros since all_bidding_fields does not
            # include it.
            if cpc_bid_ceiling_micros is not None:
                field_mask.append("target_spend.cpc_bid_ceiling_micros")

        if not field_mask and not has_network_changes and budget_amount_micros is None:
            raise ToolError("No fields to update. Provide at least one field.")

        # Update non-network campaign fields if any
        budget_updated = False
        if field_mask:
            campaign_operation.update_mask.paths.extend(field_mask)

            response = campaign_service.mutate_campaigns(
                customer_id=customer_id,
                operations=[campaign_operation],
            )
            campaign_resource_name = response.results[0].resource_name
        else:
            campaign_resource_name = (
                f"customers/{customer_id}/campaigns/{campaign_id}"
            )

        # Handle network_settings with dedicated mutation + verification
        network_verification = None
        if has_network_changes:
            MAX_RETRIES = 2
            for attempt in range(1, MAX_RETRIES + 1):
                _mutate_network_settings(
                    client, customer_id, campaign_id,
                    target_content_network=target_content_network,
                    target_search_network=target_search_network,
                    target_partner_search_network=target_partner_search_network,
                )

                # Wait briefly then verify the mutation took effect
                time.sleep(1)
                actual = _verify_network_settings(client, customer_id, campaign_id)

                mismatches = []
                if target_content_network is not None and actual["target_content_network"] != target_content_network:
                    mismatches.append(
                        f"target_content_network: wanted={target_content_network}, "
                        f"got={actual['target_content_network']}"
                    )
                if target_search_network is not None and actual["target_search_network"] != target_search_network:
                    mismatches.append(
                        f"target_search_network: wanted={target_search_network}, "
                        f"got={actual['target_search_network']}"
                    )
                if target_partner_search_network is not None and actual["target_partner_search_network"] != target_partner_search_network:
                    mismatches.append(
                        f"target_partner_search_network: wanted={target_partner_search_network}, "
                        f"got={actual['target_partner_search_network']}"
                    )

                if not mismatches:
                    network_verification = {
                        "verified": True,
                        "attempt": attempt,
                        "actual_values": actual,
                    }
                    break

                if attempt < MAX_RETRIES:
                    time.sleep(2)

            if mismatches:
                raise ToolError(
                    f"NETWORK SETTINGS VERIFICATION FAILED after {MAX_RETRIES} attempts! "
                    f"The API accepted the mutation but the values did NOT change. "
                    f"Mismatches: {'; '.join(mismatches)}. "
                    f"Actual values read back: {actual}. "
                    f"You MUST verify manually in the Google Ads UI at ads.google.com."
                )

            if target_content_network is not None:
                field_mask.append("network_settings.target_content_network")
            if target_search_network is not None:
                field_mask.append("network_settings.target_search_network")
            if target_partner_search_network is not None:
                field_mask.append("network_settings.target_partner_search_network")

        # Update budget separately (budgets are independent resources)
        if budget_amount_micros is not None:
            ga_service = client.get_service("GoogleAdsService")
            budget_query = f"""
                SELECT campaign.campaign_budget
                FROM campaign
                WHERE campaign.id = {campaign_id}
                LIMIT 1
            """
            budget_response = ga_service.search_stream(
                customer_id=customer_id,
                query=budget_query,
            )
            budget_resource_name = None
            for batch in budget_response:
                for row in batch.results:
                    budget_resource_name = row.campaign.campaign_budget

            if not budget_resource_name:
                raise ToolError(
                    f"Could not find budget for campaign {campaign_id}"
                )

            budget_service = client.get_service("CampaignBudgetService")
            budget_operation = client.get_type("CampaignBudgetOperation")
            budget = budget_operation.update
            budget.resource_name = budget_resource_name
            budget.amount_micros = budget_amount_micros
            budget_operation.update_mask.paths.append("amount_micros")

            budget_service.mutate_campaign_budgets(
                customer_id=customer_id,
                operations=[budget_operation],
            )
            budget_updated = True
            field_mask.append("budget_amount_micros")

        result = {
            "campaign_resource_name": campaign_resource_name,
            "updated_fields": field_mask,
            "budget_updated": budget_updated,
            "status": "updated",
        }
        if network_verification:
            result["network_settings_verification"] = network_verification
        return result

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_delete_campaign(
    campaign_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes a Google Ads campaign.

    Note: This sets the campaign status to REMOVED. The campaign data
    is retained and can still be queried but cannot be reactivated.

    Args:
        campaign_id: The campaign ID to remove.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal status:
            - campaign_resource_name: Full resource name
            - status: "removed"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign_operation.remove = f"customers/{customer_id}/campaigns/{campaign_id}"

        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation],
        )

        return {
            "campaign_resource_name": response.results[0].resource_name,
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_set_campaign_locations(
    campaign_id: str,
    location_ids: list[str],
    customer_id: Optional[str] = None,
    replace_existing: bool = True,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Sets location targeting for a campaign.

    By default replaces all existing location criteria. Without location targeting,
    ads show worldwide — always set locations for new campaigns!

    Args:
        campaign_id: The campaign ID to update.
        location_ids: List of geo target constant IDs.
            Common IDs: "2203" (Czech Republic), "2703" (Slovakia),
            "2276" (Germany), "2840" (United States), "2826" (United Kingdom),
            "2250" (France), "2380" (Italy), "2724" (Spain), "2616" (Poland).
            Find more at: https://developers.google.com/google-ads/api/data/geotargets
        customer_id: The Google Ads customer ID. Uses default if not provided.
        replace_existing: If True (default), removes existing location criteria first.
            If False, adds to existing locations.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Result with locations_added count and locations_removed count.

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_resource = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion_service = client.get_service("CampaignCriterionService")
        removed_count = 0

        # Remove existing location criteria if replacing
        if replace_existing:
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign_criterion.resource_name, campaign_criterion.location.geo_target_constant
                FROM campaign_criterion
                WHERE campaign.id = {campaign_id}
                  AND campaign_criterion.type = 'LOCATION'
                  AND campaign_criterion.negative = FALSE
            """
            response = ga_service.search_stream(
                customer_id=customer_id, query=query
            )
            remove_ops = []
            for batch in response:
                for row in batch.results:
                    op = client.get_type("CampaignCriterionOperation")
                    op.remove = row.campaign_criterion.resource_name
                    remove_ops.append(op)

            if remove_ops:
                criterion_service.mutate_campaign_criteria(
                    customer_id=customer_id, operations=remove_ops
                )
                removed_count = len(remove_ops)

        # Add new location criteria
        add_ops = []
        for loc_id in location_ids:
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = campaign_resource
            criterion.location.geo_target_constant = f"geoTargetConstants/{loc_id}"
            add_ops.append(op)

        if add_ops:
            criterion_service.mutate_campaign_criteria(
                customer_id=customer_id, operations=add_ops
            )

        return {
            "campaign_id": campaign_id,
            "locations_added": len(add_ops),
            "locations_removed": removed_count,
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_set_campaign_languages(
    campaign_id: str,
    language_ids: list[str],
    customer_id: Optional[str] = None,
    replace_existing: bool = True,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Sets language targeting for a campaign.

    Args:
        campaign_id: The campaign ID to update.
        language_ids: List of language criterion IDs.
            Common IDs: "1021" (Czech), "1000" (English), "1001" (German),
            "1033" (Slovak), "1002" (French), "1004" (Italian), "1003" (Spanish),
            "1030" (Polish).
        customer_id: The Google Ads customer ID. Uses default if not provided.
        replace_existing: If True (default), removes existing language criteria first.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Result with languages_added and languages_removed counts.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_resource = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion_service = client.get_service("CampaignCriterionService")
        removed_count = 0

        if replace_existing:
            ga_service = client.get_service("GoogleAdsService")
            response = ga_service.search_stream(
                customer_id=customer_id,
                query=f"""
                    SELECT campaign_criterion.resource_name
                    FROM campaign_criterion
                    WHERE campaign.id = {campaign_id}
                      AND campaign_criterion.type = 'LANGUAGE'
                      AND campaign_criterion.negative = FALSE
                """,
            )
            remove_ops = []
            for batch in response:
                for row in batch.results:
                    op = client.get_type("CampaignCriterionOperation")
                    op.remove = row.campaign_criterion.resource_name
                    remove_ops.append(op)
            if remove_ops:
                criterion_service.mutate_campaign_criteria(
                    customer_id=customer_id, operations=remove_ops
                )
                removed_count = len(remove_ops)

        add_ops = []
        for lang_id in language_ids:
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = campaign_resource
            criterion.language.language_constant = f"languageConstants/{lang_id}"
            add_ops.append(op)

        if add_ops:
            criterion_service.mutate_campaign_criteria(
                customer_id=customer_id, operations=add_ops
            )

        return {
            "campaign_id": campaign_id,
            "languages_added": len(add_ops),
            "languages_removed": removed_count,
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_set_ad_schedule(
    campaign_id: str,
    schedules: list[dict[str, Any]],
    customer_id: Optional[str] = None,
    replace_existing: bool = True,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Sets ad schedule (day/hour targeting) for a campaign.

    Controls which days and hours ads are shown. Replaces existing schedules
    by default. Without a schedule, ads run 24/7.

    Args:
        campaign_id: The campaign ID to update.
        schedules: List of schedule entries, each with:
            - day: Day of week (MONDAY, TUESDAY, WEDNESDAY, THURSDAY,
              FRIDAY, SATURDAY, SUNDAY)
            - start_hour: Start hour 0-23
            - end_hour: End hour 0-24 (24 = midnight end)
            - bid_modifier: Optional bid adjustment (1.0 = no change,
              1.2 = +20%, 0.0 = don't show)
        customer_id: The Google Ads customer ID. Uses default if not provided.
        replace_existing: If True (default), removes existing ad schedules first.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Result with schedules_added and schedules_removed counts.

    Example:
        Mon-Fri 7am-6pm:
        schedules=[
            {"day": "MONDAY", "start_hour": 7, "end_hour": 18},
            {"day": "TUESDAY", "start_hour": 7, "end_hour": 18},
            {"day": "WEDNESDAY", "start_hour": 7, "end_hour": 18},
            {"day": "THURSDAY", "start_hour": 7, "end_hour": 18},
            {"day": "FRIDAY", "start_hour": 7, "end_hour": 18},
        ]
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_resource = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion_service = client.get_service("CampaignCriterionService")
        removed_count = 0

        if replace_existing:
            ga_service = client.get_service("GoogleAdsService")
            response = ga_service.search_stream(
                customer_id=customer_id,
                query=f"""
                    SELECT campaign_criterion.resource_name
                    FROM campaign_criterion
                    WHERE campaign.id = {campaign_id}
                      AND campaign_criterion.type = 'AD_SCHEDULE'
                """,
            )
            remove_ops = []
            for batch in response:
                for row in batch.results:
                    op = client.get_type("CampaignCriterionOperation")
                    op.remove = row.campaign_criterion.resource_name
                    remove_ops.append(op)
            if remove_ops:
                criterion_service.mutate_campaign_criteria(
                    customer_id=customer_id, operations=remove_ops
                )
                removed_count = len(remove_ops)

        add_ops = []
        for sched in schedules:
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = campaign_resource
            criterion.ad_schedule.day_of_week = get_enum_value(
                client, "DayOfWeekEnum", sched["day"].upper()
            )
            criterion.ad_schedule.start_hour = sched["start_hour"]
            criterion.ad_schedule.start_minute = get_enum_value(
                client, "MinuteOfHourEnum", "ZERO"
            )
            criterion.ad_schedule.end_hour = sched["end_hour"]
            criterion.ad_schedule.end_minute = get_enum_value(
                client, "MinuteOfHourEnum", "ZERO"
            )
            if "bid_modifier" in sched:
                criterion.bid_modifier = sched["bid_modifier"]
            add_ops.append(op)

        if add_ops:
            criterion_service.mutate_campaign_criteria(
                customer_id=customer_id, operations=add_ops
            )

        return {
            "campaign_id": campaign_id,
            "schedules_added": len(add_ops),
            "schedules_removed": removed_count,
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_set_device_bid_adjustment(
    campaign_id: str,
    mobile_bid_modifier: Optional[float] = None,
    tablet_bid_modifier: Optional[float] = None,
    desktop_bid_modifier: Optional[float] = None,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Sets device bid adjustments for a campaign.

    Controls how much to bid on each device type relative to the base bid.
    A modifier of 0.0 means -100% (don't show on that device).
    A modifier of 1.0 means no adjustment. A modifier of 1.5 means +50%.

    Args:
        campaign_id: The campaign ID to update.
        mobile_bid_modifier: Bid modifier for mobile (0.0 = -100%, 0.5 = -50%,
            1.0 = no change, 1.5 = +50%). Set to 0.0 to disable mobile ads.
        tablet_bid_modifier: Bid modifier for tablets.
        desktop_bid_modifier: Bid modifier for desktops.
        customer_id: The Google Ads customer ID. Uses default if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Result with devices_updated list.

    Example - B2B desktop-only:
        mobile_bid_modifier=0.0, tablet_bid_modifier=0.0
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_resource = f"customers/{customer_id}/campaigns/{campaign_id}"
        criterion_service = client.get_service("CampaignCriterionService")

        # First query existing device criteria
        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=f"""
                SELECT campaign_criterion.resource_name, campaign_criterion.device.type,
                       campaign_criterion.bid_modifier
                FROM campaign_criterion
                WHERE campaign.id = {campaign_id}
                  AND campaign_criterion.type = 'DEVICE'
            """,
        )
        existing = {}
        for batch in response:
            for row in batch.results:
                device_type = row.campaign_criterion.device.type_
                existing[device_type] = row.campaign_criterion.resource_name

        device_map = {
            "MOBILE": (2, mobile_bid_modifier),
            "TABLET": (3, tablet_bid_modifier),
            "DESKTOP": (4, desktop_bid_modifier),
        }

        ops = []
        devices_updated = []
        for name, (enum_val, modifier) in device_map.items():
            if modifier is None:
                continue

            if enum_val in existing:
                # Update existing criterion
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.update
                criterion.resource_name = existing[enum_val]
                criterion.bid_modifier = modifier
                op.update_mask.paths.append("bid_modifier")
                ops.append(op)
            else:
                # Create new criterion
                op = client.get_type("CampaignCriterionOperation")
                criterion = op.create
                criterion.campaign = campaign_resource
                criterion.device.type_ = enum_val
                criterion.bid_modifier = modifier
                ops.append(op)
            devices_updated.append({"device": name, "bid_modifier": modifier})

        if ops:
            criterion_service.mutate_campaign_criteria(
                customer_id=customer_id, operations=ops
            )

        return {
            "campaign_id": campaign_id,
            "devices_updated": devices_updated,
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_sitelink_asset(
    link_text: str,
    final_urls: list[str],
    description1: Optional[str] = None,
    description2: Optional[str] = None,
    campaign_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a sitelink extension asset and links it at account or campaign level.

    Sitelinks appear below ads as additional links. They increase CTR and
    take up more SERP space.

    Args:
        link_text: The sitelink text shown to users (max 25 chars).
        final_urls: List of landing page URLs for this sitelink.
        description1: Optional first description line (max 35 chars).
        description2: Optional second description line (max 35 chars).
        campaign_id: If provided, links to this campaign. Otherwise links at account level.
        customer_id: The Google Ads customer ID. Uses default if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Created asset details with asset_resource_name and link_resource_name.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        # Create the sitelink asset
        asset_service = client.get_service("AssetService")
        asset_op = client.get_type("AssetOperation")
        asset = asset_op.create
        asset.sitelink_asset.link_text = link_text
        if description1:
            asset.sitelink_asset.description1 = description1
        if description2:
            asset.sitelink_asset.description2 = description2
        asset.final_urls.extend(final_urls)

        asset_response = asset_service.mutate_assets(
            customer_id=customer_id, operations=[asset_op]
        )
        asset_resource = asset_response.results[0].resource_name

        # Link the asset
        if campaign_id:
            campaign_asset_service = client.get_service("CampaignAssetService")
            link_op = client.get_type("CampaignAssetOperation")
            link = link_op.create
            link.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.SITELINK
            link_response = campaign_asset_service.mutate_campaign_assets(
                customer_id=customer_id, operations=[link_op]
            )
            link_resource = link_response.results[0].resource_name
        else:
            customer_asset_service = client.get_service("CustomerAssetService")
            link_op = client.get_type("CustomerAssetOperation")
            link = link_op.create
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.SITELINK
            link_response = customer_asset_service.mutate_customer_assets(
                customer_id=customer_id, operations=[link_op]
            )
            link_resource = link_response.results[0].resource_name

        return {
            "asset_resource_name": asset_resource,
            "link_resource_name": link_resource,
            "level": "campaign" if campaign_id else "customer",
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_callout_asset(
    callout_texts: list[str],
    campaign_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates callout extension assets and links them at account or campaign level.

    Callouts are short phrases (max 25 chars) shown with your ads highlighting
    key selling points (e.g. "Free Shipping", "24/7 Support", "No Hidden Fees").

    Args:
        callout_texts: List of callout text strings (max 25 chars each, min 2 recommended).
        campaign_id: If provided, links to this campaign. Otherwise links at account level.
        customer_id: The Google Ads customer ID. Uses default if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Created assets with asset_count and link details.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_service = client.get_service("AssetService")
        asset_ops = []
        for text in callout_texts:
            op = client.get_type("AssetOperation")
            op.create.callout_asset.callout_text = text
            asset_ops.append(op)

        asset_response = asset_service.mutate_assets(
            customer_id=customer_id, operations=asset_ops
        )
        asset_resources = [r.resource_name for r in asset_response.results]

        # Link all assets
        if campaign_id:
            campaign_asset_service = client.get_service("CampaignAssetService")
            link_ops = []
            for ar in asset_resources:
                op = client.get_type("CampaignAssetOperation")
                link = op.create
                link.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
                link.asset = ar
                link.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
                link_ops.append(op)
            campaign_asset_service.mutate_campaign_assets(
                customer_id=customer_id, operations=link_ops
            )
        else:
            customer_asset_service = client.get_service("CustomerAssetService")
            link_ops = []
            for ar in asset_resources:
                op = client.get_type("CustomerAssetOperation")
                link = op.create
                link.asset = ar
                link.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
                link_ops.append(op)
            customer_asset_service.mutate_customer_assets(
                customer_id=customer_id, operations=link_ops
            )

        return {
            "asset_resources": asset_resources,
            "asset_count": len(asset_resources),
            "level": "campaign" if campaign_id else "customer",
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_structured_snippet_asset(
    header: str,
    values: list[str],
    campaign_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a structured snippet extension asset and links it.

    Structured snippets highlight specific aspects of your products/services
    under a predefined header.

    Args:
        header: The snippet header. Must be one of: Brands, Courses, Degree programs,
            Destinations, Featured hotels, Insurance coverage, Models, Neighborhoods,
            Service catalog, Shows, Styles, Types.
        values: List of values under the header (min 3 recommended).
            Example: header="Types", values=["CRM", "ERP", "Sklad", "Výroba"]
        campaign_id: If provided, links to this campaign. Otherwise links at account level.
        customer_id: The Google Ads customer ID. Uses default if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Created asset details.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_service = client.get_service("AssetService")
        asset_op = client.get_type("AssetOperation")
        asset = asset_op.create
        asset.structured_snippet_asset.header = header
        asset.structured_snippet_asset.values.extend(values)

        asset_response = asset_service.mutate_assets(
            customer_id=customer_id, operations=[asset_op]
        )
        asset_resource = asset_response.results[0].resource_name

        if campaign_id:
            campaign_asset_service = client.get_service("CampaignAssetService")
            link_op = client.get_type("CampaignAssetOperation")
            link = link_op.create
            link.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
            campaign_asset_service.mutate_campaign_assets(
                customer_id=customer_id, operations=[link_op]
            )
        else:
            customer_asset_service = client.get_service("CustomerAssetService")
            link_op = client.get_type("CustomerAssetOperation")
            link = link_op.create
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
            customer_asset_service.mutate_customer_assets(
                customer_id=customer_id, operations=[link_op]
            )

        return {
            "asset_resource_name": asset_resource,
            "level": "campaign" if campaign_id else "customer",
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_set_tracking_template(
    tracking_url_template: Optional[str] = None,
    final_url_suffix: Optional[str] = None,
    campaign_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Sets tracking URL template and/or final URL suffix at account or campaign level.

    When no campaign_id is provided, sets the template at account level (Customer resource).
    Account-level templates apply to ALL campaigns as default.
    When campaign_id is provided, sets at campaign level (overrides account-level).

    Common tracking_url_template patterns:
        - "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign={_campaign}"
        - "{lpurl}?gclid={gclid}" (auto-tagging — usually not needed, use auto-tagging setting)

    Common final_url_suffix patterns:
        - "utm_source=google&utm_medium=cpc"
        - "utm_source=google&utm_medium=cpc&utm_campaign={_campaign}"

    ValueTrack parameters you can use:
        - {lpurl} - Landing page URL (required in tracking_url_template)
        - {gclid} - Google click ID
        - {campaignid} - Campaign ID
        - {adgroupid} - Ad group ID
        - {keyword} - Keyword that triggered the ad
        - {device} - Device type (m, t, c)
        - {matchtype} - Match type (e, p, b)
        - {network} - Network (g=Google Search, s=Search Partner, d=Display)
        - {_campaign} - Custom parameter (set via campaign custom parameters)

    Args:
        tracking_url_template: The tracking URL template. Use {lpurl} as placeholder
            for the landing page URL. Set to empty string "" to clear.
        final_url_suffix: URL parameters appended to the landing page URL.
            Do NOT include "?" — it's added automatically.
            Set to empty string "" to clear.
        campaign_id: Optional campaign ID. If provided, sets at campaign level.
            If omitted, sets at account level.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Update result:
            - level: "account" or "campaign"
            - resource_name: The updated resource name
            - updated_fields: List of fields that were updated
            - status: "updated"

    Raises:
        ToolError: If no fields provided or API request fails.
    """
    if tracking_url_template is None and final_url_suffix is None:
        raise ToolError(
            "Provide at least one of tracking_url_template or final_url_suffix."
        )

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        updated_fields: list[str] = []

        if campaign_id is not None:
            # Campaign-level tracking template
            campaign_service = client.get_service("CampaignService")
            campaign_operation = client.get_type("CampaignOperation")
            campaign = campaign_operation.update
            campaign.resource_name = (
                f"customers/{customer_id}/campaigns/{campaign_id}"
            )

            if tracking_url_template is not None:
                campaign.tracking_url_template = tracking_url_template
                updated_fields.append("tracking_url_template")

            if final_url_suffix is not None:
                campaign.final_url_suffix = final_url_suffix
                updated_fields.append("final_url_suffix")

            campaign_operation.update_mask.paths.extend(updated_fields)

            response = campaign_service.mutate_campaigns(
                customer_id=customer_id,
                operations=[campaign_operation],
            )

            return {
                "level": "campaign",
                "resource_name": response.results[0].resource_name,
                "updated_fields": updated_fields,
                "status": "updated",
            }

        else:
            # Account-level tracking template
            customer_service = client.get_service("CustomerService")
            customer_operation = client.get_type("CustomerOperation")
            customer = customer_operation.update
            customer.resource_name = f"customers/{customer_id}"

            if tracking_url_template is not None:
                customer.tracking_url_template = tracking_url_template
                updated_fields.append("tracking_url_template")

            if final_url_suffix is not None:
                customer.final_url_suffix = final_url_suffix
                updated_fields.append("final_url_suffix")

            customer_operation.update_mask.paths.extend(updated_fields)

            response = customer_service.mutate_customer(
                customer_id=customer_id,
                operation=customer_operation,
            )

            return {
                "level": "account",
                "resource_name": response.result.resource_name,
                "updated_fields": updated_fields,
                "status": "updated",
            }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
