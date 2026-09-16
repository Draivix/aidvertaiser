"""Google Tag Manager trigger management tools."""

from typing import Any, Optional

from mcp.server.fastmcp.exceptions import ToolError

from ..server import mcp
from .client import get_tagmanager_service, resolve_workspace_path, rewrite_path_to_active_workspace


def _trigger_to_dict(trigger: dict) -> dict[str, Any]:
    """Extract fields from a GTM trigger response, preserving type-specific params."""
    # Always include these core fields plus any type-specific fields
    result: dict[str, Any] = {}
    # Core fields
    for key in ("triggerId", "name", "type", "fingerprint", "path", "parentFolderId",
                "parameter", "filter", "customEventFilter",
                # Timer-specific
                "eventName", "interval", "limit",
                # Scroll-specific
                "horizontalScrollPercentageList", "verticalScrollPercentageList",
                # Visibility-specific
                "visibilitySelector", "visiblePercentage", "totalTimeMinMilliseconds",
                # Form-specific
                "waitForTags", "checkValidation", "waitForTagsTimeout",
                # Auto-event specific
                "uniqueTriggerId", "autoEventFilter",
                # Misc
                "continuousTimeMinMilliseconds", "maxTimerLengthSeconds",
                "notes", "selector"):
        if key in trigger:
            result[key] = trigger[key]
    return result


@mcp.tool()
def gtm_list_triggers(
    account_id: Optional[str] = None,
    container_id: Optional[str] = None,
    workspace_id: str = "Default Workspace",
) -> list[dict[str, Any]]:
    """Lists all triggers in a GTM workspace.

    Args:
        account_id: GTM account ID. Uses default from config if not provided.
        container_id: GTM container ID. Uses default from config if not provided.
        workspace_id: Workspace ID. Defaults to "Default Workspace".

    Returns:
        list[dict]: List of triggers with triggerId, name, type, filters, and parameters.
    """
    try:
        workspace_path = resolve_workspace_path(account_id, container_id, workspace_id)
        service = get_tagmanager_service()
        result = service.accounts().containers().workspaces().triggers().list(
            parent=workspace_path
        ).execute()
        triggers = result.get("trigger", [])
        return [_trigger_to_dict(t) for t in triggers]
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to list triggers: {e}") from e


