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


from unified_ads_mcp.google.ads import google_create_demand_gen_video_ad as _add_tool
from unified_ads_mcp.google.ads import google_update_ad as _update_tool

add_ad = _add_tool.fn
update_ad = _update_tool.fn


@pytest.mark.parametrize(
    "kwargs",
    [
        {"youtube_videos": ["I2OryjTt9vY"]},
        {"youtube_videos": ["I2OryjTt9vY"] * 6, "copy_from_ad_id": "1"},
        {"youtube_videos": ["/tmp/video.mp4"], "copy_from_ad_id": "1"},
        {"youtube_videos": ["I2OryjTt9vY"], "copy_from_ad_id": "1", "headlines": ["x" * 41]},
        {"youtube_videos": ["I2OryjTt9vY"], "copy_from_ad_id": "1", "business_name": "x" * 26},
    ],
)
def test_add_ad_rejects_invalid_input(kwargs):
    with pytest.raises(ToolError):
        add_ad(ad_group_id="1", **kwargs)


def test_update_ad_requires_a_change():
    with pytest.raises(ToolError):
        update_ad(ad_group_id="1", ad_id="1")
