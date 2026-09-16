"""Meta Ads Creative Management Tools.

This module provides MCP tools for managing Meta Ads creatives, including
uploading images and videos, creating creatives, and updating creative content.
"""

import asyncio
import base64
import os
import time
import httpx
from typing import Any, Dict, Optional

from ..server import mcp
from .client import (
    META_GRAPH_API_VERSION,
    USER_AGENT,
    make_api_request,
    meta_api_tool,
    ensure_account_prefix,
    resolve_account_id,
    get_meta_auth,
)


META_GRAPH_VIDEO_API_BASE = (
    f"https://graph-video.facebook.com/{META_GRAPH_API_VERSION}"
)
VIDEO_UPLOAD_TIMEOUT = 600.0
VIDEO_TRANSIENT_RETRY_LIMIT = 5


async def download_image_from_url(url: str) -> Optional[bytes]:
    """Download an image from a URL.

    Args:
        url: URL of the image to download.

    Returns:
        Image bytes or None if download failed.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            return response.content
    except Exception:
        return None


@mcp.tool()
@meta_api_tool
async def meta_upload_image(
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    image_url: Optional[str] = None,
    file: Optional[str] = None,
    file_path: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    """Upload an image to use in Meta Ads creatives.

    Uploads an image to the ad account's image library. The returned
    image hash can be used when creating creatives.

    Args:
        account_id: Meta Ads account ID (format: act_XXXXXXXXX).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).
        image_url: Direct URL to an image to fetch and upload.
        file: Base64-encoded image data or data URL
            (e.g., "data:image/png;base64,iVBORw0KG...").
        file_path: Local file path to an image (e.g., "/home/user/image.jpg").
        name: Optional name for the image (default: auto-generated).

    Returns:
        Dictionary containing:
            - success: True if upload successful
            - image_hash: Hash of the uploaded image (use this in creatives)
            - account_id: Account the image was uploaded to
            - name: Image name
            - images: Full image data including URL

    Note:
        Provide ONE of: image_url, file (base64), or file_path.

    Example:
        >>> result = await meta_upload_image(
        ...     account_id="act_123456789",
        ...     file_path="/home/user/images/product.jpg",
        ...     name="Product Image"
        ... )
        >>> image_hash = result["image_hash"]
        >>> # Now use image_hash in meta_create_creative()
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }

    if not file and not image_url and not file_path:
        return {
            "error": {
                "message": "Provide one of: 'file' (base64/data URL), 'image_url', or 'file_path'"
            }
        }

    account_id = ensure_account_prefix(account_id)

    try:
        encoded_image = ""
        inferred_name = name or ""

        if file_path:
            # Handle local file path
            if not os.path.isfile(file_path):
                return {
                    "error": {
                        "message": f"File not found: {file_path}",
                        "suggestions": [
                            "Check that the file path is correct",
                            "Ensure the file exists and is readable",
                        ],
                    }
                }

            try:
                with open(file_path, "rb") as f:
                    image_bytes = f.read()
                encoded_image = base64.b64encode(image_bytes).decode("utf-8")

                # Infer name from filename
                if not inferred_name:
                    inferred_name = os.path.basename(file_path)
            except Exception as e:
                return {
                    "error": {
                        "message": f"Failed to read file: {file_path}",
                        "details": str(e),
                    }
                }

        elif file:
            # Handle data URL or raw base64
            if file.startswith("data:") and "base64," in file:
                header, base64_payload = file.split("base64,", 1)
                encoded_image = base64_payload.strip()

                # Infer extension from MIME type
                if not inferred_name:
                    mime_type = header[5:].split(";")[0].strip()
                    ext_map = {
                        "image/png": ".png",
                        "image/jpeg": ".jpg",
                        "image/jpg": ".jpg",
                        "image/webp": ".webp",
                        "image/gif": ".gif",
                    }
                    ext = ext_map.get(mime_type, ".png")
                    inferred_name = f"upload{ext}"
            else:
                # Raw base64
                encoded_image = file.strip()
                if not inferred_name:
                    inferred_name = "upload.png"
        else:
            # Download from URL
            image_bytes = await download_image_from_url(image_url)

            if not image_bytes:
                return {
                    "error": {
                        "message": "Could not download image from URL",
                        "image_url": image_url,
                        "suggestions": [
                            "Ensure the URL is publicly accessible",
                            "Check that the URL points directly to an image file",
                        ],
                    }
                }

            encoded_image = base64.b64encode(image_bytes).decode("utf-8")

            # Infer name from URL
            if not inferred_name:
                try:
                    path_no_query = image_url.split("?")[0]
                    filename = os.path.basename(path_no_query)
                    inferred_name = filename if filename else "upload.jpg"
                except Exception:
                    inferred_name = "upload.jpg"

        final_name = name or inferred_name or "upload.png"

        endpoint = f"{account_id}/adimages"
        params = {"bytes": encoded_image, "name": final_name}

        data = await make_api_request(endpoint, access_token, params, method="POST")

        # Normalize response
        if (
            isinstance(data, dict)
            and "images" in data
            and isinstance(data["images"], dict)
        ):
            images_dict = data["images"]
            images_list = []
            for hash_key, info in images_dict.items():
                normalized = {
                    "hash": info.get("hash") or hash_key,
                    "url": info.get("url"),
                    "width": info.get("width"),
                    "height": info.get("height"),
                    "name": info.get("name"),
                }
                normalized = {k: v for k, v in normalized.items() if v is not None}
                images_list.append(normalized)

            images_list.sort(key=lambda i: i.get("hash", ""))
            primary_hash = images_list[0].get("hash") if images_list else None

            return {
                "success": True,
                "account_id": account_id,
                "name": final_name,
                "image_hash": primary_hash,
                "images": images_list,
            }

        if isinstance(data, dict) and "error" in data:
            return data

        return {
            "success": True,
            "account_id": account_id,
            "name": final_name,
            "raw_response": data,
        }

    except Exception as e:
        return {"error": {"message": "Failed to upload image", "details": str(e)}}


