"""Audience management tools for Google Ads API.

This module provides MCP tools for managing Google Ads audiences (UserLists)
including listing, creating, updating, and deleting remarketing audiences,
as well as Customer Match user uploads.
"""

import hashlib
from typing import Any, Optional

from google.ads.googleads.errors import GoogleAdsException
from google.api_core import protobuf_helpers
from mcp.server.fastmcp.exceptions import ToolError

from ..server import mcp
from .client import (
    get_google_ads_client,
    format_error,
    resolve_customer_id,
    get_enum_name,
    micros_to_currency,
)


@mcp.tool()
def google_list_audiences(
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists all remarketing audiences (UserLists) for a Google Ads customer.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of audiences with:
            - id: UserList ID
            - resource_name: Full resource name
            - name: Audience name
            - type: UserList type (REMARKETING, LOGICAL, BASIC, CRM_BASED, etc.)
            - status: Membership status (OPEN, CLOSED)
            - size_for_search: Estimated audience size for Search
            - size_for_display: Estimated audience size for Display
            - membership_life_span: Days users stay in the list
            - description: Audience description

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
                user_list.id,
                user_list.resource_name,
                user_list.name,
                user_list.type,
                user_list.membership_status,
                user_list.size_for_search,
                user_list.size_for_display,
                user_list.membership_life_span,
                user_list.description,
                user_list.size_range_for_search,
                user_list.size_range_for_display,
                user_list.eligible_for_search,
                user_list.eligible_for_display
            FROM user_list
            ORDER BY user_list.name
        """

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        audiences = []
        for batch in response:
            for row in batch.results:
                ul = row.user_list
                audiences.append({
                    "id": str(ul.id),
                    "resource_name": ul.resource_name,
                    "name": ul.name,
                    "type": get_enum_name(client, "UserListTypeEnum", ul.type_),
                    "status": get_enum_name(
                        client, "UserListMembershipStatusEnum", ul.membership_status
                    ),
                    "size_for_search": ul.size_for_search,
                    "size_for_display": ul.size_for_display,
                    "membership_life_span": ul.membership_life_span,
                    "description": ul.description or None,
                    "size_range_for_search": get_enum_name(
                        client, "UserListSizeRangeEnum", ul.size_range_for_search
                    ),
                    "size_range_for_display": get_enum_name(
                        client, "UserListSizeRangeEnum", ul.size_range_for_display
                    ),
                    "eligible_for_search": ul.eligible_for_search,
                    "eligible_for_display": ul.eligible_for_display,
                })

        return audiences

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_create_audience(
    name: str,
    customer_id: Optional[str] = None,
    description: Optional[str] = None,
    membership_life_span: int = 30,
    rule_type: str = "URL_CONTAINS",
    rule_value: Optional[str] = None,
    rules: Optional[list[dict[str, str]]] = None,
    combine_rules: str = "OR",
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Creates a rule-based remarketing audience (UserList) in Google Ads.

    Supports creating website visitor audiences based on URL rules.
    For simple audiences, use rule_type + rule_value. For complex
    audiences with multiple conditions, use the rules parameter.

    Args:
        name: Name for the audience (e.g., "Pricing Page Visitors").
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        description: Optional description for the audience.
        membership_life_span: Days users stay in the list (default: 30).
            Common values: 7, 14, 30, 60, 90, 180, 365, 540.
        rule_type: Type of URL rule for simple audiences. Options:
            - URL_CONTAINS: URL contains the value (e.g., "/cenik")
            - URL_EQUALS: URL exactly matches the value
            - URL_PREFIX: URL starts with the value
            - ALL_VISITORS: All website visitors (ignores rule_value)
        rule_value: The URL pattern to match (e.g., "/cenik", "/kontakt").
            Not needed for ALL_VISITORS.
        rules: List of rule dicts for complex audiences. Each dict has:
            - type: URL_CONTAINS, URL_EQUALS, or URL_PREFIX
            - value: The URL pattern to match
            Example: [{"type": "URL_CONTAINS", "value": "/cenik"},
                      {"type": "URL_CONTAINS", "value": "/kontakt"}]
        combine_rules: How to combine multiple rules - "OR" (any match)
            or "AND" (all must match). Default: "OR".
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Created audience details:
            - audience_id: The new UserList ID
            - resource_name: Full resource name
            - name: Audience name
            - membership_life_span: Configured membership duration

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        user_list_service = client.get_service("UserListService")
        operation = client.get_type("UserListOperation")
        user_list = operation.create

        user_list.name = name
        user_list.membership_life_span = membership_life_span
        user_list.membership_status = client.enums.UserListMembershipStatusEnum.OPEN

        if description:
            user_list.description = description

        # Build the rule-based user list
        if rule_type == "ALL_VISITORS":
            # All visitors: use a URL contains rule with empty string
            rule_item = client.get_type("UserListRuleItemInfo")
            rule_item.name = "url__"
            string_rule = rule_item.string_rule_item
            string_rule.operator = (
                client.enums.UserListStringRuleItemOperatorEnum.CONTAINS
            )
            string_rule.value = ""

            rule_item_group = client.get_type("UserListRuleItemGroupInfo")
            rule_item_group.rule_items.append(rule_item)

            rule_info = user_list.rule_based_user_list.flexible_rule_user_list
            rule_info.inclusive_rule_operator = (
                client.enums.UserListFlexibleRuleOperatorEnum.AND
            )
            inclusive_operand = client.get_type(
                "FlexibleRuleOperandInfo"
            )
            inclusive_operand.rule.rule_item_groups.append(rule_item_group)
            inclusive_operand.lookback_window_days = membership_life_span
            rule_info.inclusive_operands.append(inclusive_operand)

        elif rules:
            # Complex rules with multiple conditions
            if combine_rules.upper() == "AND":
                # AND: each rule in its own group
                for rule_dict in rules:
                    rule_item = _build_url_rule_item(client, rule_dict)
                    rule_item_group = client.get_type("UserListRuleItemGroupInfo")
                    rule_item_group.rule_items.append(rule_item)

                    rule_info = user_list.rule_based_user_list.flexible_rule_user_list
                    rule_info.inclusive_rule_operator = (
                        client.enums.UserListFlexibleRuleOperatorEnum.AND
                    )
                    inclusive_operand = client.get_type(
                        "FlexibleRuleOperandInfo"
                    )
                    inclusive_operand.rule.rule_item_groups.append(rule_item_group)
                    inclusive_operand.lookback_window_days = membership_life_span
                    rule_info.inclusive_operands.append(inclusive_operand)
            else:
                # OR: all rules in one group
                rule_item_group = client.get_type("UserListRuleItemGroupInfo")
                for rule_dict in rules:
                    rule_item = _build_url_rule_item(client, rule_dict)
                    rule_item_group.rule_items.append(rule_item)

                rule_info = user_list.rule_based_user_list.flexible_rule_user_list
                rule_info.inclusive_rule_operator = (
                    client.enums.UserListFlexibleRuleOperatorEnum.AND
                )
                inclusive_operand = client.get_type(
                    "FlexibleRuleOperandInfo"
                )
                inclusive_operand.rule.rule_item_groups.append(rule_item_group)
                inclusive_operand.lookback_window_days = membership_life_span
                rule_info.inclusive_operands.append(inclusive_operand)

        else:
            # Simple single-rule audience
            if not rule_value:
                raise ToolError(
                    "rule_value is required for URL-based audiences "
                    "(use rule_type='ALL_VISITORS' for all visitors)"
                )

            rule_item = _build_url_rule_item(
                client, {"type": rule_type, "value": rule_value}
            )
            rule_item_group = client.get_type("UserListRuleItemGroupInfo")
            rule_item_group.rule_items.append(rule_item)

            rule_info = user_list.rule_based_user_list.flexible_rule_user_list
            rule_info.inclusive_rule_operator = (
                client.enums.UserListFlexibleRuleOperatorEnum.AND
            )
            inclusive_operand = client.get_type(
                "FlexibleRuleOperandInfo"
            )
            inclusive_operand.rule.rule_item_groups.append(rule_item_group)
            inclusive_operand.lookback_window_days = membership_life_span
            rule_info.inclusive_operands.append(inclusive_operand)

        response = user_list_service.mutate_user_lists(
            customer_id=customer_id,
            operations=[operation],
        )

        result = response.results[0]
        return {
            "audience_id": result.resource_name.split("/")[-1],
            "resource_name": result.resource_name,
            "name": name,
            "membership_life_span": membership_life_span,
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


def _build_url_rule_item(client, rule_dict: dict[str, str]):
    """Build a UserListRuleItemInfo for a URL-based rule."""
    rule_type = rule_dict.get("type", "URL_CONTAINS").upper()
    value = rule_dict.get("value", "")

    rule_item = client.get_type("UserListRuleItemInfo")
    rule_item.name = "url__"
    string_rule = rule_item.string_rule_item

    operator_map = {
        "URL_CONTAINS": client.enums.UserListStringRuleItemOperatorEnum.CONTAINS,
        "URL_EQUALS": client.enums.UserListStringRuleItemOperatorEnum.EQUALS,
        "URL_PREFIX": client.enums.UserListStringRuleItemOperatorEnum.STARTS_WITH,
    }

    if rule_type not in operator_map:
        raise ToolError(
            f"Invalid rule_type '{rule_type}'. "
            f"Options: {', '.join(operator_map.keys())}"
        )

    string_rule.operator = operator_map[rule_type]
    string_rule.value = value
    return rule_item


@mcp.tool()
def google_update_audience(
    audience_id: str,
    customer_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    membership_life_span: Optional[int] = None,
    status: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Updates an existing remarketing audience (UserList) in Google Ads.

    Args:
        audience_id: The UserList ID to update.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        name: New name for the audience.
        description: New description for the audience.
        membership_life_span: New membership duration in days.
        status: New membership status - "OPEN" or "CLOSED".
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Updated audience details:
            - resource_name: Full resource name
            - updated_fields: List of fields that were updated

    Raises:
        ToolError: If the API request fails or no fields to update.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        user_list_service = client.get_service("UserListService")
        operation = client.get_type("UserListOperation")
        user_list = operation.update

        resource_name = user_list_service.user_list_path(customer_id, audience_id)
        user_list.resource_name = resource_name

        updated_fields = []

        if name is not None:
            user_list.name = name
            updated_fields.append("name")

        if description is not None:
            user_list.description = description
            updated_fields.append("description")

        if membership_life_span is not None:
            user_list.membership_life_span = membership_life_span
            updated_fields.append("membership_life_span")

        if status is not None:
            status_upper = status.upper()
            if status_upper == "OPEN":
                user_list.membership_status = (
                    client.enums.UserListMembershipStatusEnum.OPEN
                )
            elif status_upper == "CLOSED":
                user_list.membership_status = (
                    client.enums.UserListMembershipStatusEnum.CLOSED
                )
            else:
                raise ToolError(f"Invalid status '{status}'. Options: OPEN, CLOSED")
            updated_fields.append("membership_status")

        if not updated_fields:
            raise ToolError("No fields to update. Provide at least one field.")

        field_mask = protobuf_helpers.field_mask(None, user_list._pb)
        operation.update_mask.CopyFrom(field_mask)

        response = user_list_service.mutate_user_lists(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "resource_name": response.results[0].resource_name,
            "updated_fields": updated_fields,
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_delete_audience(
    audience_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Closes/removes a remarketing audience (UserList) in Google Ads.

    Note: UserLists cannot be truly deleted via the API. This tool closes
    the audience by setting its membership_status to CLOSED, which stops
    new users from being added.

    Args:
        audience_id: The UserList ID to close.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Result with:
            - resource_name: Full resource name
            - status: "CLOSED"

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        user_list_service = client.get_service("UserListService")
        operation = client.get_type("UserListOperation")
        user_list = operation.update

        resource_name = user_list_service.user_list_path(customer_id, audience_id)
        user_list.resource_name = resource_name
        user_list.membership_status = (
            client.enums.UserListMembershipStatusEnum.CLOSED
        )

        field_mask = protobuf_helpers.field_mask(None, user_list._pb)
        operation.update_mask.CopyFrom(field_mask)

        response = user_list_service.mutate_user_lists(
            customer_id=customer_id,
            operations=[operation],
        )

        return {
            "resource_name": response.results[0].resource_name,
            "status": "CLOSED",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_add_customer_match_users(
    audience_id: str,
    emails: Optional[list[str]] = None,
    phones: Optional[list[str]] = None,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Uploads hashed user data to a Customer Match audience via OfflineUserDataJobService.

    Email and phone values are automatically normalized and SHA-256 hashed
    before upload, as required by the Google Ads API.

    Args:
        audience_id: The UserList ID to upload users to. Must be a
            CRM_BASED (Customer Match) user list.
        emails: List of email addresses to upload. Will be lowercased,
            trimmed, and SHA-256 hashed automatically.
        phones: List of phone numbers to upload. Should be in E.164
            format (e.g., "+420123456789"). Will be SHA-256 hashed.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Upload result with:
            - job_resource_name: The offline user data job resource name
            - status: Job status
            - uploaded_count: Number of user identifiers uploaded

    Raises:
        ToolError: If the API request fails or no user data provided.
    """
    if not emails and not phones:
        raise ToolError("Provide at least one of: emails, phones")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        offline_user_data_job_service = client.get_service(
            "OfflineUserDataJobService"
        )
        user_list_service = client.get_service("UserListService")

        # Create the offline user data job
        job = client.get_type("OfflineUserDataJob")
        job.type_ = client.enums.OfflineUserDataJobTypeEnum.CUSTOMER_MATCH_USER_LIST
        job.customer_match_user_list_metadata.user_list = (
            user_list_service.user_list_path(customer_id, audience_id)
        )

        create_response = offline_user_data_job_service.create_offline_user_data_job(
            customer_id=customer_id,
            job=job,
        )
        job_resource_name = create_response.resource_name

        # Build user data operations
        operations = []
        uploaded_count = 0

        if emails:
            for email in emails:
                op = client.get_type("OfflineUserDataJobOperation")
                user_identifier = client.get_type("UserIdentifier")
                normalized = email.strip().lower()
                user_identifier.hashed_email = hashlib.sha256(
                    normalized.encode("utf-8")
                ).hexdigest()
                op.create.user_identifiers.append(user_identifier)
                operations.append(op)
                uploaded_count += 1

        if phones:
            for phone in phones:
                op = client.get_type("OfflineUserDataJobOperation")
                user_identifier = client.get_type("UserIdentifier")
                normalized = phone.strip().replace(" ", "").replace("-", "")
                user_identifier.hashed_phone_number = hashlib.sha256(
                    normalized.encode("utf-8")
                ).hexdigest()
                op.create.user_identifiers.append(user_identifier)
                operations.append(op)
                uploaded_count += 1

        # Add operations to the job
        request = client.get_type("AddOfflineUserDataJobOperationsRequest")
        request.resource_name = job_resource_name
        request.operations = operations
        request.enable_partial_failure = True

        offline_user_data_job_service.add_offline_user_data_job_operations(
            request=request,
        )

        # Run the job
        offline_user_data_job_service.run_offline_user_data_job(
            resource_name=job_resource_name,
        )

        return {
            "job_resource_name": job_resource_name,
            "status": "RUNNING",
            "uploaded_count": uploaded_count,
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_list_audience_segments(
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists audience segments available for targeting in Google Ads.

    This includes GA4-linked audience segments, Google-curated segments
    (in-market, affinity), and custom segments.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of audience segments with:
            - id: Audience segment ID
            - resource_name: Full resource name
            - name: Segment name
            - type: Segment type (CUSTOM, IN_MARKET, AFFINITY, etc.)
            - description: Segment description

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
                audience.id,
                audience.resource_name,
                audience.name,
                audience.description,
                audience.status,
                audience.scope
            FROM audience
            WHERE audience.status = 'ENABLED'
            ORDER BY audience.name
        """

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        segments = []
        for batch in response:
            for row in batch.results:
                aud = row.audience
                segments.append({
                    "id": str(aud.id),
                    "resource_name": aud.resource_name,
                    "name": aud.name,
                    "description": aud.description or None,
                    "status": get_enum_name(
                        client, "AudienceStatusEnum", aud.status
                    ),
                    "scope": get_enum_name(
                        client, "AudienceScopeEnum", aud.scope
                    ),
                })

        return segments

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


# ---------------------------------------------------------------------------
# Campaign-level audience targeting (CampaignCriterionService)
# ---------------------------------------------------------------------------


@mcp.tool()
def google_add_audience_to_campaign(
    campaign_id: str,
    audience_id: str,
    customer_id: Optional[str] = None,
    bid_modifier: Optional[float] = None,
    mode: str = "OBSERVATION",
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Attaches an audience (UserList) to a campaign for targeting or observation.

    In OBSERVATION mode (default), ads show to everyone but you can see
    performance breakdowns and set bid adjustments for the audience.
    In TARGETING mode, ads ONLY show to users in the audience.

    Args:
        campaign_id: The campaign ID to add the audience to.
        audience_id: The UserList ID to attach (from google_list_audiences).
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        bid_modifier: Optional bid adjustment multiplier.
            1.0 = no change, 1.3 = +30% bid, 1.5 = +50% bid, 0.7 = -30%.
            Only applies in OBSERVATION mode.
        mode: Targeting mode. Options:
            - OBSERVATION: Ads show to everyone; audience used for reporting
              and optional bid adjustments (default, recommended).
            - TARGETING: Ads ONLY show to users in this audience.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Result with:
            - campaign_id: Campaign ID
            - audience_id: UserList ID attached
            - mode: Targeting mode used
            - bid_modifier: Bid modifier if set
            - resource_name: Created criterion resource name

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_resource = f"customers/{customer_id}/campaigns/{campaign_id}"
        user_list_resource = f"customers/{customer_id}/userLists/{audience_id}"

        criterion_service = client.get_service("CampaignCriterionService")
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_resource
        criterion.user_list.user_list = user_list_resource

        if bid_modifier is not None:
            criterion.bid_modifier = bid_modifier

        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[op],
        )

        result_resource = response.results[0].resource_name

        # Set targeting setting on campaign if TARGETING mode
        if mode.upper() == "TARGETING":
            campaign_service = client.get_service("CampaignService")
            campaign_op = client.get_type("CampaignOperation")
            campaign = campaign_op.update
            campaign.resource_name = campaign_resource

            target_restriction = client.get_type("TargetRestriction")
            target_restriction.targeting_dimension = (
                client.enums.TargetingDimensionEnum.AUDIENCE
            )
            target_restriction.bid_only = False
            campaign.targeting_setting.target_restrictions.append(target_restriction)

            campaign_op.update_mask.paths.append("targeting_setting")
            campaign_service.mutate_campaigns(
                customer_id=customer_id,
                operations=[campaign_op],
            )

        return {
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "mode": mode.upper(),
            "bid_modifier": bid_modifier,
            "resource_name": result_resource,
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_remove_audience_from_campaign(
    campaign_id: str,
    audience_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Removes an audience criterion from a campaign.

    Args:
        campaign_id: The campaign ID.
        audience_id: The UserList ID to remove from the campaign.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Result with:
            - campaign_id: Campaign ID
            - audience_id: Removed audience ID
            - removed_count: Number of criteria removed

    Raises:
        ToolError: If the API request fails or audience not found on campaign.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        # Find the criterion resource name
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT campaign_criterion.resource_name,
                   campaign_criterion.user_list.user_list
            FROM campaign_criterion
            WHERE campaign.id = {campaign_id}
              AND campaign_criterion.type = 'USER_LIST'
              AND campaign_criterion.negative = FALSE
        """

        response = ga_service.search_stream(
            customer_id=customer_id, query=query
        )

        user_list_resource = f"customers/{customer_id}/userLists/{audience_id}"
        remove_ops = []
        criterion_service = client.get_service("CampaignCriterionService")

        for batch in response:
            for row in batch.results:
                if row.campaign_criterion.user_list.user_list == user_list_resource:
                    op = client.get_type("CampaignCriterionOperation")
                    op.remove = row.campaign_criterion.resource_name
                    remove_ops.append(op)

        if not remove_ops:
            raise ToolError(
                f"Audience {audience_id} not found on campaign {campaign_id}"
            )

        criterion_service.mutate_campaign_criteria(
            customer_id=customer_id, operations=remove_ops
        )

        return {
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "removed_count": len(remove_ops),
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_list_campaign_audiences(
    campaign_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists all audience criteria on a campaign with their bid modifiers.

    Shows both positive (targeting/observation) and negative (exclusion)
    audience criteria attached to a campaign.

    Args:
        campaign_id: The campaign ID to query.
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        list[dict]: List of audience criteria with:
            - criterion_id: Criterion ID
            - resource_name: Full resource name
            - user_list_id: UserList ID
            - user_list_name: UserList name (if available)
            - bid_modifier: Bid modifier (1.0 = no change)
            - negative: True if this is an exclusion
            - status: Criterion status

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        query = f"""
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.resource_name,
                campaign_criterion.user_list.user_list,
                campaign_criterion.bid_modifier,
                campaign_criterion.negative,
                campaign_criterion.status,
                user_list.name,
                user_list.size_for_search,
                user_list.size_for_display
            FROM campaign_criterion
            WHERE campaign.id = {campaign_id}
              AND campaign_criterion.type = 'USER_LIST'
        """

        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.search_stream(
            customer_id=customer_id, query=query
        )

        results = []
        for batch in response:
            for row in batch.results:
                cc = row.campaign_criterion
                ul = row.user_list
                user_list_rn = cc.user_list.user_list
                user_list_id = user_list_rn.split("/")[-1] if user_list_rn else None

                results.append({
                    "criterion_id": str(cc.criterion_id),
                    "resource_name": cc.resource_name,
                    "user_list_id": user_list_id,
                    "user_list_name": ul.name or None,
                    "size_for_search": ul.size_for_search,
                    "size_for_display": ul.size_for_display,
                    "bid_modifier": cc.bid_modifier if cc.bid_modifier else None,
                    "negative": cc.negative,
                    "status": get_enum_name(
                        client, "CampaignCriterionStatusEnum", cc.status
                    ),
                })

        return results

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_add_audience_exclusion(
    campaign_id: str,
    audience_id: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Excludes an audience from a campaign (negative targeting).

    Use this to prevent showing ads to specific audiences, e.g. exclude
    converters from acquisition campaigns, or exclude existing customers
    from prospecting campaigns.

    Args:
        campaign_id: The campaign ID to add the exclusion to.
        audience_id: The UserList ID to exclude (from google_list_audiences).
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        dict: Result with:
            - campaign_id: Campaign ID
            - audience_id: Excluded UserList ID
            - resource_name: Created criterion resource name

    Raises:
        ToolError: If the API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        campaign_resource = f"customers/{customer_id}/campaigns/{campaign_id}"
        user_list_resource = f"customers/{customer_id}/userLists/{audience_id}"

        criterion_service = client.get_service("CampaignCriterionService")
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_resource
        criterion.user_list.user_list = user_list_resource
        criterion.negative = True

        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=[op],
        )

        return {
            "campaign_id": campaign_id,
            "audience_id": audience_id,
            "resource_name": response.results[0].resource_name,
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
