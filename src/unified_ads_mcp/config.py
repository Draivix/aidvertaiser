"""Shared configuration helpers for Unified Ads MCP."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import yaml


_TRUTHY = {"1", "true", "yes", "y", "on"}

# Unified config directory — single source of truth for all credentials
CONFIG_DIR = Path.home() / ".unified-ads-mcp"


def resolve_config_path(filename: str, env_var: str | None = None) -> str:
    """Resolve config file path with unified fallback.

    Priority:
    1. Environment variable (if set and file exists)
    2. ~/.unified-ads-mcp/{filename}
    3. ~/{filename} (legacy fallback)
    """
    # 1. Env var override
    if env_var:
        env_path = os.environ.get(env_var)
        if env_path and os.path.exists(env_path):
            return env_path

    # 2. Unified config dir (preferred)
    unified_path = CONFIG_DIR / filename
    if unified_path.exists():
        return str(unified_path)

    # 3. Legacy home dir fallback
    legacy_path = Path.home() / filename
    if legacy_path.exists():
        return str(legacy_path)

    # Return unified path as default (even if doesn't exist yet)
    return str(unified_path)


def _env_flag(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY


def only_default_account_enabled() -> bool:
    """Return True when ONLY_DEFAULT_ACCOUNT is enabled via environment."""
    return _env_flag("ONLY_DEFAULT_ACCOUNT")


def _read_yaml(path: str) -> dict:
    """Read a YAML config file, returning {} on missing or invalid content."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _yaml_has_fields(path: str, fields: Iterable[str]) -> bool:
    config = _read_yaml(path)
    return all(config.get(field) for field in fields)


def _ads_yaml_path() -> str:
    return resolve_config_path("google-ads.yaml", "GOOGLE_ADS_CREDENTIALS")


def has_google_ads_config() -> bool:
    """Google Ads needs developer_token + client_id + client_secret."""
    return _yaml_has_fields(
        _ads_yaml_path(),
        ("developer_token", "client_id", "client_secret"),
    )


def _has_google_oauth_client() -> bool:
    """Shared client_id + client_secret available (analytics/gsc/gtm fall back to ads.yaml)."""
    return _yaml_has_fields(_ads_yaml_path(), ("client_id", "client_secret"))


def has_ga4_config() -> bool:
    path = resolve_config_path("google-analytics.yaml", "GOOGLE_ANALYTICS_CREDENTIALS")
    if _yaml_has_fields(path, ("client_id", "client_secret")):
        return True
    return _has_google_oauth_client()


def has_gsc_config() -> bool:
    path = resolve_config_path(
        "google-searchconsole.yaml", "GOOGLE_SEARCHCONSOLE_CREDENTIALS"
    )
    if _yaml_has_fields(path, ("client_id", "client_secret")):
        return True
    return _has_google_oauth_client()


def has_gtm_config() -> bool:
    path = resolve_config_path(
        "google-tagmanager.yaml", "GOOGLE_TAGMANAGER_CREDENTIALS"
    )
    if _yaml_has_fields(path, ("client_id", "client_secret")):
        return True
    return _has_google_oauth_client()


def has_meta_config() -> bool:
    """Meta needs an app or token via env or yaml."""
    if os.environ.get("META_ACCESS_TOKEN"):
        return True
    if os.environ.get("META_APP_ID") and os.environ.get("META_APP_SECRET"):
        return True
    config = _read_yaml(resolve_config_path("meta-ads.yaml", "META_ADS_CREDENTIALS"))
    if config.get("system_user_token") or config.get("access_token"):
        return True
    if config.get("app_id") and config.get("app_secret"):
        return True
    return False


def has_matomo_config() -> bool:
    return _yaml_has_fields(
        resolve_config_path("matomo.yaml", "MATOMO_CREDENTIALS"),
        ("url", "token_auth"),
    )


def has_bing_config() -> bool:
    return _yaml_has_fields(
        resolve_config_path("bing-webmaster.yaml", "BING_WEBMASTER_CREDENTIALS"),
        ("api_key",),
    )


def has_pagespeed_config() -> bool:
    """PageSpeed works without a key (rate-limited). Always available."""
    return True