@mcp.tool()
def gtm_create_trigger(
    name: str,
    trigger_type: str,
    account_id: Optional[str] = None,
    container_id: Optional[str] = None,
    workspace_id: str = "Default Workspace",
    custom_event_filter: Optional[list[dict[str, Any]]] = None,
    filter: Optional[list[dict[str, Any]]] = None,
    parameter: Optional[list[dict[str, Any]]] = None,
    # Timer-specific fields
    event_name: Optional[dict[str, Any]] = None,
    interval: Optional[dict[str, Any]] = None,
    limit: Optional[dict[str, Any]] = None,
    # General timer/visibility fields
    max_timer_length_seconds: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Creates a new trigger in a GTM workspace.

    Common trigger types:
        - "pageview": Page View (fires on page load)
        - "domReady": DOM Ready
        - "windowLoaded": Window Loaded
        - "customEvent": Custom Event (dataLayer.push)
        - "click": Click - All Elements
        - "linkClick": Click - Just Links
        - "formSubmission": Form Submission
        - "timer": Timer
        - "scrollDepth": Scroll Depth
        - "youTubeVideo": YouTube Video
        - "elementVisibility": Element Visibility

    Filters use conditions to restrict when the trigger fires. Each filter
    is a dict with:
        - type: "equals", "contains", "startsWith", "endsWith", "matchRegex", etc.
        - parameter: list of [{"type": "template", "key": "arg0", "value": "{{Page URL}}"},
                               {"type": "template", "key": "arg1", "value": "https://example.com/blog"}]

    Args:
        name: Trigger display name (e.g. "Blog Page Views").
        trigger_type: The trigger type (e.g. "pageview", "customEvent").
        account_id: GTM account ID. Uses default if not provided.
        container_id: GTM container ID. Uses default if not provided.
        workspace_id: Workspace ID. Defaults to "Default Workspace".
        custom_event_filter: Filters for custom event triggers.
        filter: General filters/conditions for the trigger.
        parameter: Additional trigger parameters.
        event_name: Timer trigger event name param (dict with type/key/value).
        interval: Timer trigger interval param (dict with type/key/value).
        limit: Timer trigger limit param (dict with type/key/value).
        max_timer_length_seconds: Max timer length param.

    Returns:
        dict: Created trigger details.
    """
    try:
        workspace_path = resolve_workspace_path(account_id, container_id, workspace_id)
        service = get_tagmanager_service()

        body: dict[str, Any] = {
            "name": name,
            "type": trigger_type,
        }
        if custom_event_filter:
            body["customEventFilter"] = custom_event_filter
        if filter:
            body["filter"] = filter
        if parameter:
            body["parameter"] = parameter

        # Timer-specific top-level fields
        if event_name is not None:
            body["eventName"] = event_name
        if interval is not None:
            body["interval"] = interval
        if limit is not None:
            body["limit"] = limit
        if max_timer_length_seconds is not None:
            body["maxTimerLengthSeconds"] = max_timer_length_seconds

        result = service.accounts().containers().workspaces().triggers().create(
            parent=workspace_path, body=body
        ).execute()
        return _trigger_to_dict(result)
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to create trigger: {e}") from e


@mcp.tool()
def gtm_update_trigger(
    trigger_path: str,
    name: Optional[str] = None,
    custom_event_filter: Optional[list[dict[str, Any]]] = None,
    filter: Optional[list[dict[str, Any]]] = None,
    parameter: Optional[list[dict[str, Any]]] = None,
    # Timer-specific fields
    event_name: Optional[dict[str, Any]] = None,
    interval: Optional[dict[str, Any]] = None,
    limit: Optional[dict[str, Any]] = None,
    # General timer/visibility fields
    max_timer_length_seconds: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Updates an existing trigger in a GTM workspace.

    If the workspace in trigger_path is submitted (read-only), the tool
    automatically retries against the current active workspace.

    Args:
        trigger_path: Full trigger path
            (e.g. "accounts/123/containers/456/workspaces/789/triggers/101").
        name: New trigger name.
        custom_event_filter: New custom event filters (replaces existing).
        filter: New filters/conditions (replaces existing).
        parameter: Parameters to merge with existing (matched by 'key' field).
            Each param is a dict like {"type": "template", "key": "...", "value": "..."}.
        event_name: Timer trigger event name param (dict with type/key/value).
        interval: Timer trigger interval param (dict with type/key/value).
        limit: Timer trigger limit param (dict with type/key/value).
        max_timer_length_seconds: Max timer length param.

    Returns:
        dict: Updated trigger details.
    """
    def _do_update(path: str) -> dict[str, Any]:
        service = get_tagmanager_service()
        current = service.accounts().containers().workspaces().triggers().get(
            path=path
        ).execute()

        if name is not None:
            current["name"] = name
        if custom_event_filter is not None:
            current["customEventFilter"] = custom_event_filter
        if filter is not None:
            current["filter"] = filter

        # Merge parameters instead of replacing
        if parameter is not None:
            existing_params = current.get("parameter", [])
            existing_by_key = {p.get("key"): p for p in existing_params}
            for new_param in parameter:
                key = new_param.get("key")
                if key:
                    existing_by_key[key] = new_param
                else:
                    existing_params.append(new_param)
            current["parameter"] = list(existing_by_key.values())

        # Timer-specific top-level fields
        if event_name is not None:
            current["eventName"] = event_name
        if interval is not None:
            current["interval"] = interval
        if limit is not None:
            current["limit"] = limit
        if max_timer_length_seconds is not None:
            current["maxTimerLengthSeconds"] = max_timer_length_seconds

        result = service.accounts().containers().workspaces().triggers().update(
            path=path, body=current
        ).execute()
        return _trigger_to_dict(result)

    try:
        return _do_update(trigger_path)
    except Exception as e:
        if "already submitted" in str(e).lower():
            new_path = rewrite_path_to_active_workspace(trigger_path)
            try:
                return _do_update(new_path)
            except Exception as e2:
                raise ToolError(f"Failed to update trigger (retried with active workspace {new_path}): {e2}") from e2
        raise ToolError(f"Failed to update trigger: {e}") from e


@mcp.tool()
def gtm_delete_trigger(
    trigger_path: str,
) -> dict[str, Any]:
    """Deletes a trigger from a GTM workspace.

    Note: You cannot delete a trigger that is referenced by any tag.
    Remove the trigger from all tags first.

    If the workspace in trigger_path is submitted (read-only), the tool
    automatically retries against the current active workspace.

    Args:
        trigger_path: Full trigger path
            (e.g. "accounts/123/containers/456/workspaces/789/triggers/101").

    Returns:
        dict: Deletion confirmation with the path that was actually used.
    """
    def _do_delete(path: str) -> dict[str, Any]:
        service = get_tagmanager_service()
        service.accounts().containers().workspaces().triggers().delete(
            path=path
        ).execute()
        return {"status": "deleted", "path": path}

    try:
        return _do_delete(trigger_path)
    except Exception as e:
        if "already submitted" in str(e).lower():
            new_path = rewrite_path_to_active_workspace(trigger_path)
            try:
                return _do_delete(new_path)
            except Exception as e2:
                raise ToolError(f"Failed to delete trigger (retried with active workspace {new_path}): {e2}") from e2
        raise ToolError(f"Failed to delete trigger: {e}") from e
