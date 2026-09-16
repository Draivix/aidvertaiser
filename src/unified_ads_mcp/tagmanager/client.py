"""Google Tag Manager API client factory."""

import sys
from typing import Optional

from googleapiclient.discovery import build

from unified_ads_mcp.auth.google_tagmanager_auth import (
    get_google_tagmanager_auth,
    GoogleTagManagerAuth,
)


def get_tagmanager_service(force_refresh: bool = False):
    """Get a configured Google Tag Manager API v2 service."""
    auth = get_google_tagmanager_auth()
    credentials = auth.get_credentials(force_refresh=force_refresh)
    try:
        return build("tagmanager", "v2", credentials=credentials)
    except Exception as e:
        print(f"[Tag Manager] Client creation failed: {e}", file=sys.stderr)
        raise


def get_default_account_id() -> Optional[str]:
    """Get the default GTM account ID from config."""
    try:
        auth = get_google_tagmanager_auth()
        return auth.default_account_id
    except Exception:
        return None


def get_default_container_id() -> Optional[str]:
    """Get the default GTM container ID from config."""
    try:
        auth = get_google_tagmanager_auth()
        return auth.default_container_id
    except Exception:
        return None


def resolve_workspace_path(
    account_id: Optional[str] = None,
    container_id: Optional[str] = None,
    workspace_id: str = "Default Workspace",
) -> str:
    """Resolve the full workspace path for GTM API calls.

    Args:
        account_id: GTM account ID. Uses default from config if not provided.
        container_id: GTM container ID. Uses default from config if not provided.
        workspace_id: Workspace ID or name. Defaults to "Default Workspace".

    Returns:
        Full workspace path like "accounts/{id}/containers/{id}/workspaces/{id}".
    """
    if not account_id:
        account_id = get_default_account_id()
    if not account_id:
        raise ValueError(
            "No account_id provided and no default_account_id configured. "
            "Set default_account_id in google-tagmanager.yaml or pass account_id explicitly."
        )

    if not container_id:
        container_id = get_default_container_id()
    if not container_id:
        raise ValueError(
            "No container_id provided and no default_container_id configured. "
            "Set default_container_id in google-tagmanager.yaml or pass container_id explicitly."
        )

    # If workspace_id is not numeric, resolve it by listing workspaces
    if not workspace_id.isdigit():
        service = get_tagmanager_service()
        parent = f"accounts/{account_id}/containers/{container_id}"
        result = service.accounts().containers().workspaces().list(parent=parent).execute()
        workspaces = result.get("workspace", [])

        # Try to match by name
        for ws in workspaces:
            if ws.get("name") == workspace_id:
                workspace_id = ws["workspaceId"]
                break
        else:
            # If "Default Workspace" not found by name, use the first workspace
            if workspaces:
                workspace_id = workspaces[0]["workspaceId"]
            else:
                raise ValueError(
                    f"No workspaces found in container {container_id}. "
                    "Create a workspace first or specify a numeric workspace_id."
                )

    return f"accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}"


def get_active_workspace_id(
    account_id: Optional[str] = None,
    container_id: Optional[str] = None,
) -> str:
    """Get the current active (non-submitted) workspace ID.

    Returns the Default Workspace ID, or the first available workspace.
    """
    if not account_id:
        account_id = get_default_account_id()
    if not container_id:
        container_id = get_default_container_id()
    if not account_id or not container_id:
        raise ValueError("Cannot resolve active workspace without account and container IDs.")

    service = get_tagmanager_service()
    parent = f"accounts/{account_id}/containers/{container_id}"
    result = service.accounts().containers().workspaces().list(parent=parent).execute()
    workspaces = result.get("workspace", [])
    if not workspaces:
        raise ValueError("No workspaces found in container.")

    # Prefer "Default Workspace"
    for ws in workspaces:
        if ws.get("name") == "Default Workspace":
            return ws["workspaceId"]
    return workspaces[0]["workspaceId"]


def rewrite_path_to_active_workspace(path: str) -> str:
    """Replace the workspace ID in a GTM resource path with the current active workspace.

    Parses account_id and container_id from the path, looks up the active workspace,
    and returns the path with the corrected workspace ID.
    """
    import re

    m = re.match(
        r"accounts/(\d+)/containers/(\d+)/workspaces/\d+/(.*)",
        path,
    )
    if not m:
        raise ValueError(f"Cannot parse GTM resource path: {path}")

    account_id, container_id, resource_suffix = m.group(1), m.group(2), m.group(3)
    active_ws = get_active_workspace_id(account_id, container_id)
    return f"accounts/{account_id}/containers/{container_id}/workspaces/{active_ws}/{resource_suffix}"
