"""Meta Ads MCP Tools.

This package provides MCP tools for managing Meta Ads (Facebook/Instagram)
campaigns, ad sets, ads, creatives, targeting, and reporting.

Modules:
    - client: API client factory and authentication
    - campaigns: Campaign management tools
    - adsets: Ad set management tools
    - ads: Ad management tools
    - creatives: Creative and image management tools
    - targeting: Targeting search and audience estimation tools
    - insights: Performance reporting tools
"""

# Import client factory
from unified_ads_mcp.meta.client import (
    get_meta_api,
    get_ad_account,
    MetaAdsClientFactory,
    make_api_request,
    ensure_account_prefix,
    meta_api_tool,
)

# Import all tool modules to register their tools with the MCP server
from unified_ads_mcp.meta import campaigns
from unified_ads_mcp.meta import adsets
from unified_ads_mcp.meta import ads
from unified_ads_mcp.meta import creatives
from unified_ads_mcp.meta import targeting
from unified_ads_mcp.meta import insights
from unified_ads_mcp.meta import conversions
from unified_ads_mcp.meta import audiences

__all__ = [
    # Client functions
    "get_meta_api",
    "get_ad_account",
    "MetaAdsClientFactory",
    "make_api_request",
    "ensure_account_prefix",
    "meta_api_tool",
    # Tool modules
    "campaigns",
    "adsets",
    "ads",
    "creatives",
    "targeting",
    "insights",
    "conversions",
    "audiences",
]
