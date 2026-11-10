"""Asset Group management tools for Google Ads API.

This module provides MCP tools for managing Asset Groups, which are required
for Performance Max campaigns. Asset Groups contain creative assets (headlines,
descriptions, images) and targeting signals.

Performance Max campaigns require at least one Asset Group with:
- 3-15 headlines (max 30 characters each)
- 2-5 descriptions (max 90 characters each)
- Marketing images and square marketing images
- Logo images
- Final URL

Asset Groups are created using atomic bulk mutate operations to ensure
all required components are created together.
"""

import json
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
def google_list_asset_groups(
    campaign_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists asset groups for a Performance Max campaign.

    Args:
        campaign_id: The Performance Max campaign ID.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of asset groups with:
            - id: Asset group ID
            - resource_name: Full resource name
            - name: Asset group name
            - status: Asset group status
            - final_urls: List of final URLs
            - path1: Display URL path 1
            - path2: Display URL path 2

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
                asset_group.id,
                asset_group.resource_name,
                asset_group.name,
                asset_group.status,
                asset_group.final_urls,
                asset_group.path1,
                asset_group.path2
            FROM asset_group
            WHERE asset_group.campaign = 'customers/{customer_id}/campaigns/{campaign_id}'
            ORDER BY asset_group.id
        """

        response = ga_service.search(customer_id=customer_id, query=query)

        asset_groups = []
        for row in response:
            ag = row.asset_group
            asset_groups.append(
                {
                    "id": str(ag.id),
                    "resource_name": ag.resource_name,
                    "name": ag.name,
                    "status": get_enum_name(client, "AssetGroupStatusEnum", ag.status),
                    "final_urls": list(ag.final_urls),
                    "path1": ag.path1 if ag.path1 else None,
                    "path2": ag.path2 if ag.path2 else None,
                }
            )

        return asset_groups

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_get_asset_group(
    asset_group_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Gets detailed information about a specific asset group.

    Args:
        asset_group_id: The asset group ID to retrieve.
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Asset group details including:
            - id: Asset group ID
            - resource_name: Full resource name
            - name: Asset group name
            - campaign_id: Parent campaign ID
            - status: Asset group status
            - final_urls: List of final URLs
            - final_mobile_urls: List of mobile URLs
            - path1: Display URL path 1
            - path2: Display URL path 2
            - assets: List of linked assets

    Raises:
        ToolError: If the asset group is not found or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")

        # Get asset group details
        query = f"""
            SELECT
                asset_group.id,
                asset_group.resource_name,
                asset_group.name,
                asset_group.campaign,
                asset_group.status,
                asset_group.final_urls,
                asset_group.final_mobile_urls,
                asset_group.path1,
                asset_group.path2
            FROM asset_group
            WHERE asset_group.id = {asset_group_id}
        """

        response = ga_service.search(customer_id=customer_id, query=query)

        asset_group_data = None
        for row in response:
            ag = row.asset_group
            campaign_id = ag.campaign.split("/")[-1] if ag.campaign else None
            asset_group_data = {
                "id": str(ag.id),
                "resource_name": ag.resource_name,
                "name": ag.name,
                "campaign_id": campaign_id,
                "status": get_enum_name(client, "AssetGroupStatusEnum", ag.status),
                "final_urls": list(ag.final_urls),
                "final_mobile_urls": list(ag.final_mobile_urls),
                "path1": ag.path1 if ag.path1 else None,
                "path2": ag.path2 if ag.path2 else None,
            }
            break

        if not asset_group_data:
            raise ToolError(f"Asset group {asset_group_id} not found")

        # Get linked assets
        assets_query = f"""
            SELECT
                asset_group_asset.asset,
                asset_group_asset.field_type,
                asset_group_asset.status,
                asset.id,
                asset.type,
                asset.name,
                asset.text_asset.text,
                asset.image_asset.full_size.url
            FROM asset_group_asset
            WHERE asset_group_asset.asset_group = '{asset_group_data["resource_name"]}'
        """

        assets_response = ga_service.search(customer_id=customer_id, query=assets_query)

        assets = []
        for row in assets_response:
            aga = row.asset_group_asset
            asset = row.asset
            asset_data = {
                "asset_id": str(asset.id),
                "asset_resource_name": aga.asset,
                "field_type": get_enum_name(
                    client, "AssetFieldTypeEnum", aga.field_type
                ),
                "status": get_enum_name(client, "AssetLinkStatusEnum", aga.status),
                "type": get_enum_name(client, "AssetTypeEnum", asset.type_),
                "name": asset.name if asset.name else None,
            }
            if asset.text_asset.text:
                asset_data["text"] = asset.text_asset.text
            if asset.image_asset.full_size.url:
                asset_data["image_url"] = asset.image_asset.full_size.url
            assets.append(asset_data)

        asset_group_data["assets"] = assets
        return asset_group_data

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_asset_group(
    campaign_id: str,
    name: str,
    final_url: str,
    headlines: Any,
    descriptions: Any,
    customer_id: Optional[str] = None,
    business_name: Optional[str] = None,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates an asset group for a Performance Max campaign with text assets.

    This creates an asset group with headlines and descriptions using atomic
    bulk mutate operations. For a complete Performance Max setup, you also need
    to add image assets using google_add_asset_group_asset after creation.

    Args:
        campaign_id: The Performance Max campaign ID.
        name: Name for the asset group.
        final_url: The landing page URL for the ads.
        headlines: List of headline texts (3-15 required, max 30 chars each).
        descriptions: List of description texts (2-5 required, max 90 chars each).
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        business_name: Business name for the ads (recommended).
        path1: Optional display URL path 1 (max 15 chars).
        path2: Optional display URL path 2 (max 15 chars, requires path1).
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created asset group details:
            - asset_group_id: The new asset group ID
            - asset_group_resource_name: Full resource name
            - headline_count: Number of headlines created
            - description_count: Number of descriptions created
            - status: Creation status

    Raises:
        ToolError: If validation fails or API request fails.
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

        # Build all operations for atomic bulk mutate
        mutate_operations = []

        # Use temporary resource names for atomic creation
        asset_group_temp_id = -1
        headline_temp_ids = list(range(-100, -100 - len(headlines), -1))
        description_temp_ids = list(range(-200, -200 - len(descriptions), -1))

        # 1. Create asset group operation
        asset_group_service = client.get_service("AssetGroupService")
        campaign_service = client.get_service("CampaignService")

        asset_group_op = client.get_type("MutateOperation")
        asset_group = asset_group_op.asset_group_operation.create
        asset_group.resource_name = asset_group_service.asset_group_path(
            customer_id, asset_group_temp_id
        )
        asset_group.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        asset_group.name = name
        asset_group.final_urls.append(final_url)
        asset_group.status = get_enum_value(client, "AssetGroupStatusEnum", "ENABLED")

        if path1:
            asset_group.path1 = path1
        if path2:
            asset_group.path2 = path2

        mutate_operations.append(asset_group_op)

        # 2. Create headline assets
        asset_service = client.get_service("AssetService")
        for i, headline in enumerate(headlines):
            asset_op = client.get_type("MutateOperation")
            asset = asset_op.asset_operation.create
            asset.resource_name = asset_service.asset_path(
                customer_id, headline_temp_ids[i]
            )
            asset.text_asset.text = headline
            mutate_operations.append(asset_op)

        # 3. Create description assets
        for i, description in enumerate(descriptions):
            asset_op = client.get_type("MutateOperation")
            asset = asset_op.asset_operation.create
            asset.resource_name = asset_service.asset_path(
                customer_id, description_temp_ids[i]
            )
            asset.text_asset.text = description
            mutate_operations.append(asset_op)

        # 4. Create business name asset if provided
        business_name_temp_id = -300
        if business_name:
            bn_op = client.get_type("MutateOperation")
            bn_asset = bn_op.asset_operation.create
            bn_asset.resource_name = asset_service.asset_path(
                customer_id, business_name_temp_id
            )
            bn_asset.text_asset.text = business_name
            mutate_operations.append(bn_op)

        # 5. Link headlines to asset group
        for temp_id in headline_temp_ids:
            link_op = client.get_type("MutateOperation")
            aga = link_op.asset_group_asset_operation.create
            aga.asset_group = asset_group_service.asset_group_path(
                customer_id, asset_group_temp_id
            )
            aga.asset = asset_service.asset_path(customer_id, temp_id)
            aga.field_type = get_enum_value(client, "AssetFieldTypeEnum", "HEADLINE")
            mutate_operations.append(link_op)

        # 6. Link descriptions to asset group
        for temp_id in description_temp_ids:
            link_op = client.get_type("MutateOperation")
            aga = link_op.asset_group_asset_operation.create
            aga.asset_group = asset_group_service.asset_group_path(
                customer_id, asset_group_temp_id
            )
            aga.asset = asset_service.asset_path(customer_id, temp_id)
            aga.field_type = get_enum_value(client, "AssetFieldTypeEnum", "DESCRIPTION")
            mutate_operations.append(link_op)

        # 7. Link business name to asset group
        if business_name:
            bn_link_op = client.get_type("MutateOperation")
            bn_aga = bn_link_op.asset_group_asset_operation.create
            bn_aga.asset_group = asset_group_service.asset_group_path(
                customer_id, asset_group_temp_id
            )
            bn_aga.asset = asset_service.asset_path(customer_id, business_name_temp_id)
            bn_aga.field_type = get_enum_value(
                client, "AssetFieldTypeEnum", "BUSINESS_NAME"
            )
            mutate_operations.append(bn_link_op)

        # Execute atomic bulk mutate
        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=mutate_operations,
        )

        # Extract the created asset group resource name from response
        asset_group_resource_name = None
        for result in response.mutate_operation_responses:
            if result.HasField("asset_group_result"):
                asset_group_resource_name = result.asset_group_result.resource_name
                break

        asset_group_id = (
            asset_group_resource_name.split("/")[-1]
            if asset_group_resource_name
            else None
        )

        return {
            "asset_group_id": asset_group_id,
            "asset_group_resource_name": asset_group_resource_name,
            "headline_count": len(headlines),
            "description_count": len(descriptions),
            "business_name_added": business_name is not None,
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_add_asset_group_asset(
    asset_group_id: str,
    asset_resource_name: str,
    field_type: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Links an existing asset to an asset group.

    Use this to add image assets to an asset group after creation.
    For Performance Max campaigns, you need at least:
    - MARKETING_IMAGE: Landscape marketing images (1.91:1 ratio, 1200x628)
    - SQUARE_MARKETING_IMAGE: Square marketing images (1:1 ratio, 1200x1200)
    - LOGO: Logo images (1:1 ratio, 1200x1200)

    Args:
        asset_group_id: The asset group ID to add the asset to.
        asset_resource_name: Full resource name of the asset to link.
        field_type: The field type for the asset. Options:
            - HEADLINE: Headline text
            - DESCRIPTION: Description text
            - BUSINESS_NAME: Business name
            - MARKETING_IMAGE: Landscape marketing image (1.91:1)
            - SQUARE_MARKETING_IMAGE: Square marketing image (1:1)
            - PORTRAIT_MARKETING_IMAGE: Portrait marketing image (4:5)
            - LOGO: Logo image (1:1)
            - LANDSCAPE_LOGO: Landscape logo (4:1)
            - YOUTUBE_VIDEO: YouTube video
            - CALL_TO_ACTION_SELECTION: CTA selection
            - LONG_HEADLINE: Long headline (max 90 chars)
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Link result:
            - asset_group_asset_resource_name: The created link resource name
            - status: Link status

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_group_asset_service = client.get_service("AssetGroupAssetService")
        asset_group_service = client.get_service("AssetGroupService")

        # Get asset group resource name
        asset_group_resource = asset_group_service.asset_group_path(
            customer_id, asset_group_id
        )

        # Create asset group asset link
        operation = client.get_type("AssetGroupAssetOperation")
        aga = operation.create
        aga.asset_group = asset_group_resource
        aga.asset = asset_resource_name
        aga.field_type = get_enum_value(
            client, "AssetFieldTypeEnum", field_type.upper()
        )

        response = asset_group_asset_service.mutate_asset_group_assets(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "asset_group_asset_resource_name": response.results[0].resource_name,
            "status": "linked",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_update_asset_group(
    asset_group_id: str,
    customer_id: Optional[str] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    final_url: Optional[str] = None,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Updates an existing asset group.

    Args:
        asset_group_id: The asset group ID to update.
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        name: Optional new name for the asset group.
        status: Optional new status - ENABLED, PAUSED, or REMOVED.
        final_url: Optional new final URL.
        path1: Optional new display URL path 1.
        path2: Optional new display URL path 2.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Update result:
            - asset_group_resource_name: Full resource name
            - updated_fields: List of fields that were updated
            - status: Update status

    Raises:
        ToolError: If no fields to update or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_group_service = client.get_service("AssetGroupService")
        operation = client.get_type("AssetGroupOperation")
        asset_group = operation.update
        asset_group.resource_name = asset_group_service.asset_group_path(
            customer_id, asset_group_id
        )

        field_mask = []

        if name is not None:
            asset_group.name = name
            field_mask.append("name")

        if status is not None:
            asset_group.status = get_enum_value(
                client, "AssetGroupStatusEnum", status.upper()
            )
            field_mask.append("status")

        if final_url is not None:
            asset_group.final_urls.clear()
            asset_group.final_urls.append(final_url)
            field_mask.append("final_urls")

        if path1 is not None:
            asset_group.path1 = path1
            field_mask.append("path1")

        if path2 is not None:
            asset_group.path2 = path2
            field_mask.append("path2")

        if not field_mask:
            raise ToolError("No fields to update. Provide at least one field.")

        operation.update_mask.paths.extend(field_mask)

        response = asset_group_service.mutate_asset_groups(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "asset_group_resource_name": response.results[0].resource_name,
            "updated_fields": field_mask,
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_delete_asset_group(
    asset_group_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes an asset group from a Performance Max campaign.

    Note: This sets the asset group status to REMOVED. The data is retained
    but the asset group cannot be reactivated.

    Args:
        asset_group_id: The asset group ID to remove.
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal status:
            - asset_group_resource_name: Full resource name
            - status: "removed"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_group_service = client.get_service("AssetGroupService")
        operation = client.get_type("AssetGroupOperation")
        operation.remove = asset_group_service.asset_group_path(
            customer_id, asset_group_id
        )

        response = asset_group_service.mutate_asset_groups(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "asset_group_resource_name": response.results[0].resource_name,
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_remove_asset_group_asset(
    asset_group_id: str,
    asset_resource_name: str,
    field_type: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes an asset link from an asset group.

    This unlinks an asset from the asset group but does not delete the asset itself.

    Args:
        asset_group_id: The asset group ID.
        asset_resource_name: Full resource name of the asset to unlink.
        field_type: The field type of the asset link to remove.
        customer_id: The Google Ads customer ID.
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal status:
            - status: "removed"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        asset_group_asset_service = client.get_service("AssetGroupAssetService")
        asset_group_service = client.get_service("AssetGroupService")

        # Build the resource name for the asset group asset
        asset_group_resource = asset_group_service.asset_group_path(
            customer_id, asset_group_id
        )

        # We need to find the exact asset group asset resource name
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT asset_group_asset.resource_name
            FROM asset_group_asset
            WHERE asset_group_asset.asset_group = '{asset_group_resource}'
            AND asset_group_asset.asset = '{asset_resource_name}'
            AND asset_group_asset.field_type = '{field_type.upper()}'
        """

        response = ga_service.search(customer_id=customer_id, query=query)

        aga_resource_name = None
        for row in response:
            aga_resource_name = row.asset_group_asset.resource_name
            break

        if not aga_resource_name:
            raise ToolError(
                f"Asset link not found for asset {asset_resource_name} in asset group {asset_group_id}"
            )

        operation = client.get_type("AssetGroupAssetOperation")
        operation.remove = aga_resource_name

        asset_group_asset_service.mutate_asset_group_assets(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
