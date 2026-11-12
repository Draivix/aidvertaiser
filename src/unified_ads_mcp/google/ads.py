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
    currency_to_micros,
)
from .assets import _YOUTUBE_ID


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
                ad_group_ad.ad.demand_gen_video_responsive_ad.headlines,
                ad_group_ad.ad.demand_gen_video_responsive_ad.long_headlines,
                ad_group_ad.ad.demand_gen_video_responsive_ad.descriptions,
                ad_group_ad.ad.demand_gen_video_responsive_ad.business_name,
                ad_group_ad.ad.demand_gen_video_responsive_ad.videos,
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
                elif ad_type == "DEMAND_GEN_VIDEO_RESPONSIVE_AD":
                    dg = row.ad_group_ad.ad.demand_gen_video_responsive_ad
                    ad_data["headlines"] = [h.text for h in dg.headlines]
                    ad_data["long_headlines"] = [h.text for h in dg.long_headlines]
                    ad_data["descriptions"] = [d.text for d in dg.descriptions]
                    ad_data["business_name"] = dg.business_name.text or None
                    ad_data["video_asset_ids"] = [v.asset.split("/")[-1] for v in dg.videos]

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


_AD_TYPE_FIELD = {
    "RESPONSIVE_SEARCH_AD": "responsive_search_ad",
    "DEMAND_GEN_VIDEO_RESPONSIVE_AD": "demand_gen_video_responsive_ad",
}

# (min items, max items, max characters) per text field and ad type.
_TEXT_LIMITS = {
    "responsive_search_ad": {"headlines": (3, 15, 30), "descriptions": (2, 4, 90)},
    "demand_gen_video_responsive_ad": {
        "headlines": (1, 5, 40),
        "long_headlines": (1, 5, 90),
        "descriptions": (1, 5, 90),
    },
}


def _checked_texts(field: str, values: Any, limits: tuple[int, int, int]) -> list[str]:
    """Coerce and validate one text-asset list against (min, max, max chars)."""
    values = _coerce_list(values)
    low, high, max_len = limits
    if not low <= len(values) <= high:
        raise ToolError(f"{field}: {low}-{high} items required, got {len(values)}")
    too_long = [v for v in values if len(v) > max_len]
    if too_long:
        raise ToolError(f"{field}: over {max_len} characters: {too_long}")
    return values


def _youtube_ids(videos: Any) -> list[str]:
    """Extract 1-5 YouTube video IDs from URLs or bare IDs."""
    ids = []
    for video in _coerce_list(videos):
        match = _YOUTUBE_ID.search(video.strip())
        if not match:
            raise ToolError(f"Not a YouTube URL or video ID: {video!r}")
        ids.append(match.group(1))
    if not 1 <= len(ids) <= 5:
        raise ToolError(f"youtube_videos: 1-5 videos per ad required, got {len(ids)}")
    return ids


def _video_asset_names(client, customer_id: str, video_ids: list[str], new_op, label: str) -> list[str]:
    """Resource names of YOUTUBE_VIDEO assets, reusing existing ones.

    Videos without an asset get an asset create operation with a temporary
    resource name, so they must run in the same mutate request as the ad.
    """
    quoted = ", ".join(f"'{v}'" for v in video_ids)
    query = f"""
        SELECT asset.resource_name, asset.youtube_video_asset.youtube_video_id
        FROM asset
        WHERE asset.type = YOUTUBE_VIDEO
          AND asset.youtube_video_asset.youtube_video_id IN ({quoted})
    """
    existing: dict[str, str] = {}
    ga_service = client.get_service("GoogleAdsService")
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            existing.setdefault(row.asset.youtube_video_asset.youtube_video_id, row.asset.resource_name)
    names = []
    for index, video_id in enumerate(video_ids):
        if video_id not in existing:
            asset = new_op().asset_operation.create
            asset.resource_name = f"customers/{customer_id}/assets/{-10 - index}"
            asset.youtube_video_asset.youtube_video_id = video_id
            asset.name = f"{label} - video {index + 1} ({video_id})"
            existing[video_id] = asset.resource_name
        names.append(existing[video_id])
    return names


def _set_videos(client, info, asset_names: list[str]) -> None:
    del info.videos[:]
    for name in asset_names:
        video = client.get_type("AdVideoAsset")
        video.asset = name
        info.videos.append(video)


