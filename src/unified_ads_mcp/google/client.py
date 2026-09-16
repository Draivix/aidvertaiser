"""Google Ads API client factory.

This module provides factory functions for creating configured Google Ads API clients
that use the authentication handled by the auth module.

Example:
    >>> from unified_ads_mcp.google.client import get_google_ads_client
    >>> client = get_google_ads_client()
    >>> # Use client with google-ads library
    >>> ga_service = client.get_service("GoogleAdsService")
"""

import os
import sys
from typing import Any, Optional

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message as ProtobufMessage
import proto
import yaml

from unified_ads_mcp.auth.google_auth import get_google_auth, GoogleAdsAuth
from ..config import only_default_account_enabled


# Default path for Google Ads credentials
from ..config import resolve_config_path
DEFAULT_CREDENTIALS_PATH = resolve_config_path("google-ads.yaml", "GOOGLE_ADS_CREDENTIALS")


class GoogleAdsClientFactory:
    """Factory for creating configured Google Ads API clients.

    This factory manages the creation of GoogleAdsClient instances with
    proper authentication and configuration. It supports:
        - Automatic OAuth authentication via browser
        - MCC (Manager Customer Center) account access
        - Customer ID specification at client creation time

    Example:
        >>> factory = GoogleAdsClientFactory()
        >>> client = factory.get_client(login_customer_id="1234567890")
    """

    def __init__(self, auth: Optional[GoogleAdsAuth] = None):
        """Initialize the client factory.

        Args:
            auth: Optional GoogleAdsAuth instance. If not provided,
                  the global singleton will be used.
        """
        self._auth = auth

    @property
    def auth(self) -> GoogleAdsAuth:
        """Get the auth handler, creating if necessary."""
        if self._auth is None:
            self._auth = get_google_auth()
        return self._auth

    def get_client(
        self,
        login_customer_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> GoogleAdsClient:
        """Get a configured Google Ads client.

        Args:
            login_customer_id: Customer ID to use for login (for MCC access).
                             Defaults to the value from config.
            force_refresh: If True, force re-authentication.

        Returns:
            A configured GoogleAdsClient instance.

        Raises:
            GoogleAdsException: If client creation fails.
        """
        auth = self.auth
        credentials = auth.get_credentials(force_refresh=force_refresh)

        # Use provided login_customer_id or fall back to config
        lid = login_customer_id or auth.login_customer_id

        # Clean up customer ID (remove dashes if present)
        if lid:
            lid = str(lid).replace("-", "")

        try:
            client = GoogleAdsClient(
                credentials=credentials,
                developer_token=auth.developer_token,
                login_customer_id=lid,
            )
            return client
        except Exception as e:
            print(f"[Google Ads] Client creation failed: {e}", file=sys.stderr)
            raise

    def validate_client(self, client: GoogleAdsClient) -> bool:
        """Validate that a client can successfully connect to the API.

        Args:
            client: The GoogleAdsClient to validate.

        Returns:
            True if the client is valid, False otherwise.
        """
        try:
            customer_service = client.get_service("CustomerService")
            accessible = customer_service.list_accessible_customers()
            return len(accessible.resource_names) > 0
        except GoogleAdsException:
            return False
        except Exception:
            return False


# Global factory instance
_factory: Optional[GoogleAdsClientFactory] = None


def get_google_ads_client(
    login_customer_id: Optional[str] = None,
    force_refresh: bool = False,
) -> GoogleAdsClient:
    """Get a configured Google Ads client using the global factory.

    This is the primary entry point for getting a Google Ads client.
    The client is configured with authentication from the auth module
    and is ready to use with the google-ads library.

    Args:
        login_customer_id: Customer ID to use for login (for MCC access).
                         If not provided, uses the value from config.
                         Format: "1234567890" (no dashes).
        force_refresh: If True, force re-authentication via browser.

    Returns:
        A configured GoogleAdsClient instance ready for API calls.

    Raises:
        FileNotFoundError: If Google Ads config file is not found.
        ValueError: If config is missing required fields.
        GoogleAdsException: If client creation fails.

    Example:
        >>> client = get_google_ads_client()
        >>>
        >>> # List accessible customers
        >>> customer_service = client.get_service("CustomerService")
        >>> accessible = customer_service.list_accessible_customers()
        >>>
        >>> # Execute a GAQL query
        >>> ga_service = client.get_service("GoogleAdsService")
        >>> query = "SELECT campaign.id, campaign.name FROM campaign"
        >>> response = ga_service.search(customer_id="1234567890", query=query)
    """
    global _factory

    if _factory is None:
        _factory = GoogleAdsClientFactory()

    return _factory.get_client(
        login_customer_id=login_customer_id,
        force_refresh=force_refresh,
    )


def get_login_customer_id() -> Optional[str]:
    """Gets the login_customer_id from the configuration.

    Returns:
        The login_customer_id if configured, None otherwise.
    """
    credentials_path = os.environ.get(
        "GOOGLE_ADS_CREDENTIALS", DEFAULT_CREDENTIALS_PATH
    )

    if not os.path.isfile(credentials_path):
        return None

    with open(credentials_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return str(config.get("login_customer_id", "")).replace("-", "") or None


def get_default_customer_id() -> Optional[str]:
    """Gets the default_customer_id from the configuration.

    This is the account to query by default when no customer_id is specified.
    Useful for avoiding AI confusion about which account to use.

    Returns:
        The default_customer_id if configured, falls back to login_customer_id.
    """
    credentials_path = os.environ.get(
        "GOOGLE_ADS_CREDENTIALS", DEFAULT_CREDENTIALS_PATH
    )

    if not os.path.isfile(credentials_path):
        return None

    with open(credentials_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Try default_customer_id first, fall back to login_customer_id
    default_id = config.get("default_customer_id") or config.get("login_customer_id")
    return str(default_id).replace("-", "") if default_id else None


def resolve_customer_id(customer_id: Optional[str]) -> str:
    """Resolve the customer ID, enforcing ONLY_DEFAULT_ACCOUNT when enabled."""
    default_id = get_default_customer_id()
    if only_default_account_enabled():
        customer_id = default_id
    else:
        customer_id = customer_id or default_id
    return clean_customer_id(customer_id or "")


def format_value(value: Any) -> Any:
    """Formats a value from a Google Ads API response.

    Converts protobuf messages and enums to JSON-serializable Python objects.

    Args:
        value: A value from the Google Ads API response.

    Returns:
        A JSON-serializable Python object.
    """
    if value is None:
        return None
    if isinstance(value, proto.Message):
        return proto.Message.to_dict(value)
    if isinstance(value, ProtobufMessage):
        return MessageToDict(value, preserving_proto_field_name=True)
    if isinstance(value, proto.Enum):
        # Return raw int for UNKNOWN enums so callers can identify newer types
        if value.name in ("UNKNOWN", "UNSPECIFIED"):
            return int(value)
        return value.name
    if isinstance(value, (str, bytes, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: format_value(v) for k, v in value.items()}
    # Protobuf repeated containers (RepeatedScalarContainer, RepeatedCompositeContainer)
    # support iteration and len() but may lack __iter__ (C extensions).
    if hasattr(value, "__iter__") or hasattr(value, "__len__"):
        return [format_value(item) for item in value]
    return str(value)


def get_enum_name(client: GoogleAdsClient, enum_path: str, value: Any) -> str:
    """Convert an enum value (int or enum object) to its name.

    Args:
        client: The GoogleAdsClient for accessing enum types.
        enum_path: The enum path like "CampaignStatusEnum" or "AdvertisingChannelTypeEnum".
        value: The enum value (int) or enum object.

    Returns:
        The enum name as a string.
    """
    if hasattr(value, "name"):
        return value.name

    # It's an integer, need to convert using protobuf EnumTypeWrapper
    try:
        enum_type = getattr(client.enums, enum_path)
        # Get the inner enum class (e.g., CampaignStatusEnum.CampaignStatus)
        inner_name = enum_path.replace("Enum", "")
        inner_enum = getattr(enum_type, inner_name, None)
        if inner_enum and hasattr(inner_enum, "Name"):
            # Protobuf enums use .Name(value) method
            return inner_enum.Name(value)
        # Fallback: just return the int as string
        return str(value)
    except Exception:
        return str(value)


def get_enum_value(client: GoogleAdsClient, enum_path: str, name: str) -> Any:
    """Convert an enum name to its protobuf enum value.

    Args:
        client: The GoogleAdsClient for accessing enum types.
        enum_path: The enum path like "CampaignStatusEnum" or "AdvertisingChannelTypeEnum".
        name: The enum name as a string (e.g., "ENABLED", "SEARCH").

    Returns:
        The protobuf enum value that can be assigned to message fields.
    """
    try:
        enum_type = getattr(client.enums, enum_path)
        # Access the enum value as an attribute (e.g., CampaignStatusEnum.ENABLED)
        return getattr(enum_type, name.upper())
    except AttributeError:
        raise ValueError(f"Invalid enum value '{name}' for {enum_path}")


def format_error(exception: GoogleAdsException) -> str:
    """Formats a GoogleAdsException into a readable error message.

    Args:
        exception: The GoogleAdsException to format.

    Returns:
        A formatted error message string.
    """
    errors = []
    for error in exception.failure.errors:
        errors.append(str(error))
    return "\n".join(errors)


def clean_customer_id(customer_id: str) -> str:
    """Cleans a customer ID by removing dashes and whitespace.

    Args:
        customer_id: The customer ID to clean.

    Returns:
        The cleaned customer ID containing only digits.
    """
    return customer_id.replace("-", "").replace(" ", "").strip()


def micros_to_currency(micros: int) -> float:
    """Converts micros to currency (dollars/euros/etc.).

    Google Ads API returns monetary values in micros where 1,000,000 micros = 1 unit of currency.
    This function converts to a human-readable decimal value.

    Args:
        micros: The value in micros.

    Returns:
        The value in currency units (e.g., dollars), rounded to 2 decimal places.
    """
    return round(micros / 1_000_000, 2)


def currency_to_micros(amount: float) -> int:
    """Converts currency amount to micros for the Google Ads API.

    Google Ads API expects monetary values in micros where 1,000,000 micros = 1 unit of currency.
    This function converts a human-readable decimal value to micros.

    Args:
        amount: The value in currency units (e.g., dollars).

    Returns:
        The value in micros as an integer.
    """
    return int(amount * 1_000_000)


def get_customer_currency(
    customer_id: str,
    login_customer_id: Optional[str] = None,
) -> str:
    """Gets the currency code for a Google Ads customer account.

    Args:
        customer_id: The Google Ads customer ID (digits only, no dashes).
        login_customer_id: Optional MCC account ID if accessing through
            a manager account.

    Returns:
        The currency code (e.g., 'CZK', 'USD', 'EUR').
    """
    try:
        client = get_google_ads_client(login_customer_id=login_customer_id)
        customer_id = clean_customer_id(customer_id)

        ga_service = client.get_service("GoogleAdsService")
        query = "SELECT customer.currency_code FROM customer LIMIT 1"

        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query,
        )

        for batch in response:
            for row in batch.results:
                return row.customer.currency_code

        return "USD"  # Default fallback
    except Exception:
        return "USD"  # Default fallback on error


def reset_client_factory() -> None:
    """Reset the global client factory (useful for testing)."""
    global _factory
    _factory = None