def _extract_error(response: httpx.Response) -> Dict[str, Any]:
    """Pull JSON error body from a non-2xx Meta response, fallback to text."""
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text}


async def _video_upload_start(
    client: httpx.AsyncClient,
    account_id: str,
    file_size: int,
    access_token: str,
) -> Dict[str, Any]:
    url = f"{META_GRAPH_VIDEO_API_BASE}/{account_id}/advideos"
    data = {
        "upload_phase": "start",
        "file_size": str(file_size),
        "access_token": access_token,
    }
    resp = await client.post(url, data=data, timeout=VIDEO_UPLOAD_TIMEOUT)
    if resp.status_code >= 400:
        return {"error": _extract_error(resp)}
    return resp.json()


async def _video_upload_transfer(
    client: httpx.AsyncClient,
    account_id: str,
    upload_session_id: str,
    file_path: str,
    start_offset: int,
    end_offset: int,
    access_token: str,
) -> Dict[str, Any]:
    url = f"{META_GRAPH_VIDEO_API_BASE}/{account_id}/advideos"
    file_name = os.path.basename(file_path)
    transient_retries = 0

    with open(file_path, "rb") as f:
        while start_offset < end_offset:
            f.seek(start_offset)
            chunk = f.read(end_offset - start_offset)
            data = {
                "upload_phase": "transfer",
                "upload_session_id": upload_session_id,
                "start_offset": str(start_offset),
                "access_token": access_token,
            }
            files = {
                "video_file_chunk": (file_name, chunk, "application/octet-stream"),
            }
            resp = await client.post(
                url, data=data, files=files, timeout=VIDEO_UPLOAD_TIMEOUT
            )
            if resp.status_code >= 400:
                body = _extract_error(resp)
                error = body.get("error") if isinstance(body, dict) else None
                # Recover from offset-mismatch (subcode 1363037)
                if (
                    isinstance(error, dict)
                    and error.get("error_subcode") == 1363037
                    and isinstance(error.get("error_data"), dict)
                    and "start_offset" in error["error_data"]
                    and transient_retries < VIDEO_TRANSIENT_RETRY_LIMIT
                ):
                    start_offset = int(error["error_data"]["start_offset"])
                    end_offset = int(error["error_data"]["end_offset"])
                    transient_retries += 1
                    continue
                # Generic transient retry
                if (
                    isinstance(error, dict)
                    and error.get("is_transient")
                    and transient_retries < VIDEO_TRANSIENT_RETRY_LIMIT
                ):
                    transient_retries += 1
                    await asyncio.sleep(1.0)
                    continue
                return {"error": body}

            payload = resp.json()
            start_offset = int(payload.get("start_offset", start_offset))
            end_offset = int(payload.get("end_offset", end_offset))

    return {"start_offset": start_offset, "end_offset": end_offset}


