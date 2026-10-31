"""Database module for ClarityX.

Provides Supabase client access, connection verification utilities, and repository abstractions.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.repositories import (
        BaseRepository,
        ProfileRepository,
        ResearchRepository,
        SourceRepository,
    )
    from app.database.supabase import (
        get_supabase_admin_client,
        get_supabase_client,
        reset_supabase_client,
        verify_database_connection,
    )


def __getattr__(name: str):
    if name in (
        "get_supabase_client",
        "get_supabase_admin_client",
        "verify_database_connection",
        "reset_supabase_client",
    ):
        from app.database import supabase
        return getattr(supabase, name)
    if name in (
        "BaseRepository",
        "ProfileRepository",
        "ResearchRepository",
        "SourceRepository",
    ):
        from app.database import repositories
        return getattr(repositories, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_supabase_client",
    "get_supabase_admin_client",
    "verify_database_connection",
    "reset_supabase_client",
    "BaseRepository",
    "ProfileRepository",
    "ResearchRepository",
    "SourceRepository",
]

