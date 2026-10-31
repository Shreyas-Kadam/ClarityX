"""Authentication and user schemas for ClarityX."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class AuthenticatedUser(BaseModel):
    """Represents an authenticated user verified via Supabase Auth."""

    id: UUID
    email: Optional[str] = None
    full_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class UserProfileResponse(BaseModel):
    """Public user profile schema matching profiles database table."""

    id: UUID
    email: Optional[str] = None
    full_name: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

