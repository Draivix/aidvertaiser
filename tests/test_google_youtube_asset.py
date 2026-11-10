"""Tests for google_create_youtube_video_asset input handling.

The happy path needs real API credentials; the ID parsing rejects bad input
before any API call.
"""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from unified_ads_mcp.google.assets import _YOUTUBE_ID
from unified_ads_mcp.google.assets import google_create_youtube_video_asset as _create

create_youtube_video_asset = _create.fn


@pytest.mark.parametrize(
    "value",
    [
        "I2OryjTt9vY",
        "https://www.youtube.com/watch?v=I2OryjTt9vY",
        "https://youtu.be/I2OryjTt9vY?si=abc",
        "https://www.youtube.com/shorts/I2OryjTt9vY",
    ],
)
def test_youtube_id_forms(value):
    assert _YOUTUBE_ID.search(value).group(1) == "I2OryjTt9vY"


@pytest.mark.parametrize("value", ["", "/tmp/video.mp4", "https://vimeo.com/123"])
def test_rejects_non_youtube(value):
    with pytest.raises(ToolError):
        create_youtube_video_asset(value)
