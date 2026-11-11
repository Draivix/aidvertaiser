"""Input validation of google_create_demand_gen_video_campaign.

Bad input is rejected before any API call; the happy path is proven with
validate_only=True against a real account.
"""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from unified_ads_mcp.google.ads import google_create_demand_gen_video_campaign as _tool

create = _tool.fn

VALID = dict(
    name="Test",
    budget=200,
    final_url="https://example.com",
    youtube_videos=["https://www.youtube.com/shorts/I2OryjTt9vY"],
    headlines=["Headline"],
    long_headlines=["Long headline"],
    descriptions=["Description"],
    business_name="Example",
    logo_asset_id="1",
    location_ids=["2203"],
)


@pytest.mark.parametrize(
    "override",
    [
        {"youtube_videos": ["/tmp/video.mp4"]},
        {"youtube_videos": []},
        {"headlines": ["x" * 41]},
        {"long_headlines": []},
        {"descriptions": ["d"] * 6},
        {"business_name": "x" * 26},
        {"location_ids": []},
        {"channels": ["tiktok"]},
        {"bidding": "TARGET_ROAS"},
    ],
)
def test_rejects_invalid_input(override):
    with pytest.raises(ToolError):
        create(**{**VALID, **override})