async def _video_upload_finish(
    client: httpx.AsyncClient,
    account_id: str,
    upload_session_id: str,
    title: str,
    description: Optional[str],
    access_token: str,
) -> Dict[str, Any]:
    url = f"{META_GRAPH_VIDEO_API_BASE}/{account_id}/advideos"
    data = {
        "upload_phase": "finish",
        "upload_session_id": upload_session_id,
        "title": title,
        "access_token": access_token,
    }
    if description:
        data["description"] = description
    resp = await client.post(url, data=data, timeout=VIDEO_UPLOAD_TIMEOUT)
    if resp.status_code >= 400:
        return {"error": _extract_error(resp)}
    return resp.json()


async def _wait_for_video_ready(
    video_id: str,
    access_token: str,
    timeout: int,
    interval: float = 3.0,
) -> Dict[str, Any]:
    deadline = time.time() + timeout
    last_status: Dict[str, Any] = {}
    while True:
        result = await make_api_request(
            f"{video_id}", access_token, {"fields": "status"}
        )
        if "error" in result:
            return result
        status = result.get("status") or {}
        last_status = status
        video_status = status.get("video_status")
        if video_status == "ready":
            return {"video_status": "ready", "status": status}
        if video_status == "error":
            return {
                "error": {
                    "message": "Video encoding failed",
                    "status": status,
                }
            }
        if time.time() >= deadline:
            return {
                "error": {
                    "message": f"Video encoding timeout after {timeout}s",
                    "status": last_status,
                }
            }
        await asyncio.sleep(interval)


