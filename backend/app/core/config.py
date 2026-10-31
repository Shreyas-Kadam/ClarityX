import os
from functools import lru_cache
from pathlib import Path
from typing import List
from urllib.parse import urlparse
from dotenv import load_dotenv

# Robustly load .env file from the backend directory regardless of working directory
backend_dir = Path(__file__).resolve().parent.parent.parent
env_path = backend_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()


class Settings:
    """Centralized application settings loaded from environment variables."""

    PROJECT_NAME: str = "ClarityX"
    PROJECT_DESCRIPTION: str = (
        "AI-Powered Information Gap Detection Platform – "
        "Don't just tell users what you found. Tell them what you haven't found."
    )
    VERSION: str = "0.1.0"

    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    PORT: int = int(os.getenv("PORT", "8000"))

    # CORS Settings
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        origins = {
            self.FRONTEND_URL.rstrip("/"),
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }
        return list(origins)

    # Supabase Credentials (Phase 2)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def SUPABASE_BASE_URL(self) -> str:
        """Returns the normalized Supabase base URL (e.g. https://<ref>.supabase.co)."""
        if not self.SUPABASE_URL:
            return ""
        parsed = urlparse(self.SUPABASE_URL.strip())
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return self.SUPABASE_URL.strip().rstrip("/")

    # OpenRouter AI Credentials (Phase 6)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    @property
    def is_supabase_configured(self) -> bool:
        """Checks whether valid Supabase configuration is present."""
        return bool(self.SUPABASE_BASE_URL and self.SUPABASE_SERVICE_ROLE_KEY)

    @property
    def is_ai_configured(self) -> bool:
        """Checks whether OpenRouter AI credentials are configured."""
        return bool(self.OPENROUTER_API_KEY)


@lru_cache()
def get_settings() -> Settings:
    """Returns a cached Settings instance."""
    return Settings()

