"""Google Tag Manager tag management tools."""

import json
from typing import Any, Optional


def _coerce_list(value: Any) -> list[str]:
    """Coerce a value to list[str]. Handles JSON strings from MCP transport."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
            except json.JSONDecodeError:
                pass
        return [v.strip() for v in value.split(",") if v.strip()]
    raise ValueError(f"Cannot coerce {type(value).__name__} to list[str]")

from mcp.server.fastmcp.exceptions import ToolError

from ..server import mcp
from .client import get_tagmanager_service, resolve_workspace_path, rewrite_path_to_active_workspace


def _tag_to_dict(tag: dict) -> dict[str, Any]:
    """Extract key fields from a GTM tag response."""
    return {
        "tagId": tag.get("tagId"),
        "name": tag.get("name"),
        "type": tag.get("type"),
        "firingTriggerId": tag.get("firingTriggerId", []),
        "blockingTriggerId": tag.get("blockingTriggerId", []),
        "liveOnly": tag.get("liveOnly", False),
        "paused": tag.get("paused", False),
        "fingerprint": tag.get("fingerprint"),
        "path": tag.get("path"),
        "parameter": tag.get("parameter", []),
    }


@mcp.tool()
def gtm_list_accounts() -> list[dict[str, Any]]:
    """Lists all Google Tag Manager accounts accessible by the authenticated user.

    Returns:
        list[dict]: List of GTM accounts with accountId, name, and path.
    """
    try:
        service = get_tagmanager_service()
        result = service.accounts().list().execute()
        accounts = result.get("account", [])
        return [
            {
                "accountId": a.get("accountId"),
                "name": a.get("name"),
                "path": a.get("path"),
            }
            for a in accounts
        ]
    except Exception as e:
        raise ToolError(f"Failed to list GTM accounts: {e}") from e


@mcp.tool()
def gtm_list_containers(
    account_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists all containers in a Google Tag Manager account.

    Args:
        account_id: GTM account ID. Uses default from config if not provided.

    Returns:
        list[dict]: List of containers with containerId, name, publicId,
            domainName, usageContext, and path.
    """
    try:
        from .client import get_default_account_id

        if not account_id:
            account_id = get_default_account_id()
        if not account_id:
            raise ToolError(
                "No account_id provided and no default configured. "
                "Use gtm_list_accounts first to find your account ID."
            )

        service = get_tagmanager_service()
        result = service.accounts().containers().list(
            parent=f"accounts/{account_id}"
        ).execute()
        containers = result.get("container", [])
        return [
            {
                "containerId": c.get("containerId"),
                "name": c.get("name"),
                "publicId": c.get("publicId"),
                "domainName": c.get("domainName", []),
                "usageContext": c.get("usageContext", []),
                "path": c.get("path"),
            }
            for c in containers
        ]
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to list containers: {e}") from e


