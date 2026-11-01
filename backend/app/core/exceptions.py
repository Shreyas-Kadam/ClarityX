import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("clarityx.exceptions")


class ClarityXException(Exception):
    """Base application exception for ClarityX."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        detail: str = "",
        headers: Optional[Dict[str, str]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        self.headers = headers
        super().__init__(message)


class AuthenticationError(ClarityXException):
    """Raised when authentication fails or access token is invalid/missing."""

    def __init__(self, message: str = "Authentication required", detail: str = ""):
        super().__init__(
            message=message,
            status_code=401,
            detail=detail or message,
            headers={"WWW-Authenticate": "Bearer"},
        )


class DatabaseConfigurationError(ClarityXException):
    """Raised when required database configuration is missing or invalid."""

    def __init__(self, message: str = "Database configuration is missing or invalid"):
        super().__init__(message=message, status_code=500, detail=message)


class DatabaseConnectionError(ClarityXException):
    """Raised when connecting to the database fails."""

    def __init__(self, message: str = "Unable to connect to the database"):
        super().__init__(message=message, status_code=503, detail=message)


class SSRFSecurityError(ClarityXException):
    """Raised when a URL violates SSRF security policies (private, loopback, metadata, invalid scheme)."""

    def __init__(
        self,
        message: str = "Security validation failed: Prohibited destination address.",
        detail: str = "",
    ):
        super().__init__(message=message, status_code=400, detail=detail or message)


class ContentSizeExceededError(ClarityXException):
    """Raised when downloaded website content exceeds maximum allowed body size."""

    def __init__(
        self,
        message: str = "Content size exceeds maximum allowable limit.",
        detail: str = "",
    ):
        super().__init__(message=message, status_code=413, detail=detail or message)


class UnsupportedContentTypeError(ClarityXException):
    """Raised when a target website provides an unsupported MIME type (e.g. binary/media)."""

    def __init__(
        self,
        message: str = "Unsupported content type. Only HTML and text documents can be processed.",
        detail: str = "",
    ):
        super().__init__(message=message, status_code=415, detail=detail or message)


class ExtractionError(ClarityXException):
    """Raised when content extraction fails across both primary and fallback extractors."""

    def __init__(
        self,
        message: str = "Failed to extract readable content from the provided source.",
        detail: str = "",
        status_code: int = 422,
    ):
        super().__init__(message=message, status_code=status_code, detail=detail or message)


class EncryptedDocumentError(ClarityXException):
    """Raised when an uploaded document is password-protected or encrypted."""

    def __init__(
        self,
        message: str = "Password-protected or encrypted documents cannot be processed.",
        detail: str = "",
    ):
        super().__init__(message=message, status_code=422, detail=detail or message)


class AIProviderError(ClarityXException):
    """Raised when the AI model provider (OpenRouter) fails or returns an API error."""

    def __init__(
        self,
        message: str = "The AI service encountered an error while processing the request.",
        detail: str = "External AI provider failed to complete analysis.",
        status_code: int = 502,
    ):
        super().__init__(message=message, status_code=status_code, detail=detail or message)


class AIResponseValidationError(ClarityXException):
    """Raised when the AI response is malformed, invalid JSON, or fails schema validation."""

    def __init__(
        self,
        message: str = "The AI model produced an invalid or unparseable analysis output.",
        detail: str = "AI analysis output failed schema validation.",
        status_code: int = 502,
    ):
        super().__init__(message=message, status_code=status_code, detail=detail or message)


class AITimeoutError(ClarityXException):
    """Raised when the AI analysis request exceeds the configured time limit."""

    def __init__(
        self,
        message: str = "The AI analysis request timed out. Please try again.",
        detail: str = "External AI analysis request exceeded the maximum allowed time limit.",
        status_code: int = 504,
    ):
        super().__init__(message=message, status_code=status_code, detail=detail or message)


def sanitize_validation_errors(errors: list) -> list:
    """Strips raw input values and sensitive data from validation error structures."""
    sanitized = []
    for err in errors:
        sanitized.append({
            "loc": err.get("loc", ()),
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        })
    return sanitized


def register_exception_handlers(app: FastAPI) -> None:
    """Registers standard JSON exception handlers across the application."""

    @app.exception_handler(ClarityXException)
    async def clarityx_exception_handler(request: Request, exc: ClarityXException):
        logger.warning(f"ClarityX error on {request.url.path}: {exc.message}")

        # Ensure all SSRF security errors return generic client-facing messages without leaking internal IPs/hostnames
        if isinstance(exc, SSRFSecurityError):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "message": "The requested URL cannot be accessed for security reasons.",
                    "detail": "Prohibited destination address or protocol.",
                },
                headers=exc.headers,
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": exc.message,
                "detail": exc.detail,
            },
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning(f"HTTP {exc.status_code} on {request.url.path}: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": exc.detail if isinstance(exc.detail, str) else "HTTP error",
                "detail": str(exc.detail),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # Sanitize errors to prevent logging raw inputs or sensitive values
        sanitized = sanitize_validation_errors(exc.errors())
        summary = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
            for err in sanitized
        )
        logger.warning(f"Validation error on {request.url.path}: {summary}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "success": False,
                "message": "Validation error in request payload",
                "detail": sanitized,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled server error on {request.url.path}: {type(exc).__name__}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "Internal server error",
                "detail": "An unexpected error occurred while processing the request.",
            },
        )
