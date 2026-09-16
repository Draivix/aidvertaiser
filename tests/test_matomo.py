"""Integration tests for Matomo Analytics tools.

Run with: pytest tests/test_matomo.py -v -s
"""

import os
import pytest
import yaml


MATOMO_CONFIG_PATH = os.environ.get(
    "MATOMO_CREDENTIALS", os.path.expanduser("~/matomo.yaml")
)


@pytest.fixture(scope="session")
def matomo_config():
    if not os.path.exists(MATOMO_CONFIG_PATH):
        pytest.skip("No Matomo config found at ~/matomo.yaml")
    with open(MATOMO_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# Import tool functions
from unified_ads_mcp.matomo.sites import (
    matomo_list_sites as _list_sites,
    matomo_get_site as _get_site,
    matomo_get_site_urls as _get_site_urls,
)
from unified_ads_mcp.matomo.reporting import (
    matomo_get_visits_summary as _visits_summary,
    matomo_get_page_urls as _page_urls,
    matomo_get_referrers as _referrers,
    matomo_get_referrer_types as _referrer_types,
    matomo_get_devices as _devices,
    matomo_get_countries as _countries,
    matomo_get_entry_pages as _entry_pages,
    matomo_get_exit_pages as _exit_pages,
    matomo_get_search_keywords as _search_keywords,
)
from unified_ads_mcp.matomo.goals import (
    matomo_list_goals as _list_goals,
    matomo_get_goal_report as _goal_report,
)
from unified_ads_mcp.matomo.live import (
    matomo_get_live_counters as _live_counters,
    matomo_get_last_visits as _last_visits,
)

list_sites = _list_sites.fn
get_site = _get_site.fn
get_site_urls = _get_site_urls.fn
visits_summary = _visits_summary.fn
page_urls = _page_urls.fn
referrers = _referrers.fn
referrer_types = _referrer_types.fn
devices = _devices.fn
countries = _countries.fn
entry_pages = _entry_pages.fn
exit_pages = _exit_pages.fn
search_keywords = _search_keywords.fn
list_goals = _list_goals.fn
goal_report = _goal_report.fn
live_counters = _live_counters.fn
last_visits = _last_visits.fn


# Use first site found for testing
@pytest.fixture(scope="session")
def site_id(matomo_config):
    sites = list_sites()
    assert len(sites) > 0, "No Matomo sites found"
    return sites[0]["idsite"]


class TestSites:
    def test_list_sites(self, matomo_config):
        result = list_sites()
        assert isinstance(result, list)
        assert len(result) > 0
        site = result[0]
        assert "idsite" in site
        assert "name" in site
        assert "main_url" in site
        print(f"\n{len(result)} sites found")
        for s in result[:5]:
            print(f"  {s['idsite']}: {s['name']} ({s['main_url']})")

    def test_get_site(self, site_id):
        result = get_site(site_id=site_id)
        assert isinstance(result, dict)
        assert result["idsite"] == str(site_id) or int(result["idsite"]) == site_id
        print(f"\nSite: {result['name']} ({result['main_url']})")

    def test_get_site_urls(self, site_id):
        result = get_site_urls(site_id=site_id)
        assert isinstance(result, list)
        print(f"\nURLs: {result}")


class TestReporting:
    def test_visits_summary(self, site_id):
        result = visits_summary(site_id=site_id, period="day", date="last7")
        assert isinstance(result, dict)
        print(f"\nVisit summary (last 7 days):")
        for date, data in result.items():
            if isinstance(data, dict):
                print(f"  {date}: {data['nb_visits']} visits")
            else:
                print(f"  {date}: {data}")

    def test_page_urls(self, site_id):
        result = page_urls(site_id=site_id, period="range", date="last7", limit=5)
        assert isinstance(result, list)
        print(f"\nTop {len(result)} pages:")
        for p in result[:5]:
            print(f"  {p.get('label', 'N/A')}: {p.get('nb_visits', 0)} visits")

    def test_referrers(self, site_id):
        result = referrers(site_id=site_id, period="range", date="last7", limit=5)
        assert isinstance(result, list)
        print(f"\nTop referrers:")
        for r in result[:5]:
            print(f"  {r.get('label', 'N/A')}: {r.get('nb_visits', 0)} visits")

    def test_referrer_types(self, site_id):
        result = referrer_types(site_id=site_id, period="range", date="last7")
        assert isinstance(result, list)
        print(f"\nReferrer types:")
        for r in result:
            print(f"  {r.get('label', 'N/A')}: {r.get('nb_visits', 0)} visits")

    def test_devices(self, site_id):
        result = devices(site_id=site_id, period="range", date="last7")
        assert isinstance(result, list)
        print(f"\nDevices:")
        for d in result:
            print(f"  {d.get('label', 'N/A')}: {d.get('nb_visits', 0)} visits")

    def test_countries(self, site_id):
        result = countries(site_id=site_id, period="range", date="last7", limit=5)
        assert isinstance(result, list)
        print(f"\nTop countries:")
        for c in result[:5]:
            print(f"  {c.get('label', 'N/A')}: {c.get('nb_visits', 0)} visits")

    def test_entry_pages(self, site_id):
        result = entry_pages(site_id=site_id, period="range", date="last7", limit=5)
        assert isinstance(result, list)
        print(f"\nTop entry pages:")
        for p in result[:5]:
            print(f"  {p.get('label', 'N/A')}: {p.get('entry_nb_visits', 0)} entries")

    def test_exit_pages(self, site_id):
        result = exit_pages(site_id=site_id, period="range", date="last7", limit=5)
        assert isinstance(result, list)
        print(f"\nTop exit pages:")
        for p in result[:5]:
            print(f"  {p.get('label', 'N/A')}: {p.get('exit_nb_visits', 0)} exits")

    def test_search_keywords(self, site_id):
        result = search_keywords(site_id=site_id, period="range", date="last30")
        assert isinstance(result, list)
        print(f"\nSearch keywords: {len(result)} found")
        for k in result[:5]:
            print(f"  {k.get('label', 'N/A')}: {k.get('nb_visits', 0)} visits")


class TestGoals:
    def test_list_goals(self, site_id):
        result = list_goals(site_id=site_id)
        assert isinstance(result, list)
        print(f"\n{len(result)} goals:")
        for g in result:
            print(f"  {g['idgoal']}: {g['name']} ({g.get('match_attribute', 'N/A')})")

    def test_goal_report(self, site_id):
        result = goal_report(site_id=site_id, period="day", date="last7")
        assert isinstance(result, dict)
        print(f"\nGoal report:")
        for date, data in result.items():
            convs = data.get("nb_conversions", 0) if isinstance(data, dict) else 0
            print(f"  {date}: {convs} conversions")


class TestLive:
    def test_live_counters(self, site_id):
        result = live_counters(site_id=site_id)
        assert isinstance(result, dict)
        assert "visitors" in result
        print(f"\nLive: {result['visitors']} visitors, {result['visits']} visits")

    def test_last_visits(self, site_id):
        result = last_visits(site_id=site_id, count=3)
        assert isinstance(result, list)
        print(f"\nLast {len(result)} visits:")
        for v in result[:3]:
            country = v.get("country", "?")
            browser = v.get("browser", "?")
            actions = v.get("actions", 0)
            print(f"  {country} / {browser}: {actions} actions")
