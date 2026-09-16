"""Keyword management tools for Google Ads API.

This module provides MCP tools for managing Google Ads keywords including
listing, adding, updating, and removing keywords within ad groups.
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
    micros_to_currency,
    currency_to_micros,
)


@mcp.tool()
def google_list_keywords(
    customer_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    status: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists keywords for a Google Ads customer with performance metrics.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: Optional ad group ID to filter keywords.
        status: Optional filter by status - ENABLED, PAUSED, or REMOVED.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of keywords with:
            - id: Keyword criterion ID
            - ad_group_id: Parent ad group ID
            - ad_group_name: Parent ad group name
            - keyword_text: The keyword text
            - match_type: Match type (EXACT, PHRASE, BROAD)
            - status: Keyword status
            - cpc_bid: CPC bid in account currency
            - impressions: Total impressions
            - clicks: Total clicks
            - cost: Total cost in account currency
            - conversions: Total conversions
            - quality_score: Quality score (if available)

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
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group_criterion.cpc_bid_micros,
                ad_group_criterion.quality_info.quality_score,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions
            FROM keyword_view
        """

        conditions = []
        if ad_group_id:
            conditions.append(f"ad_group.id = {ad_group_id}")
        if status:
            conditions.append(f"ad_group_criterion.status = '{status.upper()}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY ad_group_criterion.criterion_id"

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        keywords = []
        for batch in response:
            for row in batch.results:
                keywords.append(
                    {
                        "id": str(row.ad_group_criterion.criterion_id),
                        "ad_group_id": str(row.ad_group.id),
                        "ad_group_name": row.ad_group.name,
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name,
                        "keyword_text": row.ad_group_criterion.keyword.text,
                        "match_type": get_enum_name(
                            client,
                            "KeywordMatchTypeEnum",
                            row.ad_group_criterion.keyword.match_type,
                        ),
                        "status": get_enum_name(
                            client,
                            "AdGroupCriterionStatusEnum",
                            row.ad_group_criterion.status,
                        ),
                        "cpc_bid": micros_to_currency(
                            row.ad_group_criterion.cpc_bid_micros
                        ),
                        "quality_score": row.ad_group_criterion.quality_info.quality_score
                        or None,
                        "impressions": row.metrics.impressions,
                        "clicks": row.metrics.clicks,
                        "cost": micros_to_currency(row.metrics.cost_micros),
                        "conversions": row.metrics.conversions,
                    }
                )

        return keywords

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_get_keyword(
    ad_group_id: str,
    keyword_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Gets detailed information about a specific keyword.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: The ad group ID containing the keyword.
        keyword_id: The keyword criterion ID to retrieve.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Keyword details including:
            - id: Keyword criterion ID
            - keyword_text: The keyword text
            - match_type: Match type
            - status: Keyword status
            - cpc_bid: CPC bid in account currency
            - quality_score: Quality score
            - creative_quality_score: Creative quality
            - post_click_quality_score: Post-click quality
            - search_predicted_ctr: Predicted CTR
            - All performance metrics

    Raises:
        ToolError: If the keyword is not found or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group_criterion.cpc_bid_micros,
                ad_group_criterion.final_urls,
                ad_group_criterion.quality_info.quality_score,
                ad_group_criterion.quality_info.creative_quality_score,
                ad_group_criterion.quality_info.post_click_quality_score,
                ad_group_criterion.quality_info.search_predicted_ctr,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.ctr,
                metrics.average_cpc,
                metrics.average_position
            FROM keyword_view
            WHERE ad_group.id = {ad_group_id}
                AND ad_group_criterion.criterion_id = {keyword_id}
        """

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        for batch in response:
            for row in batch.results:
                quality_info = row.ad_group_criterion.quality_info
                return {
                    "id": str(row.ad_group_criterion.criterion_id),
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "keyword_text": row.ad_group_criterion.keyword.text,
                    "match_type": get_enum_name(
                        client,
                        "KeywordMatchTypeEnum",
                        row.ad_group_criterion.keyword.match_type,
                    ),
                    "status": get_enum_name(
                        client,
                        "AdGroupCriterionStatusEnum",
                        row.ad_group_criterion.status,
                    ),
                    "cpc_bid": micros_to_currency(
                        row.ad_group_criterion.cpc_bid_micros
                    ),
                    "final_urls": list(row.ad_group_criterion.final_urls),
                    "quality_score": quality_info.quality_score or None,
                    "creative_quality_score": get_enum_name(
                        client,
                        "QualityScoreBucketEnum",
                        quality_info.creative_quality_score,
                    )
                    if quality_info.creative_quality_score
                    else None,
                    "post_click_quality_score": get_enum_name(
                        client,
                        "QualityScoreBucketEnum",
                        quality_info.post_click_quality_score,
                    )
                    if quality_info.post_click_quality_score
                    else None,
                    "search_predicted_ctr": get_enum_name(
                        client,
                        "QualityScoreBucketEnum",
                        quality_info.search_predicted_ctr,
                    )
                    if quality_info.search_predicted_ctr
                    else None,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": micros_to_currency(row.metrics.cost_micros),
                    "conversions": row.metrics.conversions,
                    "ctr": row.metrics.ctr,
                    "average_cpc": micros_to_currency(row.metrics.average_cpc),
                }

        raise ToolError(f"Keyword {keyword_id} not found in ad group {ad_group_id}")

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_add_keywords(
    ad_group_id: str,
    keywords: Any,
    customer_id: Optional[str] = None,
    match_type: str = "BROAD",
    cpc_bid: Optional[float] = None,
    status: str = "ENABLED",
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Adds keywords to an ad group.

    Args:
        ad_group_id: The ad group ID to add keywords to.
        keywords: List of keyword texts to add.
        customer_id: The Google Ads customer ID. Uses default from config if not provided.
        match_type: Match type for all keywords. Options:
            - BROAD: Broad match (default)
            - PHRASE: Phrase match
            - EXACT: Exact match
        cpc_bid: Optional CPC bid in account currency (uses ad group default if not set).
        status: Initial status - ENABLED (default) or PAUSED.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created keywords details:
            - keywords_added: Number of keywords added
            - keyword_ids: List of new keyword criterion IDs
            - status: Creation status

    Raises:
        ToolError: If the API request fails.
    """
    keywords = _coerce_list(keywords)
    if not keywords:
        raise ToolError("At least one keyword is required")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operations = []

        for keyword_text in keywords:
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create

            criterion.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
            criterion.status = get_enum_value(
                client, "AdGroupCriterionStatusEnum", status
            )

            criterion.keyword.text = keyword_text
            criterion.keyword.match_type = get_enum_value(
                client, "KeywordMatchTypeEnum", match_type
            )

            if cpc_bid is not None:
                criterion.cpc_bid_micros = currency_to_micros(cpc_bid)

            operations.append(operation)

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=operations,
        )

        keyword_ids = [
            result.resource_name.split("~")[-1] for result in response.results
        ]

        return {
            "keywords_added": len(keyword_ids),
            "keyword_ids": keyword_ids,
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_update_keyword(
    ad_group_id: str,
    keyword_id: str,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    cpc_bid: Optional[float] = None,
    final_urls: Optional[list[str]] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Updates a keyword's settings.

    Note: The keyword text and match type cannot be changed.
    To change these, remove the keyword and create a new one.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: The ad group ID containing the keyword.
        keyword_id: The keyword criterion ID to update.
        status: Optional new status - ENABLED, PAUSED, or REMOVED.
        cpc_bid: Optional new CPC bid in account currency (e.g., 1.50 for $1.50).
        final_urls: Optional list of final URLs for the keyword.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Updated keyword details:
            - keyword_resource_name: Full resource name
            - updated_fields: List of fields that were updated
            - status: "updated"

    Raises:
        ToolError: If no fields to update or API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")
        criterion = operation.update

        criterion.resource_name = (
            f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{keyword_id}"
        )

        field_mask = []

        if status is not None:
            criterion.status = get_enum_value(
                client, "AdGroupCriterionStatusEnum", status
            )
            field_mask.append("status")

        if cpc_bid is not None:
            criterion.cpc_bid_micros = currency_to_micros(cpc_bid)
            field_mask.append("cpc_bid_micros")

        if final_urls is not None:
            criterion.final_urls.extend(final_urls)
            field_mask.append("final_urls")

        if not field_mask:
            raise ToolError("No fields to update. Provide at least one field.")

        operation.update_mask.paths.extend(field_mask)

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "keyword_resource_name": response.results[0].resource_name,
            "updated_fields": field_mask,
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_remove_keyword(
    ad_group_id: str,
    keyword_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes a keyword from an ad group.

    Note: This sets the keyword status to REMOVED. The keyword data
    is retained and can still be queried but cannot be reactivated.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: The ad group ID containing the keyword.
        keyword_id: The keyword criterion ID to remove.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal status:
            - keyword_resource_name: Full resource name
            - status: "removed"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")
        operation.remove = (
            f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{keyword_id}"
        )

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "keyword_resource_name": response.results[0].resource_name,
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_add_negative_keywords(
    ad_group_id: str,
    keywords: Any,
    customer_id: Optional[str] = None,
    match_type: str = "BROAD",
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Adds negative keywords to an ad group.

    Negative keywords prevent ads from showing for specific search terms.

    Args:
        ad_group_id: The ad group ID to add negative keywords to.
        keywords: List of negative keyword texts to add.
        customer_id: The Google Ads customer ID. Uses default from config if not provided.
        match_type: Match type for all keywords. Options:
            - BROAD: Broad match negative (default)
            - PHRASE: Phrase match negative
            - EXACT: Exact match negative
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created negative keywords details:
            - keywords_added: Number of keywords added
            - keyword_ids: List of new keyword criterion IDs
            - status: Creation status

    Raises:
        ToolError: If the API request fails.
    """
    keywords = _coerce_list(keywords)
    if not keywords:
        raise ToolError("At least one negative keyword is required")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operations = []

        for keyword_text in keywords:
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create

            criterion.ad_group = f"customers/{customer_id}/adGroups/{ad_group_id}"
            criterion.negative = True

            criterion.keyword.text = keyword_text
            criterion.keyword.match_type = get_enum_value(
                client, "KeywordMatchTypeEnum", match_type
            )

            operations.append(operation)

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=operations,
        )

        keyword_ids = [
            result.resource_name.split("~")[-1] for result in response.results
        ]

        return {
            "keywords_added": len(keyword_ids),
            "keyword_ids": keyword_ids,
            "type": "negative",
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_list_negative_keywords(
    customer_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists negative keywords for a Google Ads customer.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        ad_group_id: Optional ad group ID to filter negative keywords.
        campaign_id: Optional campaign ID to filter negative keywords.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of negative keywords with:
            - id: Keyword criterion ID
            - ad_group_id: Parent ad group ID
            - ad_group_name: Parent ad group name
            - campaign_id: Parent campaign ID
            - campaign_name: Parent campaign name
            - keyword_text: The keyword text
            - match_type: Match type (EXACT, PHRASE, BROAD)
            - status: Keyword status

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
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group_criterion.negative,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name
            FROM ad_group_criterion
            WHERE ad_group_criterion.negative = TRUE
                AND ad_group_criterion.type = 'KEYWORD'
        """

        conditions = []
        if ad_group_id:
            conditions.append(f"ad_group.id = {ad_group_id}")
        if campaign_id:
            conditions.append(f"campaign.id = {campaign_id}")

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += " ORDER BY ad_group_criterion.keyword.text"

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        keywords = []
        for batch in response:
            for row in batch.results:
                keywords.append(
                    {
                        "id": str(row.ad_group_criterion.criterion_id),
                        "ad_group_id": str(row.ad_group.id),
                        "ad_group_name": row.ad_group.name,
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name,
                        "keyword_text": row.ad_group_criterion.keyword.text,
                        "match_type": get_enum_name(
                            client,
                            "KeywordMatchTypeEnum",
                            row.ad_group_criterion.keyword.match_type,
                        ),
                        "status": get_enum_name(
                            client,
                            "AdGroupCriterionStatusEnum",
                            row.ad_group_criterion.status,
                        ),
                        "level": "ad_group",
                    }
                )

        return keywords

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_remove_negative_keyword(
    ad_group_id: str,
    keyword_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes a negative keyword from an ad group.

    Args:
        ad_group_id: The ad group ID containing the negative keyword.
        keyword_id: The negative keyword criterion ID to remove.
        customer_id: The Google Ads customer ID (digits only, no dashes).
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal status:
            - keyword_resource_name: Full resource name
            - status: "removed"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")
        operation.remove = (
            f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{keyword_id}"
        )

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "keyword_resource_name": response.results[0].resource_name,
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_add_campaign_negative_keywords(
    campaign_id: str,
    keywords: Any,
    customer_id: Optional[str] = None,
    match_type: str = "BROAD",
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Adds negative keywords at the campaign level.

    Campaign-level negative keywords apply to all ad groups within the campaign.
    This is more efficient than adding the same negative to each ad group.

    Args:
        campaign_id: The campaign ID to add negative keywords to.
        keywords: List of negative keyword texts to add.
        customer_id: The Google Ads customer ID. Uses default from config if not provided.
        match_type: Match type for all keywords. Options:
            - BROAD: Broad match negative (default)
            - PHRASE: Phrase match negative
            - EXACT: Exact match negative
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created negative keywords details:
            - keywords_added: Number of keywords added
            - keyword_ids: List of new keyword criterion IDs
            - level: "campaign"
            - status: Creation status

    Raises:
        ToolError: If the API request fails.
    """
    keywords = _coerce_list(keywords)
    if not keywords:
        raise ToolError("At least one negative keyword is required")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_criterion_service = client.get_service("CampaignCriterionService")
        operations = []

        for keyword_text in keywords:
            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create

            criterion.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
            criterion.negative = True

            criterion.keyword.text = keyword_text
            criterion.keyword.match_type = get_enum_value(
                client, "KeywordMatchTypeEnum", match_type
            )

            operations.append(operation)

        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=operations,
        )

        keyword_ids = [
            result.resource_name.split("~")[-1] for result in response.results
        ]

        return {
            "keywords_added": len(keyword_ids),
            "keyword_ids": keyword_ids,
            "level": "campaign",
            "type": "negative",
            "status": "created",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_list_campaign_negative_keywords(
    customer_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists campaign-level negative keywords.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        campaign_id: Optional campaign ID to filter negative keywords.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of campaign negative keywords with:
            - id: Keyword criterion ID
            - campaign_id: Parent campaign ID
            - campaign_name: Parent campaign name
            - keyword_text: The keyword text
            - match_type: Match type (EXACT, PHRASE, BROAD)

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
                campaign_criterion.criterion_id,
                campaign_criterion.keyword.text,
                campaign_criterion.keyword.match_type,
                campaign_criterion.negative,
                campaign.id,
                campaign.name
            FROM campaign_criterion
            WHERE campaign_criterion.negative = TRUE
                AND campaign_criterion.type = 'KEYWORD'
        """

        if campaign_id:
            query += f" AND campaign.id = {campaign_id}"

        query += " ORDER BY campaign_criterion.keyword.text"

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        keywords = []
        for batch in response:
            for row in batch.results:
                keywords.append(
                    {
                        "id": str(row.campaign_criterion.criterion_id),
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name,
                        "keyword_text": row.campaign_criterion.keyword.text,
                        "match_type": get_enum_name(
                            client,
                            "KeywordMatchTypeEnum",
                            row.campaign_criterion.keyword.match_type,
                        ),
                        "level": "campaign",
                    }
                )

        return keywords

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_remove_campaign_negative_keyword(
    campaign_id: str,
    keyword_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes a negative keyword from a campaign.

    Args:
        campaign_id: The campaign ID containing the negative keyword.
        keyword_id: The negative keyword criterion ID to remove.
        customer_id: The Google Ads customer ID (digits only, no dashes).
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Removal status:
            - keyword_resource_name: Full resource name
            - status: "removed"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_criterion_service = client.get_service("CampaignCriterionService")
        operation = client.get_type("CampaignCriterionOperation")
        operation.remove = (
            f"customers/{customer_id}/campaignCriteria/{campaign_id}~{keyword_id}"
        )

        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "keyword_resource_name": response.results[0].resource_name,
            "status": "removed",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_bulk_update_keywords(
    updates: list[dict[str, Any]],
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Bulk update keywords in a single API call (up to 5000 operations).

    This is much more efficient than calling google_update_keyword repeatedly.
    Uses partial failure mode: valid updates succeed even if some fail
    (e.g. keywords in removed ad groups are skipped and reported separately).

    Args:
        updates: List of update dicts. Each dict must contain:
            - ad_group_id (str): The ad group ID containing the keyword.
            - keyword_id (str): The keyword criterion ID to update.
            And at least one of:
            - status (str): New status - ENABLED, PAUSED, or REMOVED.
            - cpc_bid (float): New CPC bid in account currency (e.g., 1.50).
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Bulk update results:
            - keywords_updated: Number of keywords successfully updated
            - resource_names: List of updated keyword resource names
            - status: "updated" or "failed" if none succeeded
            - errors (if any): List of failed updates with index, original
              update dict, and error message
            - keywords_failed (if any): Number of keywords that failed

    Raises:
        ToolError: If updates list is empty, missing required fields,
            or the API request fails entirely.
    """
    if not updates:
        raise ToolError("At least one update is required")
    if len(updates) > 5000:
        raise ToolError("Maximum 5000 updates per call")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        operations = []

        for i, update in enumerate(updates):
            ad_group_id = update.get("ad_group_id")
            keyword_id = update.get("keyword_id")
            if not ad_group_id or not keyword_id:
                raise ToolError(
                    f"Update at index {i} missing required 'ad_group_id' "
                    f"or 'keyword_id'"
                )

            new_status = update.get("status")
            new_cpc_bid = update.get("cpc_bid")

            if new_status is None and new_cpc_bid is None:
                raise ToolError(
                    f"Update at index {i} must include at least one of "
                    f"'status' or 'cpc_bid'"
                )

            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.update
            criterion.resource_name = (
                f"customers/{customer_id}/adGroupCriteria/"
                f"{ad_group_id}~{keyword_id}"
            )

            field_mask: list[str] = []

            if new_status is not None:
                criterion.status = get_enum_value(
                    client, "AdGroupCriterionStatusEnum", new_status
                )
                field_mask.append("status")

            if new_cpc_bid is not None:
                criterion.cpc_bid_micros = currency_to_micros(new_cpc_bid)
                field_mask.append("cpc_bid_micros")

            operation.update_mask.paths.extend(field_mask)
            operations.append(operation)

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=operations,
            partial_failure=True,
        )

        resource_names = [result.resource_name for result in response.results]

        errors = []
        if response.partial_failure_error:
            from google.protobuf import json_format

            err_dict = json_format.MessageToDict(response.partial_failure_error)
            for detail in err_dict.get("details", []):
                for err in detail.get("errors", []):
                    idx = None
                    for loc in (
                        err.get("location", {}).get("fieldPathElements", [])
                    ):
                        if loc.get("fieldName") == "operations":
                            idx = loc.get("index")
                            break
                    errors.append(
                        {
                            "index": idx,
                            "update": updates[idx] if idx is not None else None,
                            "error": err.get("message", str(err)),
                        }
                    )

        result: dict[str, Any] = {
            "keywords_updated": len(resource_names),
            "resource_names": resource_names,
            "status": "updated" if resource_names else "failed",
        }
        if errors:
            result["errors"] = errors
            result["keywords_failed"] = len(errors)

        return result

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