@mcp.tool()
@meta_api_tool
async def meta_upload_video(
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    file_path: Optional[str] = None,
    file_url: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    wait_for_encoding: bool = True,
    encoding_timeout: int = 600,
) -> dict:
    """Upload a video to a Meta Ads account for use in video creatives.

    Supports two paths:
      - file_url: Meta fetches the video from a public URL (single request).
      - file_path: chunked resumable upload from a local file using the
        start/transfer/finish phases on graph-video.facebook.com.

    The returned video_id is the input for meta_create_video_creative().

    Args:
        account_id: Meta Ads account ID (act_XXXXXXXXX). Uses default if unset.
        access_token: Meta API access token (uses cached token if not provided).
        file_path: Local video file path. Triggers chunked upload.
        file_url: Public URL to a video. Triggers single-request URL upload.
        title: Video title (defaults to filename for file_path uploads).
        description: Optional video description.
        wait_for_encoding: If True, poll until video_status='ready' before
            returning. Required before the video can be used in a creative.
        encoding_timeout: Max seconds to wait for encoding when polling.

    Returns:
        Dict with success, video_id, account_id, title, status (when polled).

    Note:
        Provide exactly one of file_path or file_url.

    Example:
        >>> result = await meta_upload_video(
        ...     file_path="/home/user/videos/promo.mp4",
        ...     title="Spring Promo",
        ... )
        >>> video_id = result["video_id"]
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }

    if bool(file_path) == bool(file_url):
        return {
            "error": {
                "message": "Provide exactly one of: 'file_path' (local file) or 'file_url' (public URL)"
            }
        }

    account_id = ensure_account_prefix(account_id)

    if not access_token:
        access_token = get_meta_auth().get_access_token()

    # --- file_url path: single request, Meta fetches the video ---
    if file_url:
        params: Dict[str, Any] = {"file_url": file_url}
        if title:
            params["title"] = title
        if description:
            params["description"] = description

        data = await make_api_request(
            f"{account_id}/advideos", access_token, params, method="POST"
        )
        if "error" in data:
            return data

        video_id = data.get("id") or data.get("video_id")
        if not video_id:
            return {
                "error": {
                    "message": "Upload accepted but no video_id returned",
                    "raw_response": data,
                }
            }

        result = {
            "success": True,
            "account_id": account_id,
            "video_id": video_id,
            "title": title,
        }
        if wait_for_encoding:
            status = await _wait_for_video_ready(
                video_id, access_token, encoding_timeout
            )
            if "error" in status:
                result["encoding"] = status
                result["success"] = False
            else:
                result["status"] = status.get("status")
        return result

    # --- file_path path: chunked resumable upload ---
    if not os.path.isfile(file_path):
        return {
            "error": {
                "message": f"File not found: {file_path}",
                "suggestions": [
                    "Check that the file path is correct",
                    "Ensure the file exists and is readable",
                ],
            }
        }

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return {"error": {"message": f"File is empty: {file_path}"}}

    final_title = title or os.path.basename(file_path)

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        try:
            start = await _video_upload_start(
                client, account_id, file_size, access_token
            )
            if "error" in start:
                return {
                    "error": {
                        "message": "Video upload start phase failed",
                        "details": start["error"],
                    }
                }

            upload_session_id = start.get("upload_session_id")
            video_id = start.get("video_id")
            start_offset = int(start.get("start_offset", 0))
            end_offset = int(start.get("end_offset", 0))
            if not upload_session_id or not video_id:
                return {
                    "error": {
                        "message": "Start phase returned no session/video id",
                        "raw_response": start,
                    }
                }

            transfer = await _video_upload_transfer(
                client,
                account_id,
                upload_session_id,
                file_path,
                start_offset,
                end_offset,
                access_token,
            )
            if "error" in transfer:
                return {
                    "error": {
                        "message": "Video upload transfer phase failed",
                        "details": transfer["error"],
                    }
                }

            finish = await _video_upload_finish(
                client,
                account_id,
                upload_session_id,
                final_title,
                description,
                access_token,
            )
            if "error" in finish:
                return {
                    "error": {
                        "message": "Video upload finish phase failed",
                        "details": finish["error"],
                    }
                }

            result = {
                "success": bool(finish.get("success", True)),
                "account_id": account_id,
                "video_id": video_id,
                "title": final_title,
                "file_size": file_size,
            }

            if wait_for_encoding:
                status = await _wait_for_video_ready(
                    video_id, access_token, encoding_timeout
                )
                if "error" in status:
                    result["encoding"] = status
                    result["success"] = False
                else:
                    result["status"] = status.get("status")

            return result

        except httpx.HTTPError as e:
            return {
                "error": {"message": "HTTP error during video upload", "details": str(e)}
            }
        except Exception as e:
            return {
                "error": {"message": "Failed to upload video", "details": str(e)}
            }


@mcp.tool()
@meta_api_tool
async def meta_create_video_creative(
    video_id: str,
    page_id: str,
    name: str,
    message: str,
    link_url: str,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    image_hash: Optional[str] = None,
    image_url: Optional[str] = None,
    title: Optional[str] = None,
    link_description: Optional[str] = None,
    call_to_action_type: Optional[str] = None,
    instagram_actor_id: Optional[str] = None,
) -> dict:
    """Create an ad creative from an uploaded video.

    Builds a video_data object_story_spec referencing a previously uploaded
    video_id and a thumbnail (image_hash from meta_upload_image OR image_url).
    The video must be encoded (status='ready') before a creative can use it.

    Args:
        video_id: ID returned by meta_upload_video (required).
        page_id: Facebook Page ID for the ad (required).
        name: Internal creative name (required).
        message: Primary ad copy / body text (required).
        link_url: Destination URL when users click the CTA (required).
        account_id: Meta Ads account ID (act_XXXXXXXXX). Uses default if unset.
        access_token: Meta API access token (uses cached token if not provided).
        image_hash: Thumbnail image_hash (preferred — from meta_upload_image).
        image_url: Thumbnail URL (alternative to image_hash).
        title: Headline shown above the video.
        link_description: Description text below the headline.
        call_to_action_type: CTA button type (LEARN_MORE, SHOP_NOW, SIGN_UP,
            SUBSCRIBE, DOWNLOAD, GET_OFFER, CONTACT_US, BOOK_NOW, WATCH_MORE).
        instagram_actor_id: Instagram account ID for Instagram placements.

    Returns:
        Dict with success, creative_id, details.

    Example:
        >>> video = await meta_upload_video(file_path="/tmp/promo.mp4")
        >>> thumb = await meta_upload_image(image_url="https://x/cover.jpg")
        >>> creative = await meta_create_video_creative(
        ...     video_id=video["video_id"],
        ...     page_id="123456789",
        ...     name="Spring Video",
        ...     message="Check out our spring promo!",
        ...     link_url="https://example.com/spring",
        ...     image_hash=thumb["image_hash"],
        ...     title="Spring Sale",
        ...     call_to_action_type="SHOP_NOW",
        ... )
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }
    if not video_id:
        return {"error": {"message": "video_id is required"}}
    if not page_id:
        return {"error": {"message": "page_id is required"}}
    if not name:
        return {"error": {"message": "name is required"}}
    if not message:
        return {"error": {"message": "message is required"}}
    if not link_url:
        return {"error": {"message": "link_url is required"}}
    if not image_hash and not image_url:
        return {
            "error": {
                "message": "Provide a thumbnail via image_hash (preferred) or image_url"
            }
        }

    account_id = ensure_account_prefix(account_id)

    video_data: Dict[str, Any] = {
        "video_id": str(video_id),
        "message": message,
        "call_to_action": {
            "type": call_to_action_type or "LEARN_MORE",
            "value": {"link": link_url},
        },
    }
    if image_hash:
        video_data["image_hash"] = image_hash
    elif image_url:
        video_data["image_url"] = image_url
    if title:
        video_data["title"] = title
    if link_description:
        video_data["link_description"] = link_description

    creative_data: Dict[str, Any] = {
        "name": name,
        "object_story_spec": {
            "page_id": page_id,
            "video_data": video_data,
        },
    }
    if instagram_actor_id:
        creative_data["instagram_actor_id"] = instagram_actor_id

    endpoint = f"{account_id}/adcreatives"

    try:
        data = await make_api_request(
            endpoint, access_token, creative_data, method="POST"
        )
        if "id" in data:
            creative_id = data["id"]
            details = await make_api_request(
                f"{creative_id}",
                access_token,
                {
                    "fields": (
                        "id,name,status,thumbnail_url,object_story_spec,link_url,"
                        "video_id"
                    )
                },
            )
            return {"success": True, "creative_id": creative_id, "details": details}
        return data
    except Exception as e:
        return {
            "error": {
                "message": "Failed to create video creative",
                "details": str(e),
            }
        }


