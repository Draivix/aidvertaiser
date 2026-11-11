# Aidvertaiser

AI-powered advertising management via [MCP](https://modelcontextprotocol.io). 232 tools across 8 platforms — Google Ads, Meta Ads, GA4, Search Console, Tag Manager, Matomo, Bing Webmaster, and PageSpeed Insights.

Open source. One server. Works with Claude, Cursor, Windsurf, and any MCP client.

## Platforms

| Platform | Prefix | Tools | Auth |
|----------|--------|------:|------|
| Google Ads | `google_` | 81 | OAuth (browser) |
| Meta Ads | `meta_` | 40 | OAuth (browser) |
| Google Analytics (GA4) | `ga4_` | 31 | OAuth (browser) |
| Google Search Console | `gsc_` | 18 | OAuth (browser) |
| Google Tag Manager | `gtm_` | 14 | OAuth (browser) |
| Matomo Analytics | `matomo_` | 24 | API token |
| Bing Webmaster Tools | `bing_` | 21 | API key |
| PageSpeed Insights | `pagespeed_` | 3 | API key (optional) |

## Installation

```bash
# From source
git clone https://github.com/Draivix/aidvertaiser.git
cd aidvertaiser
uv sync
```

## Quick Start

Add to your MCP client config (e.g. `~/.claude/mcp_servers.json`):

```json
{
  "aidvertaiser": {
    "command": "uv",
    "args": ["run", "--directory", "/path/to/aidvertaiser", "unified-ads-mcp"]
  }
}
```

Or run directly:

```bash
uv run unified-ads-mcp
```

## Configuration

All config files live in `~/.unified-ads-mcp/`. Create this directory first:

```bash
mkdir -p ~/.unified-ads-mcp
```

OAuth tokens are cached here automatically after first browser-based authentication.

### Google Ads

Create `~/.unified-ads-mcp/google-ads.yaml`:

```yaml
developer_token: YOUR_DEVELOPER_TOKEN
client_id: YOUR_CLIENT_ID
client_secret: YOUR_CLIENT_SECRET
login_customer_id: YOUR_MCC_ID          # Optional, for MCC access
default_customer_id: YOUR_CUSTOMER_ID   # Optional, skip account listing
```

**Env var override:** `GOOGLE_ADS_CREDENTIALS=/path/to/google-ads.yaml`

**Tip:** Set `ONLY_DEFAULT_ACCOUNT=1` to disable `google_list_accounts` and force using the default customer ID everywhere. Useful when you only manage one account.

### Meta Ads

Create `~/.unified-ads-mcp/meta-ads.yaml`:

```yaml
app_id: YOUR_APP_ID
app_secret: YOUR_APP_SECRET
access_token: YOUR_TOKEN              # Optional, bypasses browser OAuth
default_account_id: act_XXXXXXXXXX    # Optional
```

Or set environment variables: `META_APP_ID`, `META_APP_SECRET`, `META_ACCESS_TOKEN`.

**Env var override:** `META_ADS_CREDENTIALS=/path/to/meta-ads.yaml`

### Google Analytics (GA4)

Create `~/.unified-ads-mcp/google-analytics.yaml`:

```yaml
client_id: YOUR_CLIENT_ID
client_secret: YOUR_CLIENT_SECRET
default_property_id: YOUR_PROPERTY_ID   # Optional
```

Falls back to `google-ads.yaml` for `client_id`/`client_secret` (same Google Cloud project).

**Env var override:** `GOOGLE_ANALYTICS_CREDENTIALS=/path/to/google-analytics.yaml`

### Google Search Console

Uses `google-ads.yaml` for client credentials (same Google Cloud project). No separate config needed.

Also provides the **Indexing API** for submitting URLs. Requires the *Web Search Indexing API* enabled in Google Cloud Console.

### Google Tag Manager

Create `~/.unified-ads-mcp/google-tagmanager.yaml`:

```yaml
client_id: YOUR_CLIENT_ID
client_secret: YOUR_CLIENT_SECRET
default_account_id: YOUR_GTM_ACCOUNT_ID       # Optional
default_container_id: YOUR_GTM_CONTAINER_ID   # Optional
```

Falls back to `google-ads.yaml` for `client_id`/`client_secret`.

**Env var override:** `GOOGLE_TAGMANAGER_CREDENTIALS=/path/to/google-tagmanager.yaml`

### Matomo Analytics

Create `~/.unified-ads-mcp/matomo.yaml`:

```yaml
url: https://your-matomo-instance.com
token_auth: YOUR_API_TOKEN
default_site_id: 1   # Optional
```

**Env var override:** `MATOMO_CREDENTIALS=/path/to/matomo.yaml`

### Bing Webmaster Tools

Create `~/.unified-ads-mcp/bing-webmaster.yaml`:

```yaml
api_key: YOUR_API_KEY
default_site_url: https://yoursite.com   # Optional
```

Get the API key from: Bing Webmaster Tools > Settings > API Access > Generate API Key.

**Env var override:** `BING_WEBMASTER_CREDENTIALS=/path/to/bing-webmaster.yaml`

### PageSpeed Insights

No config needed for basic usage (rate-limited to ~5 requests/min without an API key).

For higher limits, create `~/.unified-ads-mcp/pagespeed.yaml`:

```yaml
api_key: YOUR_GOOGLE_API_KEY   # 25,000 requests/day
```

Or set `PAGESPEED_API_KEY` env var.

## Available Tools

### Google Ads — 81 tools

**Accounts & Reporting:**
- `google_list_accounts` — List accessible Google Ads accounts
- `google_get_account_summary` — Account overview with metrics
- `google_run_query` — Execute raw GAQL queries

**Campaigns:**
- `google_list_campaigns` — List campaigns with optional status filter
- `google_get_campaign` — Single campaign details
- `google_create_campaign` — Create a Search campaign
- `google_create_pmax_campaign` — Create a Performance Max campaign
- `google_create_demand_gen_video_campaign` — Create a YouTube video ad (Shorts, in-stream, in-feed) as a Demand Gen campaign in one atomic call; `validate_only` dry run
- `google_search_targeting_segments` — Find affinity, in-market, life-event, detailed-demographic (company size, industry) and custom segments by name
- `google_create_custom_segment` — Create a custom segment from keywords or URLs (interest, purchase intent or Google searches)
- `google_set_ad_group_audience` — Restrict a Demand Gen (YouTube) ad group to an audience: segments, remarketing lists, age, exclusions; `validate_only` dry run
- `google_update_campaign` — Update campaign settings
- `google_delete_campaign` — Remove a campaign
- `google_get_campaign_performance` — Campaign performance metrics
- `google_set_campaign_conversion_goal` — Set conversion goals
- `google_set_campaign_locations` — Set geographic targeting
- `google_set_campaign_languages` — Set language targeting
- `google_set_ad_schedule` — Set day/time ad scheduling
- `google_set_device_bid_adjustment` — Adjust bids by device type
- `google_set_demographic_exclusions` — Exclude age/gender demographics
- `google_set_tracking_template` — Set tracking URL template at account or campaign level

**Bulk Operations & Automation:**
- `google_bulk_set_campaign_status` — Pause/enable multiple campaigns at once
- `google_bulk_update_keywords` — Batch update keyword status/bids
- `google_list_holidays` — List state holidays for a country
- `google_run_holiday_check` — Check if today is a holiday
- `google_set_holiday_schedule` — Auto-pause campaigns on holidays

**Labels:**
- `google_list_labels` — List all labels
- `google_create_label` — Create a label
- `google_delete_label` — Remove a label
- `google_assign_label_to_campaigns` — Assign label to campaigns
- `google_remove_label_from_campaigns` — Remove label from campaigns
- `google_get_campaigns_by_label` — Get campaigns by label

**Ad Groups:**
- `google_list_ad_groups` — List ad groups in a campaign
- `google_get_ad_group` — Single ad group details
- `google_create_ad_group` — Create an ad group
- `google_update_ad_group` — Update ad group settings
- `google_delete_ad_group` — Remove an ad group

**Ads:**
- `google_list_ads` — List ads in an ad group
- `google_get_ad` — Single ad details
- `google_create_responsive_search_ad` — Create a responsive search ad
- `google_update_ad` — Update ad content
- `google_delete_ad` — Remove an ad
- `google_get_ad_performance` — Ad performance metrics

**Keywords:**
- `google_list_keywords` — List keywords in an ad group
- `google_get_keyword` — Single keyword details with Quality Score
- `google_add_keywords` — Add keywords to an ad group
- `google_update_keyword` — Update keyword bid/status
- `google_remove_keyword` — Remove a keyword
- `google_get_keyword_performance` — Keyword performance metrics
- `google_get_search_terms_report` — Search terms triggering ads
- `google_add_negative_keywords` — Add negative keywords (ad group level)
- `google_list_negative_keywords` — List negative keywords (ad group level)
- `google_remove_negative_keyword` — Remove a negative keyword (ad group level)
- `google_add_campaign_negative_keywords` — Add negative keywords (campaign level)
- `google_list_campaign_negative_keywords` — List negative keywords (campaign level)
- `google_remove_campaign_negative_keyword` — Remove a negative keyword (campaign level)

**Conversions:**
- `google_list_conversion_actions` — List conversion actions
- `google_get_conversion_action` — Conversion action details
- `google_create_conversion_action` — Create a conversion action
- `google_update_conversion_action` — Update conversion action
- `google_delete_conversion_action` — Remove a conversion action
- `google_get_conversion_action_performance` — Conversion performance
- `google_upload_offline_conversions` — Upload offline conversion data
- `google_upload_enhanced_conversions` — Upload enhanced conversions
- `google_list_customer_conversion_goals` — List account-level conversion goals
- `google_update_customer_conversion_goal` — Update conversion goal settings

**Assets:**
- `google_list_assets` — List account assets
- `google_create_text_asset` — Create a text asset
- `google_create_text_assets_batch` — Create multiple text assets
- `google_create_image_asset` — Create an image asset
- `google_link_asset_to_campaign` — Link asset to a campaign
- `google_create_sitelink_asset` — Create a sitelink extension
- `google_create_callout_asset` — Create a callout extension
- `google_create_structured_snippet_asset` — Create a structured snippet extension

**Performance Max Asset Groups:**
- `google_list_asset_groups` — List PMax asset groups
- `google_get_asset_group` — Asset group details
- `google_create_asset_group` — Create a PMax asset group
- `google_update_asset_group` — Update asset group
- `google_delete_asset_group` — Remove an asset group
- `google_add_asset_group_asset` — Add asset to group
- `google_remove_asset_group_asset` — Remove asset from group
- `google_get_asset_automation_settings` — Get auto-asset settings
- `google_update_asset_automation_settings` — Update auto-asset settings
- `google_list_auto_created_assets` — List auto-created assets
- `google_remove_auto_created_asset` — Remove an auto-created asset

### Meta Ads — 40 tools

**Accounts:**
- `meta_list_accounts` — List accessible ad accounts
- `meta_get_account_info` — Account details
- `meta_get_login_link` — Get OAuth login URL

**Campaigns:**
- `meta_list_campaigns` — List campaigns
- `meta_get_campaign_details` — Campaign details
- `meta_create_campaign` — Create a campaign
- `meta_update_campaign` — Update campaign settings

**Ad Sets:**
- `meta_list_adsets` — List ad sets
- `meta_get_adset_details` — Ad set details
- `meta_create_adset` — Create an ad set
- `meta_update_adset` — Update ad set settings

**Ads & Creatives:**
- `meta_list_ads` — List ads
- `meta_get_ad_details` — Ad details
- `meta_create_ad` — Create an ad
- `meta_update_ad` — Update ad settings
- `meta_get_ad_creatives` — Creative details
- `meta_create_creative` — Create a creative
- `meta_update_creative` — Update a creative
- `meta_upload_image` — Upload image for ads

**Insights:**
- `meta_get_insights` — Performance reports

**Targeting:**
- `meta_search_interests` — Search interest targeting
- `meta_get_interest_suggestions` — Interest suggestions
- `meta_search_behaviors` — Search behavior targeting
- `meta_search_geo_locations` — Search geographic locations
- `meta_estimate_audience_size` — Estimate audience size

**Tracking Pixels:**
- `meta_list_pixels` — List tracking pixels
- `meta_get_pixel` — Pixel details
- `meta_create_pixel` — Create a pixel
- `meta_update_pixel` — Update pixel settings
- `meta_get_pixel_stats` — Pixel event statistics

**Conversions:**
- `meta_send_conversion_event` — Send a Conversions API event
- `meta_send_conversion_events_batch` — Send batch events
- `meta_list_custom_conversions` — List custom conversions
- `meta_get_custom_conversion` — Custom conversion details
- `meta_create_custom_conversion` — Create custom conversion
- `meta_update_custom_conversion` — Update custom conversion
- `meta_delete_custom_conversion` — Delete custom conversion
- `meta_list_offline_conversion_sets` — List offline conversion sets
- `meta_create_offline_conversion_set` — Create offline conversion set
- `meta_upload_offline_conversions` — Upload offline conversions

### Google Analytics (GA4) — 31 tools

**Accounts & Properties:**
- `ga4_list_accounts` — List GA4 accounts
- `ga4_list_account_summaries` — Account summaries
- `ga4_list_properties` — List properties in an account
- `ga4_get_property` — Property details
- `ga4_create_property` — Create a property
- `ga4_update_property` — Update property settings
- `ga4_delete_property` — Remove a property

**Data Streams:**
- `ga4_list_data_streams` — List data streams
- `ga4_get_data_stream` — Data stream details
- `ga4_create_web_data_stream` — Create web data stream
- `ga4_create_android_data_stream` — Create Android data stream
- `ga4_create_ios_data_stream` — Create iOS data stream
- `ga4_update_data_stream` — Update data stream
- `ga4_delete_data_stream` — Remove a data stream
- `ga4_get_tracking_code` — Get tracking code snippet

**Reporting:**
- `ga4_run_report` — Standard analytics report
- `ga4_run_realtime_report` — Real-time data
- `ga4_get_metadata` — Available dimensions and metrics

**Key Events:**
- `ga4_list_key_events` — List key events (conversions)
- `ga4_create_key_event` — Create a key event
- `ga4_update_key_event` — Update key event
- `ga4_delete_key_event` — Remove a key event

**Custom Dimensions:**
- `ga4_list_custom_dimensions` — List custom dimensions
- `ga4_create_custom_dimension` — Create a custom dimension
- `ga4_update_custom_dimension` — Update display name or description
- `ga4_archive_custom_dimension` — Archive (soft-delete) a custom dimension

**Measurement Protocol:**
- `ga4_send_measurement_protocol_event` — Send server-side event
- `ga4_send_measurement_protocol_batch` — Send batch server-side events
- `ga4_list_measurement_protocol_secrets` — List API secrets for a data stream
- `ga4_create_measurement_protocol_secret` — Create an API secret
- `ga4_delete_measurement_protocol_secret` — Delete an API secret

### Google Search Console — 18 tools

**Sites:**
- `gsc_list_sites` — List registered sites
- `gsc_get_site` — Site details
- `gsc_add_site` — Register a site
- `gsc_delete_site` — Remove a site

**Search Analytics:**
- `gsc_search_analytics` — Full search traffic data (clicks, impressions, CTR, position)
- `gsc_search_analytics_by_query` — Top search queries
- `gsc_search_analytics_by_page` — Top pages by performance

**URL Inspection:**
- `gsc_inspect_url` — Check indexing status

**Indexing API:**
- `gsc_submit_url_for_indexing` — Submit a URL for indexing
- `gsc_submit_urls_for_indexing` — Batch submit URLs (~200/day limit)
- `gsc_get_indexing_notification_status` — Check indexing notification status

**Sitemaps:**
- `gsc_list_sitemaps` — List submitted sitemaps
- `gsc_get_sitemap` — Sitemap details
- `gsc_submit_sitemap` — Submit a sitemap
- `gsc_delete_sitemap` — Remove a sitemap

**Verification:**
- `gsc_get_verification_token` — Get verification token
- `gsc_verify_site` — Verify site ownership
- `gsc_list_verified_sites` — List all verified sites

### Google Tag Manager — 14 tools

**Accounts & Containers:**
- `gtm_list_accounts` — List GTM accounts
- `gtm_list_containers` — List containers
- `gtm_list_workspaces` — List workspaces

**Tags:**
- `gtm_list_tags` — List tags in a workspace
- `gtm_create_tag` — Create a tag (GA4, Google Ads, custom HTML, etc.)
- `gtm_update_tag` — Update tag settings
- `gtm_delete_tag` — Remove a tag

**Triggers:**
- `gtm_list_triggers` — List triggers
- `gtm_create_trigger` — Create a trigger (page view, click, custom event, etc.)
- `gtm_update_trigger` — Update trigger settings
- `gtm_delete_trigger` — Remove a trigger

**Versions & Publishing:**
- `gtm_list_versions` — Version history
- `gtm_create_version` — Create a version from workspace
- `gtm_publish_version` — Publish a version (makes changes live)

### Matomo Analytics — 24 tools

**Sites:**
- `matomo_list_sites` — List tracked websites
- `matomo_get_site` — Site details
- `matomo_add_site` — Add a website
- `matomo_update_site` — Update site settings
- `matomo_delete_site` — Remove a site
- `matomo_get_site_urls` — Get URLs for a site
- `matomo_get_tracking_code` — Get tracking code snippet

**Reporting:**
- `matomo_get_visits_summary` — Basic visit metrics
- `matomo_get_page_urls` — Page URL performance
- `matomo_get_entry_pages` — Top entry pages
- `matomo_get_exit_pages` — Top exit pages
- `matomo_get_referrers` — Referrer sources
- `matomo_get_referrer_types` — Referrer type breakdown
- `matomo_get_search_keywords` — Internal search keywords
- `matomo_get_countries` — Visitor countries
- `matomo_get_devices` — Visitor devices

**Live:**
- `matomo_get_live_counters` — Real-time active visitors
- `matomo_get_last_visits` — Recent visit details
- `matomo_get_visitor_profile` — Individual visitor profile

**Goals:**
- `matomo_list_goals` — List goals
- `matomo_add_goal` — Create a goal
- `matomo_update_goal` — Update a goal
- `matomo_delete_goal` — Remove a goal
- `matomo_get_goal_report` — Goal conversion report

### Bing Webmaster Tools — 21 tools

**Sites:**
- `bing_list_sites` — List registered sites
- `bing_add_site` — Register a site
- `bing_verify_site` — Verify site ownership
- `bing_remove_site` — Remove a site

**URL Submission:**
- `bing_submit_url` — Submit a URL for crawling
- `bing_submit_url_batch` — Batch submit up to 500 URLs
- `bing_get_url_submission_quota` — Check daily submission quota

**Sitemaps:**
- `bing_list_sitemaps` — List submitted sitemaps
- `bing_submit_sitemap` — Submit a sitemap
- `bing_remove_sitemap` — Remove a sitemap

**Search Analytics:**
- `bing_get_rank_and_traffic_stats` — Overall search performance
- `bing_get_query_stats` — Per-query metrics
- `bing_get_page_stats` — Per-page metrics

**Crawl Management:**
- `bing_get_crawl_stats` — Crawl activity statistics
- `bing_get_crawl_issues` — Crawl errors
- `bing_get_crawl_settings` — Current crawl rate settings
- `bing_save_crawl_settings` — Update crawl rate (1–10)

**Keyword Research:**
- `bing_get_keyword` — Search volume for a keyword
- `bing_get_related_keywords` — Related keyword suggestions

**Link Analysis:**
- `bing_get_link_counts` — Total inbound link counts
- `bing_get_url_links` — Detailed inbound link list

### PageSpeed Insights — 3 tools

- `pagespeed_analyze` — Full Lighthouse audit (scores, Core Web Vitals, opportunities)
- `pagespeed_compare` — Mobile vs desktop side-by-side comparison
- `pagespeed_core_web_vitals` — Chrome UX Report field data (LCP, INP, CLS, FCP, TTFB)

## Required Google Cloud APIs

Enable these in your [Google Cloud Console](https://console.cloud.google.com/apis/library):

| API | Required for | Enable command |
|-----|-------------|----------------|
| Google Ads API | `google_*` | `gcloud services enable googleads.googleapis.com` |
| Google Analytics Admin API | `ga4_*` | `gcloud services enable analyticsadmin.googleapis.com` |
| Google Analytics Data API | `ga4_run_report`, `ga4_run_realtime_report` | `gcloud services enable analyticsdata.googleapis.com` |
| Google Search Console API | `gsc_*` | `gcloud services enable searchconsole.googleapis.com` |
| Web Search Indexing API | `gsc_submit_url_for_indexing` | `gcloud services enable indexing.googleapis.com` |
| Tag Manager API | `gtm_*` | `gcloud services enable tagmanager.googleapis.com` |
| Site Verification API | `gsc_verify_site` | `gcloud services enable siteverification.googleapis.com` |
| PageSpeed Insights API | `pagespeed_*` (optional) | `gcloud services enable pagespeedonline.googleapis.com` |

## Authentication

**OAuth platforms** (Google Ads, Meta, GA4, Search Console, Tag Manager):

1. On first use, a local OAuth server starts on `localhost:8888+`
2. Browser opens automatically with the consent page
3. User completes authentication
4. Token is cached to `~/.unified-ads-mcp/`
5. Tokens auto-refresh on subsequent runs

Cached token files:
- `~/.unified-ads-mcp/google_ads_token.json`
- `~/.unified-ads-mcp/google_analytics_token.json`
- `~/.unified-ads-mcp/google_searchconsole_token.json`
- `~/.unified-ads-mcp/google_tagmanager_token.json`
- `~/.unified-ads-mcp/meta_token.json`

To force re-authentication (e.g. after adding OAuth scopes), delete the relevant token file.

**API key/token platforms** (Matomo, Bing, PageSpeed): No browser flow — credentials are read directly from YAML config.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GOOGLE_ADS_CREDENTIALS` | Path to Google Ads YAML config |
| `GOOGLE_ANALYTICS_CREDENTIALS` | Path to GA4 YAML config |
| `GOOGLE_TAGMANAGER_CREDENTIALS` | Path to Tag Manager YAML config |
| `META_ADS_CREDENTIALS` | Path to Meta Ads YAML config |
| `META_APP_ID` | Meta app ID (alternative to YAML) |
| `META_APP_SECRET` | Meta app secret (alternative to YAML) |
| `META_ACCESS_TOKEN` | Meta access token (bypasses OAuth) |
| `MATOMO_CREDENTIALS` | Path to Matomo YAML config |
| `BING_WEBMASTER_CREDENTIALS` | Path to Bing YAML config |
| `PAGESPEED_API_KEY` | Google PageSpeed API key |
| `ONLY_DEFAULT_ACCOUNT` | Set to `1` to force using default customer ID |

## License

MIT
