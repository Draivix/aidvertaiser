"""Input validation of the Demand Gen audience-targeting tools.

Bad input is rejected before any API call; the happy paths are proven with
validate_only=True against a real account.
"""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from unified_ads_mcp.google.audiences import (
    google_create_custom_segment,
    google_search_targeting_segments,
    google_set_ad_group_audience,
)

set_audience = google_set_ad_group_audience.fn
create_segment = google_create_custom_segment.fn
search = google_search_targeting_segments.fn


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ad_group_id": "12 OR 1=1", "age_min": 25},
        {"ad_group_id": "1"},
        {"ad_group_id": "1", "audience_id": "5", "user_interest_ids": ["80536"]},
        {"ad_group_id": "1", "audience_id": "x"},
        {"ad_group_id": "1", "user_interest_ids": ["ERP"]},
        {"ad_group_id": "1", "age_min": 30},
        {"ad_group_id": "1", "age_min": 35, "age_max": 34},
        {"ad_group_id": "1", "age_min": 25, "age_max": 40},
    ],
)
def test_set_ad_group_audience_rejects_invalid_input(kwargs):
    with pytest.raises(ToolError):
        set_audience(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "x"},
        {"name": "x", "keywords": ["erp"], "segment_type": "LOOKALIKE"},
        {"name": "x", "urls": ["https://example.com"], "segment_type": "SEARCH"},
    ],
)
def test_create_custom_segment_rejects_invalid_input(kwargs):
    with pytest.raises(ToolError):
        create_segment(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [{"query": "  "}, {"query": "'\\"}, {"query": "erp", "kinds": ["topics"]}],
)
def test_search_targeting_segments_rejects_invalid_input(kwargs):
    with pytest.raises(ToolError):
        search(**kwargs)