@mcp.tool()
@meta_api_tool
async def meta_create_creative(
    image_hash: str,
    page_id: str,
    name: str,
    message: str,
    link_url: str,
    account_id: Optional[str] = None,
    access_token: Optional[str] = None,
    headline: Optional[str] = None,
    description: Optional[str] = None,
    call_to_action_type: Optional[str] = None,
    instagram_actor_id: Optional[str] = None,
) -> dict:
    """Create a new ad creative using an uploaded image.

    Creates a creative that can be used in ads. The creative combines
    an image with copy, headline, and call-to-action.

    Args:
        image_hash: Hash of the uploaded image (from meta_upload_image).
        page_id: Facebook Page ID for the ad (required).
        name: Creative name (required).
        message: Primary ad copy/text (required).
        link_url: Destination URL when users click the ad (required).
        account_id: Meta Ads account ID (format: act_XXXXXXXXX).
            Uses default from config if not provided.
        access_token: Meta API access token (uses cached token if not provided).
        headline: Ad headline (appears below the image).
        description: Ad description (appears below headline).
        call_to_action_type: CTA button type. Options:
            - LEARN_MORE
            - SHOP_NOW
            - SIGN_UP
            - SUBSCRIBE
            - DOWNLOAD
            - GET_OFFER
            - CONTACT_US
            - BOOK_NOW
            - WATCH_MORE
        instagram_actor_id: Instagram account ID for Instagram placements.

    Returns:
        Dictionary containing:
            - success: True if created successfully
            - creative_id: ID of the created creative
            - details: Full creative details

    Example:
        >>> # First upload an image
        >>> image = await meta_upload_image(
        ...     account_id="act_123456789",
        ...     image_url="https://example.com/hero.jpg"
        ... )
        >>>
        >>> # Then create the creative
        >>> creative = await meta_create_creative(
        ...     account_id="act_123456789",
        ...     image_hash=image["image_hash"],
        ...     page_id="123456789012345",
        ...     name="Summer Sale Creative",
        ...     message="Don't miss our biggest sale of the year!",
        ...     link_url="https://example.com/summer-sale",
        ...     headline="50% Off Everything",
        ...     call_to_action_type="SHOP_NOW"
        ... )
        >>> creative_id = creative["creative_id"]
    """
    account_id = resolve_account_id(account_id)
    if not account_id:
        return {
            "error": {
                "message": "account_id is required - configure default_account_id in meta-ads.yaml or META_DEFAULT_ACCOUNT_ID"
            }
        }
    if not image_hash:
        return {"error": {"message": "image_hash is required"}}
    if not page_id:
        return {"error": {"message": "page_id is required"}}
    if not name:
        return {"error": {"message": "name is required"}}
    if not message:
        return {"error": {"message": "message is required"}}
    if not link_url:
        return {"error": {"message": "link_url is required"}}

    account_id = ensure_account_prefix(account_id)

    # Build the creative data
    creative_data = {
        "name": name,
        "object_story_spec": {
            "page_id": page_id,
            "link_data": {
                "image_hash": image_hash,
                "link": link_url,
                "message": message,
            },
        },
    }

    if headline:
        creative_data["object_story_spec"]["link_data"]["name"] = headline

    if description:
        creative_data["object_story_spec"]["link_data"]["description"] = description

    if call_to_action_type:
        creative_data["object_story_spec"]["link_data"]["call_to_action"] = {
            "type": call_to_action_type
        }

    if instagram_actor_id:
        creative_data["instagram_actor_id"] = instagram_actor_id

    endpoint = f"{account_id}/adcreatives"

    try:
        data = await make_api_request(
            endpoint, access_token, creative_data, method="POST"
        )

        if "id" in data:
            creative_id = data["id"]
            # Get full creative details
            detail_endpoint = f"{creative_id}"
            detail_params = {
                "fields": "id,name,status,thumbnail_url,image_url,image_hash,object_story_spec,link_url"
            }
            details = await make_api_request(
                detail_endpoint, access_token, detail_params
            )

            return {"success": True, "creative_id": creative_id, "details": details}

        return data

    except Exception as e:
        return {"error": {"message": "Failed to create creative", "details": str(e)}}


