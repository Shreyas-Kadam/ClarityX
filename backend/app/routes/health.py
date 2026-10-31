from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(tags=["Health & System"])
settings = get_settings()


@router.get(
    "/",
    summary="API Root",
    description="Confirms that the ClarityX backend is running.",
)
async def root():
    return {
        "message": "Welcome to ClarityX API",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
    }


@router.get(
    "/health",
    summary="Health Check",
    description="Health check endpoint verifying the backend service status.",
)
async def health_check():
    # Only report database/service status when explicitly configured and verified
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
    }

