"""Google Ads module for Unified Ads MCP.

This module provides Google Ads API client factory and tool implementations
for campaign management, ad groups, ads, keywords, reporting, and other operations.

The client uses OAuth2 authentication handled by the auth module.

Submodules:
    - client: Google Ads API client initialization
    - campaigns: Campaign management tools
    - ad_groups: Ad group management tools
    - ads: Ad management tools
    - keywords: Keyword management tools
    - reporting: Reporting and GAQL query tools

Example:
    The tools are automatically registered with the MCP server when
    this module is imported:

        from unified_ads_mcp import google
        # All Google Ads tools are now available

    Or import specific modules:

        from unified_ads_mcp.google import campaigns
        from unified_ads_mcp.google.campaigns import google_list_campaigns
"""

# Import client factory
from unified_ads_mcp.google.client import (
    get_google_ads_client,
    GoogleAdsClientFactory,
    get_login_customer_id,
    clean_customer_id,
    format_value,
    format_error,
)

# Import all tool modules to register them with the MCP server
from unified_ads_mcp.google import campaigns
from unified_ads_mcp.google import ad_groups
from unified_ads_mcp.google import ads
from unified_ads_mcp.google import keywords
from unified_ads_mcp.google import reporting
from unified_ads_mcp.google import assets
from unified_ads_mcp.google import asset_groups
from unified_ads_mcp.google import conversions
from unified_ads_mcp.google import labels
from unified_ads_mcp.google import automation
from unified_ads_mcp.google import audiences

__all__ = [
    # Client factory and utilities
    "get_google_ads_client",
    "GoogleAdsClientFactory",
    "get_login_customer_id",
    "clean_customer_id",
    "format_value",
    "format_error",
    # Tool modules
    "campaigns",
    "ad_groups",
    "ads",
    "keywords",
    "reporting",
    "assets",
    "asset_groups",
    "conversions",
    "labels",
    "automation",
    "audiences",
]
