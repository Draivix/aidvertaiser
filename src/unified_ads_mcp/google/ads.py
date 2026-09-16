"""Ad management tools for Google Ads API.

This module provides MCP tools for managing Google Ads including
listing, creating, updating, and deleting ads within ad groups.
"""

import json
from typing import Any, Optional

from google.ads.googleads.errors import GoogleAdsException
from mcp.server.fastmcp.exceptions import ToolError

from ..server import mcp
from .client import (
    get_google_ads_client,
    format_error,
    resolve_customer_id,
    get_enum_name,
    get_enum_value,
    micros_to_currency,
)


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


@mcp.tool()
def google_list_ads(
    customer_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    status: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists ads for a Google Ads customer with performance metrics.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: Optional ad group ID to filter ads.
        status: Optional filter by status - ENABLED, PAUSED, or REMOVED.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of ads with:
            - id: Ad ID
            - ad_group_id: Parent ad group ID
            - ad_group_name: Parent ad group name
            - status: Ad status
            - type: Ad type (RESPONSIVE_SEARCH_AD, etc.)
            - final_urls: List of final URLs
            - impressions: Total impressions
            - clicks: Total clicks
            - cost: Total cost in account currency
            - conversions: Total conversions

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
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.ad.final_urls,
                ad_group_ad.status,
                ad_group_ad.ad.responsive_search_ad.headlines,
                ad_group_ad.ad.responsive_search_ad.descriptions,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM ad_group_ad
        """

        conditions = []
        if ad_group_id:
            conditions.append(f"ad_group.id = {ad_group_id}")
        if status:
            conditions.append(f"ad_group_ad.status = '{status.upper()}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY ad_group_ad.ad.id"

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        ads = []
        for batch in response:
            for row in batch.results:
                ad_type = get_enum_name(client, "AdTypeEnum", row.ad_group_ad.ad.type_)
                ad_data = {
                    "id": str(row.ad_group_ad.ad.id),
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "status": get_enum_name(
                        client, "AdGroupAdStatusEnum", row.ad_group_ad.status
                    ),
                    "type": ad_type,
                    "final_urls": list(row.ad_group_ad.ad.final_urls),
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": micros_to_currency(row.metrics.cost_micros),
                    "conversions": row.metrics.conversions,
                }

                # Add RSA-specific fields if it's a responsive search ad
                if ad_type == "RESPONSIVE_SEARCH_AD":
                    rsa = row.ad_group_ad.ad.responsive_search_ad
                    ad_data["headlines"] = [h.text for h in rsa.headlines]
                    ad_data["descriptions"] = [d.text for d in rsa.descriptions]

                ads.append(ad_data)

        return ads

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_get_ad(
    ad_group_id: str,
    ad_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Gets detailed information about a specific ad.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: The ad group ID containing the ad.
        ad_id: The ad ID to retrieve.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Ad details including:
            - id: Ad ID
            - ad_group_id: Parent ad group ID
            - status: Ad status
            - type: Ad type
            - final_urls: List of final URLs
            - headlines: List of headlines (for RSA)
            - descriptions: List of descriptions (for RSA)
            - impressions, clicks, cost, conversions: Metrics

    Raises:
        ToolError: If the ad is not found or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        query = f"""
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.ad.final_urls,
                ad_group_ad.ad.final_mobile_urls,
                ad_group_ad.ad.tracking_url_template,
                ad_group_ad.status,
                ad_group_ad.ad.responsive_search_ad.headlines,
                ad_group_ad.ad.responsive_search_ad.descriptions,
                ad_group_ad.ad.responsive_search_ad.path1,
                ad_group_ad.ad.responsive_search_ad.path2,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.ctr,
                metrics.average_cpc
            FROM ad_group_ad
            WHERE ad_group.id = {ad_group_id} AND ad_group_ad.ad.id = {ad_id}
        """

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        for batch in response:
            for row in batch.results:
                ad_type = get_enum_name(client, "AdTypeEnum", row.ad_group_ad.ad.type_)
                ad_data = {
                    "id": str(row.ad_group_ad.ad.id),
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "status": get_enum_name(
                        client, "AdGroupAdStatusEnum", row.ad_group_ad.status
                    ),
                    "type": ad_type,
                    "final_urls": list(row.ad_group_ad.ad.final_urls),
                    "final_mobile_urls": list(row.ad_group_ad.ad.final_mobile_urls),
                    "tracking_url_template": row.ad_group_ad.ad.tracking_url_template
                    or None,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": micros_to_currency(row.metrics.cost_micros),
                    "conversions": row.metrics.conversions,
                    "ctr": row.metrics.ctr,
                    "average_cpc": micros_to_currency(row.metrics.average_cpc),
                }

                # Add RSA-specific fields
                if ad_type == "RESPONSIVE_SEARCH_AD":
                    rsa = row.ad_group_ad.ad.responsive_search_ad
                    ad_data["headlines"] = [
                        {
                            "text": h.text,
                            "pinned_field": get_enum_name(
                                client, "ServedAssetFieldTypeEnum", h.pinned_field
                            )
                            if h.pinned_field
                            else None,
                        }
                        for h in rsa.headlines
                    ]
                    ad_data["descriptions"] = [
                        {
                            "text": d.text,
                            "pinned_field": get_enum_name(
                                client, "ServedAssetFieldTypeEnum", d.pinned_field
                            )
                            if d.pinned_field
                            else None,
                        }
                        for d in rsa.descriptions
                    ]
                    ad_data["path1"] = rsa.path1 or None
                    ad_data["path2"] = rsa.path2 or None

                return ad_data

        raise ToolError(f"Ad {ad_id} not found in ad group {ad_group_id}")

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_responsive_search_ad(
    ad_group_id: str,
    headlines: Any,
    descriptions: Any,
    final_urls: Any,
    customer_id: Optional[str] = None,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    status: str = "ENABLED",
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a new Responsive Search Ad (RSA).

    Responsive Search Ads automatically test different combinations
    of headlines and descriptions to find the best performing ads.

    Args:
        ad_group_id: The ad group ID to add the ad to.
        headlines: List of headline texts (3-15 required, max 30 chars each).
        descriptions: List of description texts (2-4 required, max 90 chars each).
        final_urls: List of final landing page URLs.
        customer_id: The Google Ads customer ID. Uses default from config if not provided.
        path1: Optional display path 1 (max 15 chars).
        path2: Optional display path 2 (max 15 chars, requires path1).
        status: Initial status - ENABLED (default) or PAUSED.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created ad details:
            - ad_id: The new ad ID
            - ad_resource_name: Full resource name
            - status: Creation status

    Raises:
        ToolError: If validation fails or API request fails.
    """
    headlines = _coerce_list(headlines)
    descriptions = _coerce_list(descriptions)
    final_urls = _coerce_list(final_urls)

    # Validate inputs
    if len(headlines) < 3:
        raise ToolError("At least 3 headlines are required for Responsive Search Ads")
    if len(headlines) > 15:
        raise ToolError("Maximum 15 headlines allowed for Responsive Search Ads")
    if len(descriptions) < 2:
        raise ToolError(
            "At least 2 descriptions are required for Responsive Search Ads"
        )
    if len(descriptions) > 4:
        raise ToolError("Maximum 4 descriptions allowed for Responsive Search Ads")
    if not final_urls:
        raise ToolError("At least one final URL is required")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_ad_service = client.get_service("AdGroupAdService")
        ad_group_ad_operation = client.get_type("AdGroupAdOperation")
        ad_group_ad = ad_group_ad_operation.create

        ad_group_ad.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
        ad_group_ad.status = get_enum_value(client, "AdGroupAdStatusEnum", status)

        # Set up the responsive search ad
        ad = ad_group_ad.ad
        ad.final_urls.extend(final_urls)

        rsa = ad.responsive_search_ad

        # Add headlines
        for headline_text in headlines:
            headline = client.get_type("AdTextAsset")
            headline.text = headline_text
            rsa.headlines.append(headline)

        # Add descriptions
        for desc_text in descriptions:
            description = client.get_type("AdTextAsset")
            description.text = desc_text
            rsa.descriptions.append(description)

        # Set display paths
        if path1:
            rsa.path1 = path1
        if path2:
            rsa.path2 = path2

        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id,
            operations=[ad_group_ad_operation],
        )

        resource_name = response.results[0].resource_name
        # Extract ad ID from resource name: customers/{customer_id}/adGroupAds/{ad_group_id}~{ad_id}
        ad_id = resource_name.split("~")[-1]

        return {
            "ad_id": ad_id,
            "ad_resource_name": resource_name,
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_update_ad(
    ad_group_id: str,
    ad_id: str,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    headlines: Optional[Any] = None,
    descriptions: Optional[Any] = None,
    final_urls: Optional[Any] = None,
    final_mobile_urls: Optional[Any] = None,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    tracking_url_template: Optional[str] = None,
    final_url_suffix: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Updates an ad's status and/or content (headlines, descriptions, URLs).

    For Responsive Search Ads, content fields (headlines, descriptions, URLs,
    paths) are updated via the AdService which preserves performance history.
    Status is updated via the AdGroupAdService.

    Content updates replace the full field value — provide ALL headlines/
    descriptions you want the ad to have, not just changes.

    Args:
        ad_group_id: The ad group ID containing the ad.
        ad_id: The ad ID to update.
        customer_id: The Google Ads customer ID. Uses default from config if not provided.
        status: Optional new status - ENABLED, PAUSED, or REMOVED.
        headlines: Optional list of new headline texts (3-15, max 30 chars each).
            Replaces all existing headlines.
        descriptions: Optional list of new description texts (2-4, max 90 chars each).
            Replaces all existing descriptions.
        final_urls: Optional list of new final landing page URLs.
        final_mobile_urls: Optional list of new mobile final URLs.
        path1: Optional new display path 1 (max 15 chars). Pass empty string to clear.
        path2: Optional new display path 2 (max 15 chars, requires path1).
            Pass empty string to clear.
        tracking_url_template: Optional new tracking URL template.
            Pass empty string to clear.
        final_url_suffix: Optional new final URL suffix. Pass empty string to clear.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Updated ad details:
            - ad_resource_name: Full resource name
            - status_updated: Whether status was changed
            - content_updated: Whether ad content was changed
            - fields_updated: List of fields that were updated

    Raises:
        ToolError: If the API request fails or validation fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        has_content_update = any(
            v is not None
            for v in [
                headlines,
                descriptions,
                final_urls,
                final_mobile_urls,
                path1,
                path2,
                tracking_url_template,
                final_url_suffix,
            ]
        )

        if not status and not has_content_update:
            raise ToolError(
                "Nothing to update. Provide status and/or content fields "
                "(headlines, descriptions, final_urls, etc.)"
            )

        fields_updated = []
        result: dict[str, Any] = {
            "status_updated": False,
            "content_updated": False,
            "fields_updated": fields_updated,
        }

        # --- Status update via AdGroupAdService ---
        if status:
            ad_group_ad_service = client.get_service("AdGroupAdService")
            ad_group_ad_operation = client.get_type("AdGroupAdOperation")
            ad_group_ad = ad_group_ad_operation.update
            ad_group_ad.resource_name = (
                f"customers/{customer_id}/adGroupAds/{ad_group_id}~{ad_id}"
            )
            ad_group_ad.status = get_enum_value(
                client, "AdGroupAdStatusEnum", status
            )
            ad_group_ad_operation.update_mask.paths.append("status")

            response = ad_group_ad_service.mutate_ad_group_ads(
                customer_id=customer_id,
                operations=[ad_group_ad_operation],
            )
            result["ad_resource_name"] = response.results[0].resource_name
            result["status_updated"] = True
            fields_updated.append("status")

        # --- Content update via AdService ---
        if has_content_update:
            ad_service = client.get_service("AdService")
            ad_operation = client.get_type("AdOperation")
            ad = ad_operation.update
            ad.resource_name = ad_service.ad_path(customer_id, ad_id)

            if headlines is not None:
                headlines = _coerce_list(headlines)
                if len(headlines) < 3:
                    raise ToolError("At least 3 headlines required")
                if len(headlines) > 15:
                    raise ToolError("Maximum 15 headlines allowed")
                for text in headlines:
                    asset = client.get_type("AdTextAsset")
                    asset.text = text
                    ad.responsive_search_ad.headlines.append(asset)
                fields_updated.append("headlines")

            if descriptions is not None:
                descriptions = _coerce_list(descriptions)
                if len(descriptions) < 2:
                    raise ToolError("At least 2 descriptions required")
                if len(descriptions) > 4:
                    raise ToolError("Maximum 4 descriptions allowed")
                for text in descriptions:
                    asset = client.get_type("AdTextAsset")
                    asset.text = text
                    ad.responsive_search_ad.descriptions.append(asset)
                fields_updated.append("descriptions")

            if final_urls is not None:
                final_urls = _coerce_list(final_urls)
                if not final_urls:
                    raise ToolError("At least one final URL required")
                ad.final_urls.extend(final_urls)
                fields_updated.append("final_urls")

            if final_mobile_urls is not None:
                final_mobile_urls = _coerce_list(final_mobile_urls)
                ad.final_mobile_urls.extend(final_mobile_urls)
                fields_updated.append("final_mobile_urls")

            if path1 is not None:
                ad.responsive_search_ad.path1 = path1
                fields_updated.append("path1")

            if path2 is not None:
                ad.responsive_search_ad.path2 = path2
                fields_updated.append("path2")

            if tracking_url_template is not None:
                ad.tracking_url_template = tracking_url_template
                fields_updated.append("tracking_url_template")

            if final_url_suffix is not None:
                ad.final_url_suffix = final_url_suffix
                fields_updated.append("final_url_suffix")

            # Build field mask from explicitly updated fields
            mask_paths = []
            if final_urls is not None:
                mask_paths.append("final_urls")
            if final_mobile_urls is not None:
                mask_paths.append("final_mobile_urls")
            if tracking_url_template is not None:
                mask_paths.append("tracking_url_template")
            if final_url_suffix is not None:
                mask_paths.append("final_url_suffix")
            if headlines is not None:
                mask_paths.append("responsive_search_ad.headlines")
            if descriptions is not None:
                mask_paths.append("responsive_search_ad.descriptions")
            if path1 is not None:
                mask_paths.append("responsive_search_ad.path1")
            if path2 is not None:
                mask_paths.append("responsive_search_ad.path2")
            ad_operation.update_mask.paths.extend(mask_paths)

            ad_service.mutate_ads(
                customer_id=customer_id,
                operations=[ad_operation],
            )
            result["ad_resource_name"] = ad.resource_name
            result["content_updated"] = True

        return result

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_delete_ad(
    ad_group_id: str,
    ad_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes an ad.

    Note: This sets the ad status to REMOVED. The ad data
    is retained and can still be queried but cannot be reactivated.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: The ad group ID containing the ad.
        ad_id: The ad ID to remove.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal status:
            - ad_resource_name: Full resource name
            - status: "removed"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_ad_service = client.get_service("AdGroupAdService")
        ad_group_ad_operation = client.get_type("AdGroupAdOperation")
        ad_group_ad_operation.remove = (
            f"customers/{customer_id}/adGroupAds/{ad_group_id}~{ad_id}"
        )

        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id,
            operations=[ad_group_ad_operation],
        )

        return {
            "ad_resource_name": response.results[0].resource_name,
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_set_demographic_exclusions(
    ad_group_id: str,
    exclusions: list[dict[str, str]],
    customer_id: Optional[str] = None,
    replace_existing: bool = True,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Adds negative demographic criteria to an ad group (age, gender, income).

    Search campaigns require ad group level targeting, not campaign level.
    Use this to exclude age ranges, genders, or income ranges from seeing ads.

    Args:
        ad_group_id: The ad group ID to modify.
        exclusions: List of exclusion objects, each with:
            - type: "AGE_RANGE", "GENDER", or "INCOME_RANGE"
            - value: The enum value name, e.g.:
              Age: AGE_RANGE_18_24, AGE_RANGE_25_34, AGE_RANGE_35_44,
                   AGE_RANGE_45_54, AGE_RANGE_55_64, AGE_RANGE_65_UP,
                   AGE_RANGE_UNDETERMINED
              Gender: MALE, FEMALE, UNDETERMINED
              Income: INCOME_RANGE_0_50, INCOME_RANGE_50_60, INCOME_RANGE_60_70,
                      INCOME_RANGE_70_80, INCOME_RANGE_80_90, INCOME_RANGE_90_UP,
                      INCOME_RANGE_UNDETERMINED
        customer_id: The Google Ads customer ID. Uses default if not provided.
        replace_existing: If True (default), removes existing negative demographic
            criteria of the same types before adding new ones.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Result with exclusions_added and exclusions_removed counts.

    Example - B2B targeting (exclude under-25 and undetermined age):
        exclusions=[
            {"type": "AGE_RANGE", "value": "AGE_RANGE_18_24"},
            {"type": "AGE_RANGE", "value": "AGE_RANGE_UNDETERMINED"},
        ]
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_resource = f"customers/{customer_id}/adGroups/{ad_group_id}"
        criterion_service = client.get_service("AdGroupCriterionService")
        removed_count = 0

        # Determine which demographic types we're setting
        types_to_set = {e["type"].upper() for e in exclusions}
        type_to_gaql = {
            "AGE_RANGE": "AGE_RANGE",
            "GENDER": "GENDER",
            "INCOME_RANGE": "INCOME_RANGE",
        }

        # Remove existing criteria (both negative and observation) for the same types.
        # Non-negative (observation) criteria must be removed first, otherwise
        # creating a negative criterion fails with CRITERION_ALREADY_EXISTS.
        if replace_existing and types_to_set:
            ga_service = client.get_service("GoogleAdsService")
            type_values = [f"'{type_to_gaql[t]}'" for t in types_to_set if t in type_to_gaql]
            query = f"""
                SELECT ad_group_criterion.resource_name, ad_group_criterion.type
                FROM ad_group_criterion
                WHERE ad_group.id = {ad_group_id}
                  AND ad_group_criterion.type IN ({', '.join(type_values)})
            """
            response = ga_service.search_stream(
                customer_id=customer_id, query=query
            )
            remove_ops = []
            for batch in response:
                for row in batch.results:
                    op = client.get_type("AdGroupCriterionOperation")
                    op.remove = row.ad_group_criterion.resource_name
                    remove_ops.append(op)

            if remove_ops:
                criterion_service.mutate_ad_group_criteria(
                    customer_id=customer_id, operations=remove_ops
                )
                removed_count = len(remove_ops)

        # Add new negative criteria
        add_ops = []
        for excl in exclusions:
            excl_type = excl["type"].upper()
            excl_value = excl["value"].upper()

            op = client.get_type("AdGroupCriterionOperation")
            criterion = op.create
            criterion.ad_group = ad_group_resource
            criterion.negative = True

            if excl_type == "AGE_RANGE":
                criterion.age_range.type_ = get_enum_value(
                    client, "AgeRangeTypeEnum", excl_value
                )
            elif excl_type == "GENDER":
                criterion.gender.type_ = get_enum_value(
                    client, "GenderTypeEnum", excl_value
                )
            elif excl_type == "INCOME_RANGE":
                criterion.income_range.type_ = get_enum_value(
                    client, "IncomeRangeTypeEnum", excl_value
                )
            else:
                raise ToolError(
                    f"Invalid exclusion type '{excl_type}'. "
                    "Options: AGE_RANGE, GENDER, INCOME_RANGE"
                )
            add_ops.append(op)

        if add_ops:
            criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id, operations=add_ops
            )

        return {
            "ad_group_id": ad_group_id,
            "exclusions_added": len(add_ops),
            "exclusions_removed": removed_count,
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