@mcp.tool()
@meta_api_tool
async def meta_update_creative(
    creative_id: str,
    access_token: Optional[str] = None,
    name: Optional[str] = None,
    message: Optional[str] = None,
    headline: Optional[str] = None,
    description: Optional[str] = None,
    call_to_action_type: Optional[str] = None,
) -> dict:
    """Update an existing creative's content.

    Updates specified fields of a creative. Only provided parameters
    will be updated; others remain unchanged.

    Note: Some fields like image_hash cannot be updated. To change
    the image, create a new creative.

    Args:
        creative_id: Meta Ads creative ID (required).
        access_token: Meta API access token (uses cached token if not provided).
        name: New creative name.
        message: New ad copy/text.
        headline: New headline.
        description: New description.
        call_to_action_type: New CTA button type.

    Returns:
        Dictionary containing:
            - success: True if update was successful
            - creative_id: ID of the updated creative
            - details: Updated creative details

    Example:
        >>> result = await meta_update_creative(
        ...     creative_id="23842614006150185",
        ...     headline="70% Off - Extended!",
        ...     message="Sale extended through Sunday!"
        ... )
    """
    if not creative_id:
        return {"error": {"message": "creative_id is required"}}

    update_data = {}

    if name is not None:
        update_data["name"] = name

    # For updating link_data fields, we need to use object_story_spec
    link_data_updates = {}
    if message is not None:
        link_data_updates["message"] = message
    if headline is not None:
        link_data_updates["name"] = headline  # API uses "name" for headline
    if description is not None:
        link_data_updates["description"] = description
    if call_to_action_type is not None:
        link_data_updates["call_to_action"] = {"type": call_to_action_type}

    if link_data_updates:
        update_data["object_story_spec"] = {"link_data": link_data_updates}

    if not update_data:
        return {"error": {"message": "No update parameters provided"}}

    endpoint = f"{creative_id}"

    try:
        data = await make_api_request(
            endpoint, access_token, update_data, method="POST"
        )

        if "success" in data or "id" in data:
            # Get updated details
            detail_params = {
                "fields": "id,name,status,thumbnail_url,image_url,image_hash,object_story_spec,link_url"
            }
            details = await make_api_request(endpoint, access_token, detail_params)

            return {"success": True, "creative_id": creative_id, "details": details}

        return data

    except Exception as e:
        return {
            "error": {
                "message": f"Failed to update creative {creative_id}",
                "details": str(e),
            }
        }