@mcp.tool()
def gtm_list_workspaces(
    account_id: Optional[str] = None,
    container_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Lists all workspaces in a GTM container.

    Workspaces are where you make changes before publishing. The
    "Default Workspace" is always available.

    Args:
        account_id: GTM account ID. Uses default from config if not provided.
        container_id: GTM container ID. Uses default from config if not provided.

    Returns:
        list[dict]: List of workspaces with workspaceId, name, description, and path.
    """
    try:
        from .client import get_default_account_id, get_default_container_id

        if not account_id:
            account_id = get_default_account_id()
        if not account_id:
            raise ToolError("No account_id provided and no default configured.")

        if not container_id:
            container_id = get_default_container_id()
        if not container_id:
            raise ToolError("No container_id provided and no default configured.")

        service = get_tagmanager_service()
        parent = f"accounts/{account_id}/containers/{container_id}"
        result = service.accounts().containers().workspaces().list(
            parent=parent
        ).execute()
        workspaces = result.get("workspace", [])
        return [
            {
                "workspaceId": w.get("workspaceId"),
                "name": w.get("name"),
                "description": w.get("description", ""),
                "path": w.get("path"),
            }
            for w in workspaces
        ]
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to list workspaces: {e}") from e


@mcp.tool()
def gtm_list_tags(
    account_id: Optional[str] = None,
    container_id: Optional[str] = None,
    workspace_id: str = "Default Workspace",
) -> list[dict[str, Any]]:
    """Lists all tags in a GTM workspace.

    Args:
        account_id: GTM account ID. Uses default from config if not provided.
        container_id: GTM container ID. Uses default from config if not provided.
        workspace_id: Workspace ID. Defaults to "Default Workspace".

    Returns:
        list[dict]: List of tags with tagId, name, type, firingTriggerId,
            paused status, and parameters.
    """
    try:
        workspace_path = resolve_workspace_path(account_id, container_id, workspace_id)
        service = get_tagmanager_service()
        result = service.accounts().containers().workspaces().tags().list(
            parent=workspace_path
        ).execute()
        tags = result.get("tag", [])
        return [_tag_to_dict(t) for t in tags]
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to list tags: {e}") from e


@mcp.tool()
def gtm_create_tag(
    name: str,
    tag_type: str,
    parameter: list[dict[str, Any]],
    firing_trigger_id: Any,
    account_id: Optional[str] = None,
    container_id: Optional[str] = None,
    workspace_id: str = "Default Workspace",
    blocking_trigger_id: Optional[Any] = None,
    paused: bool = False,
) -> dict[str, Any]:
    """Creates a new tag in a GTM workspace.

    Common tag types:
        - "html": Custom HTML tag
        - "ua": Universal Analytics (deprecated, use GA4)
        - "gaawc": Google Analytics: GA4 Configuration
        - "gaawe": Google Analytics: GA4 Event
        - "awct": Google Ads Conversion Tracking
        - "gclidw": Google Ads Remarketing
        - "sp": Meta Pixel (Custom HTML with pixel code)

    Args:
        name: Tag display name (e.g. "GA4 - Purchase Event").
        tag_type: The tag type identifier (e.g. "gaawe" for GA4 Event).
        parameter: List of tag parameters. Each parameter is a dict with:
            - type: "template" for strings, "boolean" for bools, "list" for lists
            - key: Parameter key
            - value: Parameter value
            Example: [{"type": "template", "key": "measurementId", "value": "G-XXXXXXX"}]
        firing_trigger_id: List of trigger IDs that fire this tag.
        account_id: GTM account ID. Uses default if not provided.
        container_id: GTM container ID. Uses default if not provided.
        workspace_id: Workspace ID. Defaults to "Default Workspace".
        blocking_trigger_id: Optional list of trigger IDs that block this tag.
        paused: Whether the tag should be paused (default: False).

    Returns:
        dict: Created tag details.
    """
    firing_trigger_id = _coerce_list(firing_trigger_id)
    if blocking_trigger_id is not None:
        blocking_trigger_id = _coerce_list(blocking_trigger_id)
    try:
        workspace_path = resolve_workspace_path(account_id, container_id, workspace_id)
        service = get_tagmanager_service()

        body: dict[str, Any] = {
            "name": name,
            "type": tag_type,
            "parameter": parameter,
            "firingTriggerId": firing_trigger_id,
            "paused": paused,
        }
        if blocking_trigger_id:
            body["blockingTriggerId"] = blocking_trigger_id

        result = service.accounts().containers().workspaces().tags().create(
            parent=workspace_path, body=body
        ).execute()
        return _tag_to_dict(result)
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to create tag: {e}") from e


@mcp.tool()
def gtm_update_tag(
    tag_path: str,
    name: Optional[str] = None,
    parameter: Optional[list[dict[str, Any]]] = None,
    firing_trigger_id: Optional[Any] = None,
    blocking_trigger_id: Optional[Any] = None,
    paused: Optional[bool] = None,
) -> dict[str, Any]:
    """Updates an existing tag in a GTM workspace.

    If the workspace in tag_path is submitted (read-only), the tool
    automatically retries against the current active workspace.

    Args:
        tag_path: Full tag path
            (e.g. "accounts/123/containers/456/workspaces/789/tags/101").
        name: New tag name.
        parameter: New list of tag parameters (replaces all existing parameters).
        firing_trigger_id: New list of firing trigger IDs.
        blocking_trigger_id: New list of blocking trigger IDs.
        paused: Whether the tag should be paused.

    Returns:
        dict: Updated tag details.
    """
    if firing_trigger_id is not None:
        firing_trigger_id = _coerce_list(firing_trigger_id)
    if blocking_trigger_id is not None:
        blocking_trigger_id = _coerce_list(blocking_trigger_id)

    def _do_update(path: str) -> dict[str, Any]:
        service = get_tagmanager_service()
        current = service.accounts().containers().workspaces().tags().get(
            path=path
        ).execute()

        if name is not None:
            current["name"] = name
        if parameter is not None:
            current["parameter"] = parameter
        if firing_trigger_id is not None:
            current["firingTriggerId"] = firing_trigger_id
        if blocking_trigger_id is not None:
            current["blockingTriggerId"] = blocking_trigger_id
        if paused is not None:
            current["paused"] = paused

        result = service.accounts().containers().workspaces().tags().update(
            path=path, body=current
        ).execute()
        return _tag_to_dict(result)

    try:
        return _do_update(tag_path)
    except Exception as e:
        if "already submitted" in str(e).lower():
            new_path = rewrite_path_to_active_workspace(tag_path)
            try:
                return _do_update(new_path)
            except Exception as e2:
                raise ToolError(f"Failed to update tag (retried with active workspace {new_path}): {e2}") from e2
        raise ToolError(f"Failed to update tag: {e}") from e


@mcp.tool()
def gtm_delete_tag(
    tag_path: str,
) -> dict[str, Any]:
    """Deletes a tag from a GTM workspace.

    If the workspace in tag_path is submitted (read-only), the tool
    automatically retries against the current active workspace.

    Args:
        tag_path: Full tag path
            (e.g. "accounts/123/containers/456/workspaces/789/tags/101").

    Returns:
        dict: Deletion confirmation with the path that was actually used.
    """
    def _do_delete(path: str) -> dict[str, Any]:
        service = get_tagmanager_service()
        service.accounts().containers().workspaces().tags().delete(
            path=path
        ).execute()
        return {"status": "deleted", "path": path}

    try:
        return _do_delete(tag_path)
    except Exception as e:
        if "already submitted" in str(e).lower():
            new_path = rewrite_path_to_active_workspace(tag_path)
            try:
                return _do_delete(new_path)
            except Exception as e2:
                raise ToolError(f"Failed to delete tag (retried with active workspace {new_path}): {e2}") from e2
        raise ToolError(f"Failed to delete tag: {e}") from e
