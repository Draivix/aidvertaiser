"""Campaign automation tools for Google Ads API.

This module provides MCP tools for bulk campaign operations and
holiday-based campaign scheduling (pause on holidays, enable on business days).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from dateutil.easter import easter
from google.ads.googleads.errors import GoogleAdsException
from mcp.server.fastmcp.exceptions import ToolError

from ..server import mcp
from ..config import CONFIG_DIR
from .client import (
    get_google_ads_client,
    format_error,
    resolve_customer_id,
    get_enum_value,
    get_enum_name,
)

# --- Czech holiday calendar ---

# Fixed holidays (month, day, name)
_CZ_FIXED_HOLIDAYS = [
    (1, 1, "New Year's Day / Restoration of Czech Independence"),
    (5, 1, "Labor Day"),
    (5, 8, "Liberation Day"),
    (7, 5, "Saints Cyril and Methodius Day"),
    (7, 6, "Jan Hus Day"),
    (9, 28, "Czech Statehood Day"),
    (10, 28, "Independent Czechoslovak State Day"),
    (11, 17, "Struggle for Freedom and Democracy Day"),
    (12, 24, "Christmas Eve"),
    (12, 25, "Christmas Day"),
    (12, 26, "St. Stephen's Day"),
]

# Supported country calendars
_COUNTRY_FIXED_HOLIDAYS: dict[str, list[tuple[int, int, str]]] = {
    "CZ": _CZ_FIXED_HOLIDAYS,
    "SK": [
        (1, 1, "Day of the Establishment of the Slovak Republic"),
        (1, 6, "Epiphany"),
        (5, 1, "Labor Day"),
        (5, 8, "Victory over Fascism Day"),
        (7, 5, "Saints Cyril and Methodius Day"),
        (8, 29, "Slovak National Uprising Anniversary"),
        (9, 1, "Day of the Constitution"),
        (9, 15, "Our Lady of Sorrows"),
        (11, 1, "All Saints' Day"),
        (11, 17, "Struggle for Freedom and Democracy Day"),
        (12, 24, "Christmas Eve"),
        (12, 25, "Christmas Day"),
        (12, 26, "St. Stephen's Day"),
    ],
}

# Countries that observe Good Friday
_GOOD_FRIDAY_COUNTRIES = {"CZ", "SK", "DE", "GB"}
# Countries that observe Easter Monday
_EASTER_MONDAY_COUNTRIES = {"CZ", "SK", "DE", "PL", "GB", "FR", "IT"}


def get_holidays_for_year(year: int, country: str = "CZ") -> list[dict[str, str]]:
    """Get all holidays for a given year and country.

    Returns list of {"date": "YYYY-MM-DD", "name": "..."} sorted by date.
    """
    country = country.upper()
    fixed = _COUNTRY_FIXED_HOLIDAYS.get(country, _CZ_FIXED_HOLIDAYS)

    holidays = []
    for month, day, name in fixed:
        holidays.append({
            "date": date(year, month, day).isoformat(),
            "name": name,
        })

    # Easter-based holidays
    easter_sunday = easter(year)
    if country in _GOOD_FRIDAY_COUNTRIES:
        good_friday = easter_sunday - timedelta(days=2)
        holidays.append({
            "date": good_friday.isoformat(),
            "name": "Good Friday",
        })
    if country in _EASTER_MONDAY_COUNTRIES:
        easter_monday = easter_sunday + timedelta(days=1)
        holidays.append({
            "date": easter_monday.isoformat(),
            "name": "Easter Monday",
        })

    holidays.sort(key=lambda h: h["date"])
    return holidays


def is_holiday(d: date, country: str = "CZ") -> str | None:
    """Check if a date is a holiday. Returns holiday name or None."""
    for h in get_holidays_for_year(d.year, country):
        if h["date"] == d.isoformat():
            return h["name"]
    return None


def next_business_day(d: date, country: str = "CZ") -> date:
    """Find the next business day after date d (skipping weekends and holidays)."""
    candidate = d + timedelta(days=1)
    while candidate.weekday() >= 5 or is_holiday(candidate, country):
        candidate += timedelta(days=1)
    return candidate


# --- State file management ---

HOLIDAY_SCHEDULES_DIR = CONFIG_DIR / "holiday-schedules"
HOLIDAY_STATE_DIR = CONFIG_DIR / "holiday-state"


def _load_schedule(customer_id: str) -> dict:
    path = HOLIDAY_SCHEDULES_DIR / f"{customer_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_schedule(customer_id: str, data: dict) -> None:
    HOLIDAY_SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)
    path = HOLIDAY_SCHEDULES_DIR / f"{customer_id}.json"
    path.write_text(json.dumps(data, indent=2))


def _load_state(customer_id: str) -> dict:
    path = HOLIDAY_STATE_DIR / f"{customer_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"paused_campaigns": []}


def _save_state(customer_id: str, data: dict) -> None:
    HOLIDAY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = HOLIDAY_STATE_DIR / f"{customer_id}.json"
    path.write_text(json.dumps(data, indent=2))


# --- MCP Tools ---


@mcp.tool()
def google_bulk_set_campaign_status(
    campaign_ids: list[str],
    status: str,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Bulk pause or enable multiple campaigns in one API call.

    Uses GoogleAdsService.Mutate for batch efficiency (up to 10,000 ops/request).

    Args:
        campaign_ids: List of campaign IDs to update.
        status: Target status - ENABLED or PAUSED.
        customer_id: The Google Ads customer ID. Uses default if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Result with updated_count, failed details.
    """
    if status.upper() not in ("ENABLED", "PAUSED"):
        raise ToolError("status must be ENABLED or PAUSED")

    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")
        status_enum = get_enum_value(client, "CampaignStatusEnum", status.upper())

        mutate_ops = []
        for cid in campaign_ids:
            campaign_op = client.get_type("MutateOperation")
            campaign = campaign_op.campaign_operation.update
            campaign.resource_name = f"customers/{customer_id}/campaigns/{cid}"
            campaign.status = status_enum
            campaign_op.campaign_operation.update_mask.paths.append("status")
            mutate_ops.append(campaign_op)

        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=mutate_ops,
        )

        return {
            "updated_count": len(response.mutate_operation_responses),
            "campaign_ids": campaign_ids,
            "new_status": status.upper(),
            "status": "updated",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_list_holidays(
    country: str = "CZ",
    year: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Lists state holidays for a country and year.

    Includes both fixed holidays and Easter-based movable holidays.

    Args:
        country: Country code - "CZ" (Czech Republic) or "SK" (Slovakia).
            Default: CZ.
        year: Year to list holidays for. Default: current year.

    Returns:
        list[dict]: Holidays with date (YYYY-MM-DD), name, day_of_week,
            and is_weekend flag.
    """
    if year is None:
        year = date.today().year

    holidays = get_holidays_for_year(year, country)
    for h in holidays:
        d = date.fromisoformat(h["date"])
        h["day_of_week"] = d.strftime("%A")
        h["is_weekend"] = d.weekday() >= 5

    return holidays


@mcp.tool()
def google_set_holiday_schedule(
    country: str = "CZ",
    campaign_ids: Optional[list[str]] = None,
    label_id: Optional[str] = None,
    extra_holidays: Optional[list[str]] = None,
    year: Optional[int] = None,
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Configures holiday pausing for campaigns.

    Stores a schedule that google_run_holiday_check reads daily to
    automatically pause campaigns on holidays and re-enable them after.

    Target campaigns are selected by:
    - explicit campaign_ids list, OR
    - all campaigns with label_id, OR
    - all ENABLED campaigns (if neither specified)

    Args:
        country: Country code for holiday calendar ("CZ" or "SK"). Default: CZ.
        campaign_ids: Specific campaign IDs to pause on holidays.
        label_id: Alternative - pause all campaigns with this label.
        extra_holidays: Additional holiday dates (YYYY-MM-DD) beyond
            the built-in calendar (e.g., company-specific days off).
        year: Year for the schedule. Default: current year.
        customer_id: The Google Ads customer ID. Uses default if not provided.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Schedule summary with holiday count and next upcoming holiday.
    """
    customer_id = resolve_customer_id(customer_id)
    if not customer_id:
        raise ToolError("No customer_id provided and no default configured")

    if year is None:
        year = date.today().year

    holidays = get_holidays_for_year(year, country)
    holiday_dates = [h["date"] for h in holidays]

    if extra_holidays:
        for eh in extra_holidays:
            if eh not in holiday_dates:
                holiday_dates.append(eh)
                holidays.append({"date": eh, "name": "Custom holiday"})
        holiday_dates.sort()
        holidays.sort(key=lambda h: h["date"])

    schedule = {
        "customer_id": customer_id,
        "country": country.upper(),
        "year": year,
        "campaign_ids": campaign_ids,
        "label_id": label_id,
        "login_customer_id": login_customer_id,
        "holidays": holiday_dates,
        "extra_holidays": extra_holidays or [],
    }

    _save_schedule(customer_id, schedule)

    # Find next upcoming holiday
    today = date.today()
    upcoming = [h for h in holidays if date.fromisoformat(h["date"]) >= today]
    weekday_holidays = [
        h for h in upcoming
        if date.fromisoformat(h["date"]).weekday() < 5
    ]

    return {
        "customer_id": customer_id,
        "country": country.upper(),
        "year": year,
        "total_holidays": len(holiday_dates),
        "weekday_holidays_remaining": len(weekday_holidays),
        "next_holiday": weekday_holidays[0] if weekday_holidays else None,
        "targeting": (
            f"campaigns: {campaign_ids}" if campaign_ids
            else f"label: {label_id}" if label_id
            else "all ENABLED campaigns"
        ),
        "config_path": str(HOLIDAY_SCHEDULES_DIR / f"{customer_id}.json"),
        "status": "configured",
    }


@mcp.tool()
def google_run_holiday_check(
    customer_id: Optional[str] = None,
    check_date: Optional[str] = None,
    dry_run: bool = False,
    login_customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """Checks today against holiday schedule and pauses/enables campaigns.

    Designed to be called daily (e.g., via cron at 00:05).

    Logic:
    - If today IS a holiday → pause targeted campaigns, record state
    - If today is NOT a holiday → re-enable campaigns that were auto-paused

    Only re-enables campaigns that were paused by this tool, not manually paused ones.

    Args:
        customer_id: The Google Ads customer ID. Uses default if not provided.
        check_date: Override date to check (YYYY-MM-DD). Default: today.
        dry_run: If True, report what would happen without making changes.
        login_customer_id: Optional MCC account ID.

    Returns:
        dict: Action taken, campaigns affected, next holiday.
    """
    try:
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        schedule = _load_schedule(customer_id)
        if not schedule:
            raise ToolError(
                f"No holiday schedule configured for customer {customer_id}. "
                "Use google_set_holiday_schedule first."
            )

        state = _load_state(customer_id)
        today = date.fromisoformat(check_date) if check_date else date.today()
        today_str = today.isoformat()
        country = schedule.get("country", "CZ")

        holiday_name = is_holiday(today, country)
        is_weekend = today.weekday() >= 5
        should_pause = holiday_name is not None or is_weekend

        # Resolve target campaigns
        target_campaign_ids = schedule.get("campaign_ids")
        label_id = schedule.get("label_id")
        lid = login_customer_id or schedule.get("login_customer_id")

        client = get_google_ads_client(login_customer_id=lid)
        ga_service = client.get_service("GoogleAdsService")

        if target_campaign_ids:
            campaigns_to_manage = target_campaign_ids
        elif label_id:
            response = ga_service.search_stream(
                customer_id=customer_id,
                query=f"""
                    SELECT campaign.id
                    FROM campaign_label
                    WHERE label.id = {label_id}
                      AND campaign.status IN ('ENABLED', 'PAUSED')
                """,
            )
            campaigns_to_manage = []
            for batch in response:
                for row in batch.results:
                    campaigns_to_manage.append(str(row.campaign.id))
        else:
            response = ga_service.search_stream(
                customer_id=customer_id,
                query="""
                    SELECT campaign.id
                    FROM campaign
                    WHERE campaign.status IN ('ENABLED', 'PAUSED')
                      AND campaign.serving_status != 'ENDED'
                """,
            )
            campaigns_to_manage = []
            for batch in response:
                for row in batch.results:
                    campaigns_to_manage.append(str(row.campaign.id))

        action = "none"
        affected = []
        already_paused = state.get("paused_campaigns", [])

        if should_pause:
            # Find ENABLED campaigns that need pausing
            if campaigns_to_manage:
                ids_str = ", ".join(campaigns_to_manage)
                response = ga_service.search_stream(
                    customer_id=customer_id,
                    query=f"""
                        SELECT campaign.id, campaign.name
                        FROM campaign
                        WHERE campaign.id IN ({ids_str})
                          AND campaign.status = 'ENABLED'
                    """,
                )
                to_pause = []
                for batch in response:
                    for row in batch.results:
                        to_pause.append({
                            "id": str(row.campaign.id),
                            "name": row.campaign.name,
                        })

                if to_pause and not dry_run:
                    pause_ids = [c["id"] for c in to_pause]
                    status_enum = get_enum_value(client, "CampaignStatusEnum", "PAUSED")
                    mutate_ops = []
                    for cid in pause_ids:
                        op = client.get_type("MutateOperation")
                        campaign = op.campaign_operation.update
                        campaign.resource_name = f"customers/{customer_id}/campaigns/{cid}"
                        campaign.status = status_enum
                        op.campaign_operation.update_mask.paths.append("status")
                        mutate_ops.append(op)

                    ga_service.mutate(
                        customer_id=customer_id,
                        mutate_operations=mutate_ops,
                    )

                    # Track which campaigns we paused
                    new_paused = list(set(already_paused + pause_ids))
                    state["paused_campaigns"] = new_paused
                    state["paused_date"] = today_str
                    state["paused_reason"] = holiday_name or "weekend"
                    _save_state(customer_id, state)

                action = "paused"
                affected = to_pause

        else:
            # Re-enable campaigns that were auto-paused
            if already_paused:
                if not dry_run:
                    status_enum = get_enum_value(client, "CampaignStatusEnum", "ENABLED")
                    mutate_ops = []
                    for cid in already_paused:
                        op = client.get_type("MutateOperation")
                        campaign = op.campaign_operation.update
                        campaign.resource_name = f"customers/{customer_id}/campaigns/{cid}"
                        campaign.status = status_enum
                        op.campaign_operation.update_mask.paths.append("status")
                        mutate_ops.append(op)

                    ga_service.mutate(
                        customer_id=customer_id,
                        mutate_operations=mutate_ops,
                    )

                    state["paused_campaigns"] = []
                    state["enabled_date"] = today_str
                    _save_state(customer_id, state)

                action = "enabled"
                affected = [{"id": cid} for cid in already_paused]

        # Find next holiday
        upcoming = [
            h for h in get_holidays_for_year(today.year, country)
            if date.fromisoformat(h["date"]) > today
            and date.fromisoformat(h["date"]).weekday() < 5
        ]

        return {
            "check_date": today_str,
            "is_holiday": holiday_name,
            "is_weekend": is_weekend,
            "action": action,
            "dry_run": dry_run,
            "campaigns_affected": len(affected),
            "campaigns": affected,
            "next_weekday_holiday": upcoming[0] if upcoming else None,
            "status": "checked",
        }

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e


@mcp.tool()
def google_disable_auto_recommendations(
    customer_id: Optional[str] = None,
    login_customer_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Disables ALL auto-applied recommendation subscriptions on a Google Ads account.

    Google Ads auto-applies recommendations like enabling Display Network,
    switching bidding strategies, adding broad match keywords, etc. These
    can silently undo manual campaign settings. This tool pauses all active
    subscriptions.

    Common auto-applied recommendations that cause problems:
    - DISPLAY_EXPANSION_OPT_IN: Re-enables Display Network on Search campaigns
    - MAXIMIZE_CONVERSIONS_OPT_IN: Switches bidding strategy
    - USE_BROAD_MATCH_KEYWORD: Changes keyword match types
    - TARGET_CPA_OPT_IN / TARGET_ROAS_OPT_IN: Changes bidding
    - OPTIMIZE_AD_ROTATION: Overrides ad rotation settings

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
            Uses default from config if not provided.
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.
        dry_run: If True, list subscriptions without disabling them.

    Returns:
        dict: Result with disabled count, subscription details, and status.

    Raises:
        ToolError: If API request fails.
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = resolve_customer_id(customer_id)
        if not customer_id:
            raise ToolError("No customer_id provided and no default configured")

        ga_service = client.get_service("GoogleAdsService")

        # Step 1: Find all ENABLED recommendation subscriptions
        query = """
            SELECT
                recommendation_subscription.resource_name,
                recommendation_subscription.type,
                recommendation_subscription.status
            FROM recommendation_subscription
            WHERE recommendation_subscription.status = 'ENABLED'
        """
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        enabled_subs = []
        skipped_unknown = 0
        for batch in response:
            for row in batch.results:
                sub = row.recommendation_subscription
                type_name = get_enum_name(
                    client, "RecommendationTypeEnum", sub.type_
                )
                # Get raw integer value for unknown types
                raw_type_int = int(sub.type_) if hasattr(sub.type_, '__int__') else sub.type_
                if type_name in ("UNKNOWN", "UNSPECIFIED"):
                    skipped_unknown += 1
                    # Still include them — try to disable via resource_name
                    enabled_subs.append({
                        "resource_name": sub.resource_name,
                        "type": f"UNKNOWN (raw={raw_type_int})",
                        "raw_type": raw_type_int,
                    })
                    continue
                enabled_subs.append({
                    "resource_name": sub.resource_name,
                    "type": type_name,
                    "raw_type": raw_type_int,
                })

        if not enabled_subs:
            return {
                "customer_id": customer_id,
                "enabled_count": 0,
                "disabled_count": 0,
                "skipped_unknown": skipped_unknown,
                "subscriptions": [],
                "status": "no_enabled_subscriptions",
            }

        if dry_run:
            return {
                "customer_id": customer_id,
                "enabled_count": len(enabled_subs),
                "disabled_count": 0,
                "skipped_unknown": skipped_unknown,
                "dry_run": True,
                "subscriptions": enabled_subs,
                "status": "dry_run",
            }

        # Step 2: Build mutate operations to PAUSE each subscription
        sub_service = client.get_service("RecommendationSubscriptionService")
        paused_status = get_enum_value(
            client, "RecommendationSubscriptionStatusEnum", "PAUSED"
        )

        operations = []
        for sub in enabled_subs:
            op = client.get_type("RecommendationSubscriptionOperation")
            op.update.resource_name = sub["resource_name"]
            op.update.status = paused_status
            op.update_mask.paths.append("status")
            operations.append(op)

        response = sub_service.mutate_recommendation_subscription(
            customer_id=customer_id,
            operations=operations,
        )

        disabled_names = [r.resource_name for r in response.results]

        # Step 3: Verify by re-querying
        verify_query = """
            SELECT
                recommendation_subscription.resource_name,
                recommendation_subscription.type,
                recommendation_subscription.status
            FROM recommendation_subscription
            WHERE recommendation_subscription.status = 'ENABLED'
        """
        verify_response = ga_service.search_stream(
            customer_id=customer_id,
            query=verify_query,
        )
        still_enabled = []
        for batch in verify_response:
            for row in batch.results:
                sub = row.recommendation_subscription
                still_enabled.append(get_enum_name(
                    client, "RecommendationTypeEnum", sub.type_
                ))

        result = {
            "customer_id": customer_id,
            "disabled_count": len(disabled_names),
            "skipped_unknown": skipped_unknown,
            "subscriptions_disabled": enabled_subs,
            "status": "all_disabled",
        }

        if still_enabled:
            result["status"] = "partial_failure"
            result["still_enabled"] = still_enabled
            result["warning"] = (
                f"{len(still_enabled)} subscriptions are STILL enabled after "
                f"mutation. Check the Google Ads UI manually."
            )

        return result

    except GoogleAdsException as e:
        raise ToolError(format_error(e)) from e
