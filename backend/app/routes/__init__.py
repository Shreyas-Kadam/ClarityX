"""API Route definitions for ClarityX."""

from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.research import router as research_router
from app.routes.sources import router as sources_router
from app.routes.verification import router as verification_router

__all__ = [
    "auth_router",
    "health_router",
    "research_router",
    "sources_router",
    "verification_router",
]