def _set_texts(client, info, field: str, values: list[str]) -> None:
    target = getattr(info, field)
    del target[:]
    for text in values:
        text_asset = client.get_type("AdTextAsset")
        text_asset.text = text
        target.append(text_asset)


def _ad_id_int(value: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ToolError(f"{field} must be a numeric ID, got {value!r}") from None


def _fetch_ad(client, customer_id: str, ad_group_id: str, ad_id: str):
    """The ad row (ad type, URLs, Demand Gen video content) or ToolError."""
    query = f"""
        SELECT
            ad_group_ad.ad.type,
            ad_group_ad.ad.final_urls,
            ad_group_ad.ad.demand_gen_video_responsive_ad.headlines,
            ad_group_ad.ad.demand_gen_video_responsive_ad.long_headlines,
            ad_group_ad.ad.demand_gen_video_responsive_ad.descriptions,
            ad_group_ad.ad.demand_gen_video_responsive_ad.business_name,
            ad_group_ad.ad.demand_gen_video_responsive_ad.logo_images,
            ad_group_ad.ad.demand_gen_video_responsive_ad.call_to_actions,
            ad_group_ad.ad.demand_gen_video_responsive_ad.breadcrumb1,
            ad_group_ad.ad.demand_gen_video_responsive_ad.breadcrumb2
        FROM ad_group_ad
        WHERE ad_group.id = {_ad_id_int(ad_group_id, "ad_group_id")}
          AND ad_group_ad.ad.id = {_ad_id_int(ad_id, "ad_id")}
    """
    ga_service = client.get_service("GoogleAdsService")
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            return row.ad_group_ad.ad
    raise ToolError(f"Ad {ad_id} not found in ad group {ad_group_id}")


def _run_mutate(client, customer_id: str, operations: list, validate_only: bool):
    request = client.get_type("MutateGoogleAdsRequest")
    request.customer_id = customer_id
    request.mutate_operations.extend(operations)
    request.validate_only = validate_only
    return client.get_service("GoogleAdsService").mutate(request=request)


@mcp.tool()
def google_update_ad(
    ad_group_id: str,
    ad_id: str,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    headlines: Optional[Any] = None,
    descriptions: Optional[Any] = None,
    long_headlines: Optional[Any] = None,
    youtube_videos: Optional[Any] = None,
    business_name: Optional[str] = None,
    final_urls: Optional[Any] = None,
    final_mobile_urls: Optional[Any] = None,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    tracking_url_template: Optional[str] = None,
    final_url_suffix: Optional[str] = None,
    validate_only: bool = False,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Edits an existing ad in place: status, texts, videos, URLs.

    Supported ad types for texts: Responsive Search Ads and Demand Gen video
    ads (YouTube Shorts/in-stream/in-feed, e.g. campaigns created with
    google_create_demand_gen_video_campaign). The ad keeps its ID and
    performance history. Everything runs in one atomic request.

    List fields replace the full value: pass ALL headlines/videos the ad
    should have, not just the new ones. A Demand Gen video ad holds at most
    5 videos; for more, add a second ad with google_create_demand_gen_video_ad.

    Run first with validate_only=True: Google checks the change, nothing is
    saved.

    Args:
        ad_group_id: The ad group ID containing the ad.
        ad_id: The ad ID to update.
        customer_id: The Google Ads customer ID. Uses default from config if not provided.
        status: Optional new status - ENABLED, PAUSED, or REMOVED.
        headlines: Optional new headlines. Search ad: 3-15, max 30 chars.
            Demand Gen video ad: 1-5, max 40 chars.
        descriptions: Optional new descriptions. Search ad: 2-4, max 90 chars.
            Demand Gen video ad: 1-5, max 90 chars.
        long_headlines: Demand Gen video ad only: 1-5, max 90 chars.
        youtube_videos: Demand Gen video ad only: 1-5 YouTube URLs or video IDs,
            the complete new video list (keep the current ones you want to stay;
            google_get_ad lists them). Existing video assets are reused.
        business_name: Demand Gen video ad only: max 25 chars.
        final_urls: Optional list of new final landing page URLs.
        final_mobile_urls: Optional list of new mobile final URLs.
        path1: Search ad only: display path 1 (max 15 chars). Empty string clears.
        path2: Search ad only: display path 2 (max 15 chars, requires path1).
        tracking_url_template: Optional new tracking URL template.
            Pass empty string to clear.
        final_url_suffix: Optional new final URL suffix. Pass empty string to clear.
        validate_only: True = Google validates the change, nothing is saved.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: ad_resource_name, ad_type, status_updated, content_updated,
            fields_updated, validated_only.

    Raises:
        ToolError: If the API request fails or validation fails.
    """
    typed_fields = {
        "headlines": headlines,
        "descriptions": descriptions,
        "long_headlines": long_headlines,
        "youtube_videos": youtube_videos,
        "business_name": business_name,
        "path1": path1,
        "path2": path2,
    }
    typed_fields = {k: v for k, v in typed_fields.items() if v is not None}
    generic_fields = {
        "final_urls": final_urls,
        "final_mobile_urls": final_mobile_urls,
        "tracking_url_template": tracking_url_template,
        "final_url_suffix": final_url_suffix,
    }
    generic_fields = {k: v for k, v in generic_fields.items() if v is not None}

    if not status and not typed_fields and not generic_fields:
        raise ToolError(
            "Nothing to update. Provide status and/or content fields "
            "(headlines, descriptions, youtube_videos, final_urls, etc.)"
        )

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        operations = []

        def new_op():
            op = client.get_type("MutateOperation")
            operations.append(op)
            return op

        fields_updated: list[str] = []
        ad_type = None

        if typed_fields or generic_fields:
            ad_operation = client.get_type("MutateOperation")
            ad = ad_operation.ad_operation.update
            ad.resource_name = f"customers/{customer_id}/ads/{_ad_id_int(ad_id, 'ad_id')}"
            mask = ad_operation.ad_operation.update_mask.paths

            if typed_fields:
                current = _fetch_ad(client, customer_id, ad_group_id, ad_id)
                ad_type = get_enum_name(client, "AdTypeEnum", current.type_)
                prefix = _AD_TYPE_FIELD.get(ad_type)
                if not prefix:
                    raise ToolError(
                        f"Ad {ad_id} is {ad_type}; texts and videos can be edited "
                        f"only on {sorted(_AD_TYPE_FIELD)}"
                    )
                info = getattr(ad, prefix)
                limits = _TEXT_LIMITS[prefix]
                for field, value in typed_fields.items():
                    if field in limits:
                        _set_texts(client, info, field, _checked_texts(field, value, limits[field]))
                    elif prefix == "responsive_search_ad" and field in ("path1", "path2"):
                        setattr(info, field, value)
                    elif prefix == "demand_gen_video_responsive_ad" and field == "business_name":
                        if not 1 <= len(value) <= 25:
                            raise ToolError("business_name: 1-25 characters required")
                        info.business_name.text = value
                        field = "business_name.text"
                    elif prefix == "demand_gen_video_responsive_ad" and field == "youtube_videos":
                        names = _video_asset_names(
                            client, customer_id, _youtube_ids(value), new_op, f"Ad {ad_id}"
                        )
                        _set_videos(client, info, names)
                        field = "videos"
                    else:
                        raise ToolError(f"{field} does not apply to {ad_type}")
                    mask.append(f"{prefix}.{field}")
                    fields_updated.append(field)

            for field, value in generic_fields.items():
                if field in ("final_urls", "final_mobile_urls"):
                    values = _coerce_list(value)
                    if field == "final_urls" and not values:
                        raise ToolError("At least one final URL required")
                    getattr(ad, field).extend(values)
                else:
                    setattr(ad, field, value)
                mask.append(field)
                fields_updated.append(field)

            operations.append(ad_operation)

        if status:
            ad_group_ad_operation = new_op().ad_group_ad_operation
            ad_group_ad = ad_group_ad_operation.update
            ad_group_ad.resource_name = (
                f"customers/{customer_id}/adGroupAds/"
                f"{_ad_id_int(ad_group_id, 'ad_group_id')}~{_ad_id_int(ad_id, 'ad_id')}"
            )
            ad_group_ad.status = get_enum_value(client, "AdGroupAdStatusEnum", status)
            ad_group_ad_operation.update_mask.paths.append("status")
            fields_updated.append("status")

        _run_mutate(client, customer_id, operations, validate_only)
        return {
            "ad_resource_name": f"customers/{customer_id}/ads/{ad_id}",
            "ad_type": ad_type,
            "status_updated": bool(status) and not validate_only,
            "content_updated": bool(typed_fields or generic_fields) and not validate_only,
            "fields_updated": fields_updated,
            "validated_only": validate_only,
        }

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


_DEMAND_GEN_CHANNELS = (
    "youtube_in_stream",
    "youtube_in_feed",
    "youtube_shorts",
    "discover",
    "gmail",
    "display",
    "maps",
)


@mcp.tool()
def google_create_demand_gen_video_campaign(
    name: str,
    budget: float,
    final_url: str,
    youtube_videos: Any,
    headlines: Any,
    long_headlines: Any,
    descriptions: Any,
    business_name: str,
    logo_asset_id: str,
    location_ids: Any,
    language_ids: Any = None,
    channels: Any = None,
    bidding: str = "MAXIMIZE_CLICKS",
    status: str = "PAUSED",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    validate_only: bool = False,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a complete YouTube video ad: Demand Gen campaign, ad group, video ad.

    This is the API route for YouTube ads (Shorts, in-stream, in-feed): the
    Google Ads API cannot create classic VIDEO campaigns, Demand Gen serves the
    same YouTube placements. Everything is created in one atomic request:
    budget, campaign, ad group (channels, locations, languages), one
    YOUTUBE_VIDEO asset per video and one Demand Gen video responsive ad.

    Run first with validate_only=True: Google checks the whole request and
    nothing is created or spent.

    Args:
        name: Campaign name (the ad group and ad reuse it).
        budget: Daily budget in account currency (e.g. 200 for 200 CZK).
        final_url: Landing page URL.
        youtube_videos: 1-5 YouTube URLs or video IDs. The videos must already
            be on YouTube (public or unlisted); the API cannot upload a file.
        headlines: 1-5 headlines, max 40 characters each.
        long_headlines: 1-5 long headlines, max 90 characters each.
        descriptions: 1-5 descriptions, max 90 characters each.
        business_name: Advertiser name, max 25 characters.
        logo_asset_id: ID of an existing square (1:1) IMAGE asset used as the
            logo; create it with google_create_image_asset.
        location_ids: Geo target constant IDs, required so the ad never runs
            worldwide by accident. "2203" = Czech Republic, "2703" = Slovakia.
        language_ids: Optional language IDs. "1021" = Czech, "1000" = English.
        channels: Where the ad may run. Default YouTube only:
            ["youtube_shorts", "youtube_in_stream", "youtube_in_feed"].
            Also "discover", "gmail", "display", "maps", or ["all"] for every
            Google channel.
        bidding: MAXIMIZE_CLICKS (default; needs no conversion tracking) or
            MAXIMIZE_CONVERSIONS (needs a working conversion action).
        status: Campaign status - PAUSED (default) or ENABLED.
        start_date: Optional start date YYYY-MM-DD.
        end_date: Optional end date YYYY-MM-DD.
        validate_only: True = Google validates the request, nothing is created.
        customer_id: Google Ads customer ID. Uses default from config if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: campaign_id, ad_group_id, ad_id, video_asset_ids, status
        ("validated" or "created").

    Raises:
        ToolError: If input is invalid or the API rejects the request.
    """
    limits = _TEXT_LIMITS["demand_gen_video_responsive_ad"]
    texts = {
        "headlines": _checked_texts("headlines", headlines, limits["headlines"]),
        "long_headlines": _checked_texts("long_headlines", long_headlines, limits["long_headlines"]),
        "descriptions": _checked_texts("descriptions", descriptions, limits["descriptions"]),
    }
    if not 1 <= len(business_name) <= 25:
        raise ToolError("business_name: 1-25 characters required")
    video_ids = _youtube_ids(youtube_videos)

    locations = _coerce_list(location_ids)
    if not locations:
        raise ToolError("location_ids is required (e.g. ['2203'] for Czech Republic)")
    languages = _coerce_list(language_ids) if language_ids else []

    selected = (
        _coerce_list(channels)
        if channels
        else ["youtube_shorts", "youtube_in_stream", "youtube_in_feed"]
    )
    unknown = [c for c in selected if c != "all" and c not in _DEMAND_GEN_CHANNELS]
    if unknown:
        raise ToolError(f"Unknown channels {unknown}; allowed: {_DEMAND_GEN_CHANNELS} or ['all']")

    bidding = bidding.upper()
    if bidding not in ("MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS"):
        raise ToolError("bidding must be MAXIMIZE_CLICKS or MAXIMIZE_CONVERSIONS")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        budget_rn = f"customers/{customer_id}/campaignBudgets/-1"
        campaign_rn = f"customers/{customer_id}/campaigns/-2"
        ad_group_rn = f"customers/{customer_id}/adGroups/-3"
        operations = []

        def new_op():
            op = client.get_type("MutateOperation")
            operations.append(op)
            return op

        campaign_budget = new_op().campaign_budget_operation.create
        campaign_budget.resource_name = budget_rn
        campaign_budget.name = f"{name} Budget"
        campaign_budget.amount_micros = currency_to_micros(budget)
        campaign_budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        campaign_budget.explicitly_shared = False

        campaign = new_op().campaign_operation.create
        campaign.resource_name = campaign_rn
        campaign.name = name
        campaign.campaign_budget = budget_rn
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.DEMAND_GEN
        campaign.status = get_enum_value(client, "CampaignStatusEnum", status)
        campaign.contains_eu_political_advertising = get_enum_value(
            client,
            "EuPoliticalAdvertisingStatusEnum",
            "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
        )
        if bidding == "MAXIMIZE_CLICKS":
            campaign.target_spend.target_spend_micros = 0
        else:
            campaign.maximize_conversions.target_cpa_micros = 0
        if start_date:
            campaign.start_date_time = f"{start_date} 00:00:00"
        if end_date:
            campaign.end_date_time = f"{end_date} 23:59:59"

        ad_group = new_op().ad_group_operation.create
        ad_group.resource_name = ad_group_rn
        ad_group.name = name
        ad_group.campaign = campaign_rn
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
        controls = ad_group.demand_gen_ad_group_settings.channel_controls
        if "all" in selected:
            controls.channel_strategy = client.enums.DemandGenChannelStrategyEnum.ALL_CHANNELS
        else:
            for channel in selected:
                setattr(controls.selected_channels, channel, True)

        for loc_id in locations:
            criterion = new_op().ad_group_criterion_operation.create
            criterion.ad_group = ad_group_rn
            criterion.location.geo_target_constant = f"geoTargetConstants/{loc_id}"
        for lang_id in languages:
            criterion = new_op().ad_group_criterion_operation.create
            criterion.ad_group = ad_group_rn
            criterion.language.language_constant = f"languageConstants/{lang_id}"

        video_rns = _video_asset_names(client, customer_id, video_ids, new_op, name)

        ad_group_ad = new_op().ad_group_ad_operation.create
        ad_group_ad.ad_group = ad_group_rn
        ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
        ad = ad_group_ad.ad
        ad.name = name
        ad.final_urls.append(final_url)
        info = ad.demand_gen_video_responsive_ad
        for field, values in texts.items():
            _set_texts(client, info, field, values)
        info.business_name.text = business_name
        logo = client.get_type("AdImageAsset")
        logo.asset = f"customers/{customer_id}/assets/{logo_asset_id}"
        info.logo_images.append(logo)
        _set_videos(client, info, video_rns)

        response = _run_mutate(client, customer_id, operations, validate_only)
        if validate_only:
            return {"status": "validated", "operations": len(operations)}

        result: dict[str, Any] = {"status": "created", "video_asset_ids": []}
        for op_response in response.mutate_operation_responses:
            kind = op_response.WhichOneof("response")
            resource_name = getattr(op_response, kind).resource_name
            if kind == "campaign_result":
                result["campaign_id"] = resource_name.split("/")[-1]
            elif kind == "ad_group_result":
                result["ad_group_id"] = resource_name.split("/")[-1]
            elif kind == "ad_group_ad_result":
                result["ad_id"] = resource_name.split("~")[-1]
            elif kind == "asset_result":
                result["video_asset_ids"].append(resource_name.split("/")[-1])
        return result

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_demand_gen_video_ad(
    ad_group_id: str,
    youtube_videos: Any,
    copy_from_ad_id: Optional[str] = None,
    headlines: Any = None,
    long_headlines: Any = None,
    descriptions: Any = None,
    business_name: Optional[str] = None,
    final_url: Optional[str] = None,
    logo_asset_id: Optional[str] = None,
    name: Optional[str] = None,
    status: str = "PAUSED",
    validate_only: bool = False,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Adds another YouTube video ad to an existing Demand Gen ad group.

    Use it when an ad already holds the maximum of 5 videos, or to test new
    videos next to the running ad. With copy_from_ad_id the new ad takes the
    texts, logo, business name, call to action and URL of that ad in the same
    ad group; any argument given here overrides the copied value.

    Run first with validate_only=True: Google checks the request, nothing is
    created.

    Args:
        ad_group_id: Existing Demand Gen ad group ID.
        youtube_videos: 1-5 YouTube URLs or video IDs (already on YouTube).
        copy_from_ad_id: Optional Demand Gen video ad in the same ad group to
            copy everything except the videos from.
        headlines: 1-5 headlines, max 40 characters (required without copy).
        long_headlines: 1-5 long headlines, max 90 characters (required without copy).
        descriptions: 1-5 descriptions, max 90 characters (required without copy).
        business_name: Max 25 characters (required without copy).
        final_url: Landing page URL (required without copy).
        logo_asset_id: Square IMAGE asset ID (required without copy).
        name: Optional ad name (default "Video ad <video IDs>").
        status: Ad status - PAUSED (default) or ENABLED.
        validate_only: True = Google validates the request, nothing is created.
        customer_id: Google Ads customer ID. Uses default from config if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: status ("validated" or "created"), ad_id, ad_group_id.

    Raises:
        ToolError: If input is invalid or the API rejects the request.
    """
    limits = _TEXT_LIMITS["demand_gen_video_responsive_ad"]
    video_ids = _youtube_ids(youtube_videos)
    given = {"headlines": headlines, "long_headlines": long_headlines, "descriptions": descriptions}
    texts = {f: _checked_texts(f, v, limits[f]) for f, v in given.items() if v is not None}
    if business_name is not None and not 1 <= len(business_name) <= 25:
        raise ToolError("business_name: 1-25 characters required")
    if not copy_from_ad_id:
        missing = [f for f in given if f not in texts]
        missing += [
            f for f, v in (("business_name", business_name), ("final_url", final_url),
                           ("logo_asset_id", logo_asset_id)) if not v
        ]
        if missing:
            raise ToolError(f"Without copy_from_ad_id these are required: {missing}")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        operations = []

        def new_op():
            op = client.get_type("MutateOperation")
            operations.append(op)
            return op

        group = _ad_id_int(ad_group_id, "ad_group_id")
        video_rns = _video_asset_names(
            client, customer_id, video_ids, new_op, name or f"Ad group {group}"
        )

        ad_group_ad = new_op().ad_group_ad_operation.create
        ad_group_ad.ad_group = f"customers/{customer_id}/adGroups/{group}"
        ad_group_ad.status = get_enum_value(client, "AdGroupAdStatusEnum", status)
        ad = ad_group_ad.ad
        info = ad.demand_gen_video_responsive_ad
        if copy_from_ad_id:
            source = _fetch_ad(client, customer_id, ad_group_id, copy_from_ad_id)
            source_type = get_enum_name(client, "AdTypeEnum", source.type_)
            if source_type != "DEMAND_GEN_VIDEO_RESPONSIVE_AD":
                raise ToolError(f"copy_from_ad_id {copy_from_ad_id} is {source_type}, not a Demand Gen video ad")
            info.CopyFrom(source.demand_gen_video_responsive_ad)
            ad.final_urls.extend(source.final_urls)
        ad.name = name or f"Video ad {' '.join(video_ids)}"
        for field, values in texts.items():
            _set_texts(client, info, field, values)
        if business_name:
            info.business_name.text = business_name
        if final_url:
            del ad.final_urls[:]
            ad.final_urls.append(final_url)
        if logo_asset_id:
            del info.logo_images[:]
            logo = client.get_type("AdImageAsset")
            logo.asset = f"customers/{customer_id}/assets/{_ad_id_int(logo_asset_id, 'logo_asset_id')}"
            info.logo_images.append(logo)
        _set_videos(client, info, video_rns)

        response = _run_mutate(client, customer_id, operations, validate_only)
        if validate_only:
            return {"status": "validated", "operations": len(operations)}
        for op_response in response.mutate_operation_responses:
            if op_response.WhichOneof("response") == "ad_group_ad_result":
                resource_name = op_response.ad_group_ad_result.resource_name
                return {
                    "status": "created",
                    "ad_group_id": str(group),
                    "ad_id": resource_name.split("~")[-1],
                    "ad_group_ad_resource_name": resource_name,
                }
        return {"status": "created", "ad_group_id": str(group)}

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
