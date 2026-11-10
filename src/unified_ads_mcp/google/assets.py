"""Asset management tools for Google Ads API.

This module provides MCP tools for managing Google Ads assets including
text assets (headlines, descriptions), image assets, asset linking
for Performance Max campaigns, asset automation settings, and
automatically created asset management.
"""

import base64
import json
import os
import re
from typing import Any, Optional


def _coerce_list(value: Any) -> list[str]:
    """Coerce a value to list[str]. Handles JSON strings from MCP transport."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
            except json.JSONDecodeError:
                pass
        return [v.strip() for v in value.split(",") if v.strip()]
    raise ValueError(f"Cannot coerce {type(value).__name__} to list[str]")

from google.ads.googleads.errors import GoogleAdsException
from mcp.server.fastmcp.exceptions import ToolError

from ..server import mcp
from .client import (
    get_google_ads_client,
    format_error,
    resolve_customer_id,
    get_enum_name,
    get_enum_value,
)


@mcp.tool()
def google_list_assets(
    customer_id: Optional[str] = None,
    asset_type: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists assets for a Google Ads customer.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        asset_type: Optional filter by asset type. Options:
            - TEXT: Text assets (headlines, descriptions)
            - IMAGE: Image assets
            - MEDIA_BUNDLE: Media bundle assets
            - YOUTUBE_VIDEO: YouTube video assets
            - CALL_TO_ACTION: Call to action assets
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of assets with:
            - id: Asset ID
            - resource_name: Full resource name
            - type: Asset type
            - name: Asset name (if set)
            - text: Text content (for TEXT assets)
            - image_url: Image URL (for IMAGE assets)

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")

        query = """
            SELECT
                asset.id,
                asset.resource_name,
                asset.type,
                asset.name,
                asset.text_asset.text,
                asset.image_asset.full_size.url,
                asset.image_asset.file_size,
                asset.youtube_video_asset.youtube_video_id
            FROM asset
        """

        if asset_type:
            query += f" WHERE asset.type = '{asset_type.upper()}'"

        query += " ORDER BY asset.id LIMIT 100"

        response = ga_service.search(customer_id=customer_id, query=query)

        assets = []
        for row in response:
            asset = row.asset
            asset_data = {
                "id": str(asset.id),
                "resource_name": asset.resource_name,
                "type": get_enum_name(client, "AssetTypeEnum", asset.type_),
                "name": asset.name if asset.name else None,
            }

            # Add type-specific fields
            if asset.text_asset.text:
                asset_data["text"] = asset.text_asset.text
            if asset.image_asset.full_size.url:
                asset_data["image_url"] = asset.image_asset.full_size.url
                asset_data["file_size"] = asset.image_asset.file_size
            if asset.youtube_video_asset.youtube_video_id:
                asset_data["youtube_video_id"] = (
                    asset.youtube_video_asset.youtube_video_id
                )

            assets.append(asset_data)

        return assets

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_text_asset(
    text: str,
    customer_id: Optional[str] = None,
    name: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a text asset (for headlines, descriptions, etc.).

    Args:
        text: The text content for the asset.
            - Headlines: max 30 characters
            - Descriptions: max 90 characters
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        name: Optional name for the asset.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created asset details:
            - asset_id: The new asset ID
            - resource_name: Full resource name
            - text: The text content

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_service = client.get_service("AssetService")

        # Create the text asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.text_asset.text = text
        if name:
            asset.name = name

        # Execute the mutation
        response = asset_service.mutate_assets(
            customer_id=customer_id,
            operations=[asset_operation],
        )

        created_resource = response.results[0].resource_name
        asset_id = created_resource.split("/")[-1]

        return {
            "asset_id": asset_id,
            "resource_name": created_resource,
            "text": text,
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_image_asset(
    image_data: str,
    customer_id: Optional[str] = None,
    name: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates an image asset from base64 data or a file path.

    Args:
        image_data: Can be one of:
            - File path to an image file (PNG, JPG, GIF) - e.g., "/tmp/image.jpg"
            - File path to a text file containing base64 data - e.g., "/tmp/image-b64.txt"
            - Direct base64 encoded image data string
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        name: Optional name for the asset.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created asset details:
            - asset_id: The new asset ID
            - resource_name: Full resource name
            - status: Creation status

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_service = client.get_service("AssetService")

        # Handle different input types
        image_bytes = None

        # Check if it's a file path
        if image_data.startswith("/") and os.path.isfile(image_data):
            file_path = image_data
            # Check if it's an image file or a base64 text file
            lower_path = file_path.lower()
            if lower_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                # Read binary image file directly
                with open(file_path, "rb") as f:
                    image_bytes = f.read()
            else:
                # Assume it's a text file containing base64 data
                with open(file_path, "r") as f:
                    b64_data = f.read().strip()
                try:
                    image_bytes = base64.b64decode(b64_data)
                except Exception as e:
                    raise ToolError(f"Invalid base64 data in file {file_path}: {e}")
        else:
            # Treat as direct base64 data
            try:
                image_bytes = base64.b64decode(image_data)
            except Exception as e:
                raise ToolError(f"Invalid base64 image data: {e}")

        # Create the image asset
        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.image_asset.data = image_bytes
        if name:
            asset.name = name

        # Execute the mutation
        response = asset_service.mutate_assets(
            customer_id=customer_id,
            operations=[asset_operation],
        )

        created_resource = response.results[0].resource_name
        asset_id = created_resource.split("/")[-1]

        return {
            "asset_id": asset_id,
            "resource_name": created_resource,
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


_YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|^)([A-Za-z0-9_-]{11})(?:[?&#/]|$)")


@mcp.tool()
def google_create_youtube_video_asset(
    youtube_video: str,
    customer_id: Optional[str] = None,
    name: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a YOUTUBE_VIDEO asset from a video already on YouTube.

    The Google Ads API cannot take a video file: upload the video to YouTube
    first (public or unlisted), then pass its URL or ID here. Link the asset
    with google_add_asset_group_asset (field type YOUTUBE_VIDEO) or use it
    in a Demand Gen / video ad.

    Args:
        youtube_video: YouTube URL (watch, youtu.be, shorts) or the 11-char video ID.
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        name: Optional name for the asset.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: asset_id, resource_name, youtube_video_id, status.

    Raises:
        ToolError: If the ID is invalid or the API request fails.
    """
    match = _YOUTUBE_ID.search(youtube_video.strip())
    if not match:
        raise ToolError(f"Not a YouTube URL or video ID: {youtube_video!r}")
    video_id = match.group(1)
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_operation = client.get_type("AssetOperation")
        asset = asset_operation.create
        asset.youtube_video_asset.youtube_video_id = video_id
        if name:
            asset.name = name

        response = client.get_service("AssetService").mutate_assets(
            customer_id=customer_id,
            operations=[asset_operation],
        )
        created_resource = response.results[0].resource_name
        return {
            "asset_id": created_resource.split("/")[-1],
            "resource_name": created_resource,
            "youtube_video_id": video_id,
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_text_assets_batch(
    headlines: Any,
    descriptions: Any,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates multiple text assets in a single batch operation.

    This is useful for creating all assets needed for a Performance Max
    campaign at once.

    Args:
        headlines: List of headline texts (3-15 headlines, max 30 chars each).
        descriptions: List of description texts (2-5 descriptions, max 90 chars each).
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created assets details:
            - headline_assets: List of created headline asset resource names
            - description_assets: List of created description asset resource names
            - status: Creation status

    Raises:
        ToolError: If the API request fails or validation fails.
    """
    headlines = _coerce_list(headlines)
    descriptions = _coerce_list(descriptions)

    try:
        # Validate inputs
        if len(headlines) < 3:
            raise ToolError("At least 3 headlines are required")
        if len(headlines) > 15:
            raise ToolError("Maximum 15 headlines allowed")
        if len(descriptions) < 2:
            raise ToolError("At least 2 descriptions are required")
        if len(descriptions) > 5:
            raise ToolError("Maximum 5 descriptions allowed")

        for i, h in enumerate(headlines):
            if len(h) > 30:
                raise ToolError(f"Headline {i + 1} exceeds 30 characters: '{h}'")

        for i, d in enumerate(descriptions):
            if len(d) > 90:
                raise ToolError(f"Description {i + 1} exceeds 90 characters")

        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_service = client.get_service("AssetService")

        # Create operations for all assets
        operations = []

        # Headlines
        for headline in headlines:
            op = client.get_type("AssetOperation")
            op.create.text_asset.text = headline
            operations.append(op)

        # Descriptions
        for description in descriptions:
            op = client.get_type("AssetOperation")
            op.create.text_asset.text = description
            operations.append(op)

        # Execute batch mutation
        response = asset_service.mutate_assets(
            customer_id=customer_id,
            operations=operations,
        )

        # Split results into headlines and descriptions
        headline_count = len(headlines)
        headline_assets = [r.resource_name for r in response.results[:headline_count]]
        description_assets = [
            r.resource_name for r in response.results[headline_count:]
        ]

        return {
            "headline_assets": headline_assets,
            "description_assets": description_assets,
            "headlines_created": len(headline_assets),
            "descriptions_created": len(description_assets),
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_link_asset_to_campaign(
    campaign_id: str,
    asset_resource_name: str,
    field_type: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Links an asset to a campaign (for brand guidelines, etc.).

    This is used to link BUSINESS_NAME and LOGO assets at the campaign level,
    which is required for Performance Max campaigns since API v21.

    Args:
        campaign_id: The campaign ID to link the asset to.
        asset_resource_name: The full resource name of the asset.
        field_type: The field type for the asset. Options:
            - BUSINESS_NAME: Business name text asset
            - LOGO: Logo image asset
            - MARKETING_IMAGE: Marketing image
            - SQUARE_MARKETING_IMAGE: Square marketing image
            - HEADLINE: Headline text
            - DESCRIPTION: Description text
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Link result:
            - campaign_asset_resource_name: The created link resource name
            - status: Link status

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_asset_service = client.get_service("CampaignAssetService")
        campaign_service = client.get_service("CampaignService")

        # Get campaign resource name
        campaign_resource = campaign_service.campaign_path(customer_id, campaign_id)

        # Create campaign asset link
        operation = client.get_type("CampaignAssetOperation")
        campaign_asset = operation.create
        campaign_asset.campaign = campaign_resource
        campaign_asset.asset = asset_resource_name
        campaign_asset.field_type = get_enum_value(
            client, "AssetFieldTypeEnum", field_type.upper()
        )

        response = campaign_asset_service.mutate_campaign_assets(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "campaign_asset_resource_name": response.results[0].resource_name,
            "status": "linked",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


# --- Asset Automation Settings (campaign-level) ---


@mcp.tool()
def google_get_asset_automation_settings(
    campaign_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Gets the asset automation settings for a Google Ads campaign.

    Shows whether Google automatically generates text assets (headlines,
    descriptions), image enhancements, or videos for this campaign.
    Relevant for Performance Max and Search campaigns.

    NOTE: This shows campaign-level text/image/video auto-generation settings.
    For account-level automated extensions (dynamic sitelinks, callouts that
    pull blog titles), use google_list_auto_created_assets instead.

    Args:
        campaign_id: The campaign ID to check.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Campaign details with automation settings:
            - id: Campaign ID
            - name: Campaign name
            - channel_type: Campaign type (SEARCH, PERFORMANCE_MAX, etc.)
            - asset_automation_settings: List of settings, each with:
                - type: Automation type name
                - status: OPTED_IN or OPTED_OUT

    Raises:
        ToolError: If the campaign is not found or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.advertising_channel_type,
                campaign.asset_automation_settings
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """

        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        for batch in response:
            for row in batch.results:
                settings = []
                for s in row.campaign.asset_automation_settings:
                    settings.append(
                        {
                            "type": get_enum_name(
                                client,
                                "AssetAutomationTypeEnum",
                                s.asset_automation_type,
                            ),
                            "status": get_enum_name(
                                client,
                                "AssetAutomationStatusEnum",
                                s.asset_automation_status,
                            ),
                        }
                    )

                return {
                    "id": str(row.campaign.id),
                    "name": row.campaign.name,
                    "channel_type": get_enum_name(
                        client,
                        "AdvertisingChannelTypeEnum",
                        row.campaign.advertising_channel_type,
                    ),
                    "asset_automation_settings": settings,
                }

        raise ToolError(f"Campaign {campaign_id} not found")

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_update_asset_automation_settings(
    campaign_id: str,
    automation_type: str,
    enabled: bool,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Enables or disables a specific asset automation type on a campaign.

    Controls whether Google automatically creates text, images, or videos
    for this campaign. Use google_get_asset_automation_settings to check
    current state first.

    IMPORTANT: This controls campaign-level text/image/video auto-generation
    (Search + Performance Max campaigns). It does NOT control account-level
    automated extensions (dynamic sitelinks pulling blog titles). For those,
    use google_list_auto_created_assets + google_remove_auto_created_asset,
    or disable in Google Ads UI > Account Settings.

    Args:
        campaign_id: The campaign ID to update.
        automation_type: The type of automation to control. Options:
            - TEXT_ASSET_AUTOMATION: Auto-generate headlines and descriptions
            - FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION: Text for final URL expansion
            - GENERATE_ENHANCED_YOUTUBE_VIDEOS: Enhanced YouTube videos (PMax only)
            - GENERATE_IMAGE_ENHANCEMENT: Image enhancement (PMax only)
            - GENERATE_IMAGE_EXTRACTION: Extract images from landing pages (PMax only)
        enabled: True to opt in (enable), False to opt out (disable).
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Update result:
            - campaign_id: Campaign ID
            - automation_type: The type that was updated
            - status: New status (OPTED_IN or OPTED_OUT)
            - all_settings: All automation settings after the update
            - result: "updated"

    Raises:
        ToolError: If the campaign is not found or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")
        campaign_service = client.get_service("CampaignService")

        # Read existing settings (the API replaces ALL settings on update)
        query = f"""
            SELECT campaign.asset_automation_settings
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """

        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        existing = {}
        found = False
        for batch in response:
            for row in batch.results:
                found = True
                for s in row.campaign.asset_automation_settings:
                    existing[s.asset_automation_type] = s.asset_automation_status

        if not found:
            raise ToolError(f"Campaign {campaign_id} not found")

        # Apply the requested change
        target_type = get_enum_value(
            client, "AssetAutomationTypeEnum", automation_type.upper()
        )
        target_status = (
            client.enums.AssetAutomationStatusEnum.OPTED_IN
            if enabled
            else client.enums.AssetAutomationStatusEnum.OPTED_OUT
        )
        existing[target_type] = target_status

        # Build campaign update with all settings preserved
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.update
        campaign.resource_name = campaign_service.campaign_path(
            customer_id, campaign_id
        )

        for type_val, status_val in existing.items():
            setting = campaign.asset_automation_settings.add()
            setting.asset_automation_type = type_val
            setting.asset_automation_status = status_val

        campaign_operation.update_mask.paths.append("asset_automation_settings")

        campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation],
        )

        # Build result
        all_settings = []
        for type_val, status_val in existing.items():
            all_settings.append(
                {
                    "type": get_enum_name(
                        client, "AssetAutomationTypeEnum", type_val
                    ),
                    "status": get_enum_name(
                        client, "AssetAutomationStatusEnum", status_val
                    ),
                }
            )

        return {
            "campaign_id": campaign_id,
            "automation_type": automation_type.upper(),
            "status": "OPTED_IN" if enabled else "OPTED_OUT",
            "all_settings": all_settings,
            "result": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


# --- Automatically Created Assets (account-level sitelinks, callouts, etc.) ---


def _format_auto_asset(
    client: Any, row: Any, level: str
) -> dict[str, Any]:
    """Format an auto-created asset row into a dict."""
    asset = row.asset
    link = row.campaign_asset if level == "campaign" else row.customer_asset

    result: dict[str, Any] = {
        "asset_id": str(asset.id),
        "resource_name": link.resource_name,
        "asset_resource_name": link.asset,
        "field_type": get_enum_name(
            client, "AssetFieldTypeEnum", link.field_type
        ),
        "status": get_enum_name(
            client, "AssetLinkStatusEnum", link.status
        ),
        "level": level,
        "details": {},
    }

    # Add type-specific content
    if asset.sitelink_asset.link_text:
        result["details"]["link_text"] = asset.sitelink_asset.link_text
        if asset.sitelink_asset.description1:
            result["details"]["description1"] = asset.sitelink_asset.description1
        if asset.sitelink_asset.description2:
            result["details"]["description2"] = asset.sitelink_asset.description2
    elif asset.callout_asset.callout_text:
        result["details"]["callout_text"] = asset.callout_asset.callout_text
    elif asset.structured_snippet_asset.header:
        result["details"]["header"] = asset.structured_snippet_asset.header
        result["details"]["values"] = list(
            asset.structured_snippet_asset.values
        )
    elif asset.text_asset.text:
        result["details"]["text"] = asset.text_asset.text

    return result


@mcp.tool()
def google_list_auto_created_assets(
    customer_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    field_type: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists automatically created assets (sitelinks, callouts, etc.) generated
    by Google from your website content.

    These are the dynamic sitelinks, callouts, and structured snippets that
    Google auto-creates by scanning your website. They often pull irrelevant
    content like blog post titles as sitelinks (e.g., "Co je ERP...").

    While the auto-creation feature itself can only be disabled in the Google
    Ads UI (Account Settings > Automatically created assets), you CAN list
    and remove individual unwanted assets via API using this tool and
    google_remove_auto_created_asset.

    Args:
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        campaign_id: Optional campaign ID to filter by. If not provided,
            lists account-level auto-created assets.
        field_type: Optional filter by asset field type:
            SITELINK, CALLOUT, STRUCTURED_SNIPPET, CALL, etc.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: Auto-created assets, each with:
            - asset_id: Asset ID
            - resource_name: Link resource name (use for removal)
            - asset_resource_name: Underlying asset resource name
            - field_type: SITELINK, CALLOUT, STRUCTURED_SNIPPET, etc.
            - status: ENABLED, PAUSED, or REMOVED
            - level: "customer" or "campaign"
            - details: Type-specific content:
                - Sitelinks: link_text, description1, description2
                - Callouts: callout_text
                - Structured snippets: header, values

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")
        assets = []

        if campaign_id:
            query = f"""
                SELECT
                    campaign_asset.resource_name,
                    campaign_asset.asset,
                    campaign_asset.field_type,
                    campaign_asset.status,
                    asset.id,
                    asset.type,
                    asset.source,
                    asset.text_asset.text,
                    asset.sitelink_asset.link_text,
                    asset.sitelink_asset.description1,
                    asset.sitelink_asset.description2,
                    asset.callout_asset.callout_text,
                    asset.structured_snippet_asset.header,
                    asset.structured_snippet_asset.values
                FROM campaign_asset
                WHERE asset.source = 'AUTOMATICALLY_CREATED'
                    AND campaign.id = {campaign_id}
            """
            if field_type:
                query += (
                    f" AND campaign_asset.field_type = '{field_type.upper()}'"
                )

            response = ga_service.search_stream(
                customer_id=customer_id, query=query
            )
            for batch in response:
                for row in batch.results:
                    assets.append(
                        _format_auto_asset(client, row, "campaign")
                    )
        else:
            query = """
                SELECT
                    customer_asset.resource_name,
                    customer_asset.asset,
                    customer_asset.field_type,
                    customer_asset.status,
                    asset.id,
                    asset.type,
                    asset.source,
                    asset.text_asset.text,
                    asset.sitelink_asset.link_text,
                    asset.sitelink_asset.description1,
                    asset.sitelink_asset.description2,
                    asset.callout_asset.callout_text,
                    asset.structured_snippet_asset.header,
                    asset.structured_snippet_asset.values
                FROM customer_asset
                WHERE asset.source = 'AUTOMATICALLY_CREATED'
            """
            if field_type:
                query += (
                    f" AND customer_asset.field_type = '{field_type.upper()}'"
                )

            response = ga_service.search_stream(
                customer_id=customer_id, query=query
            )
            for batch in response:
                for row in batch.results:
                    assets.append(
                        _format_auto_asset(client, row, "customer")
                    )

        return assets

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_remove_auto_created_asset(
    resource_name: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes an automatically created asset link (sitelink, callout, etc.).

    Use google_list_auto_created_assets first to find the resource_name of
    unwanted auto-created assets (e.g., sitelinks pulling blog titles like
    "Co je ERP...").

    NOTE: This removes the asset LINK, not the underlying asset. Google may
    re-create similar assets over time. To permanently stop auto-creation,
    disable "Automatically created assets" in the Google Ads UI under
    Account Settings > Auto-applied suggestions.

    Args:
        resource_name: The customer_asset or campaign_asset resource name
            to remove. Get this from google_list_auto_created_assets results.
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal result:
            - resource_name: The removed resource name
            - status: "removed"

    Raises:
        ToolError: If the resource name format is unrecognized or API fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        if "customerAssets" in resource_name:
            service = client.get_service("CustomerAssetService")
            operation = client.get_type("CustomerAssetOperation")
            operation.remove = resource_name
            service.mutate_customer_assets(
                customer_id=customer_id,
                operations=[operation],
            )
        elif "campaignAssets" in resource_name:
            service = client.get_service("CampaignAssetService")
            operation = client.get_type("CampaignAssetOperation")
            operation.remove = resource_name
            service.mutate_campaign_assets(
                customer_id=customer_id,
                operations=[operation],
            )
        else:
            raise ToolError(
                f"Unrecognized resource name format: {resource_name}. "
                "Expected a customerAssets or campaignAssets resource name "
                "from google_list_auto_created_assets."
            )

        return {
            "resource_name": resource_name,
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
