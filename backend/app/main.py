import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.research import router as research_router
from app.routes.sources import router as sources_router

# Setup application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("clarityx")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    logger.info(f"Starting {settings.PROJECT_NAME} backend v{settings.VERSION} [{settings.ENVIRONMENT}]")
    logger.info(f"CORS enabled for origins: {settings.ALLOWED_ORIGINS}")
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME} backend")


def create_app() -> FastAPI:
    """Application factory for ClarityX backend."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Configure CORS middleware for frontend communication
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register standardized exception handlers
    register_exception_handlers(app)

    # Register routes
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(research_router)
    app.include_router(sources_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)

