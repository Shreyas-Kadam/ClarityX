"""Supabase Client Module for ClarityX.

Provides a centralized, reusable Supabase client for privileged server-side
operations. Credentials are read strictly from application settings and
must never be exposed in API responses or logs.
"""

import logging
from typing import Any, Dict, Optional
from supabase import Client, create_client

from app.core.config import get_settings
from app.core.exceptions import DatabaseConfigurationError, DatabaseConnectionError

logger = logging.getLogger("clarityx.database")

# Cached client instance
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Returns a singleton Supabase client initialized with the service-role key.

    Raises:
        DatabaseConfigurationError: If SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing.
    """
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    settings = get_settings()

    if not settings.SUPABASE_BASE_URL:
        logger.error("Database initialization failed: SUPABASE_URL is missing")
        raise DatabaseConfigurationError(
            "SUPABASE_URL is not configured. Please set SUPABASE_URL in your backend .env file."
        )

    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.error("Database initialization failed: SUPABASE_SERVICE_ROLE_KEY is missing")
        raise DatabaseConfigurationError(
            "SUPABASE_SERVICE_ROLE_KEY is not configured. Please set SUPABASE_SERVICE_ROLE_KEY in your backend .env file."
        )

    try:
        # Initialize client with the normalized base URL and privileged service-role key
        _supabase_client = create_client(
            supabase_url=settings.SUPABASE_BASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info(f"Supabase client initialized successfully for {settings.SUPABASE_BASE_URL}")
        return _supabase_client
    except Exception as exc:
        logger.error(f"Failed to create Supabase client: {type(exc).__name__}")
        raise DatabaseConnectionError(
            f"Failed to initialize Supabase client: {type(exc).__name__}"
        ) from exc


def get_supabase_admin_client() -> Client:
    """Semantic alias for get_supabase_client() representing privileged operations."""
    return get_supabase_client()


def reset_supabase_client() -> None:
    """Resets the cached Supabase client instance (primarily used in tests)."""
    global _supabase_client
    _supabase_client = None


def verify_database_connection() -> Dict[str, Any]:
    """Verifies that the Supabase REST and Auth API can be reached and authenticated.

    This check verifies network connectivity and key validity without requiring
    any custom application database tables to exist yet.

    Returns:
        dict: Status dictionary with 'connected' boolean and descriptive message.
    """
    settings = get_settings()

    if not settings.SUPABASE_BASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        return {
            "connected": False,
            "status": "unconfigured",
            "message": "Supabase credentials are not fully configured in the environment.",
        }

    try:
        client = get_supabase_client()

        # Query the Auth admin API for a single user record to verify auth & network connectivity
        # This succeeds even on brand new Supabase projects with zero users and no tables.
        client.auth.admin.list_users(page=1, per_page=1)

        logger.info("Supabase database connection test verified successfully")
        return {
            "connected": True,
            "status": "connected",
            "message": "Supabase API reached and authenticated successfully.",
            "endpoint": settings.SUPABASE_BASE_URL,
        }
    except DatabaseConfigurationError as exc:
        return {
            "connected": False,
            "status": "unconfigured",
            "message": str(exc),
        }
    except Exception as exc:
        # Never log or expose credentials in error messages
        logger.warning(f"Supabase connectivity check failed: {type(exc).__name__}")
        return {
            "connected": False,
            "status": "error",
            "message": f"Connection check failed: {type(exc).__name__}",
        }


if __name__ == "__main__":
    import sys

    print("\n--- ClarityX Supabase Connectivity Check ---")
    result = verify_database_connection()
    if result.get("connected"):
        print(f"[SUCCESS] Status: {result.get('status')}")
        print(f"[SUCCESS] Message: {result.get('message')}")
        print(f"[SUCCESS] Endpoint: {result.get('endpoint')}")
        sys.exit(0)
    else:
        print(f"[FAILURE] Status: {result.get('status')}")
        print(f"[FAILURE] Message: {result.get('message')}")
        sys.exit(1)

