import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import config

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Raised by validate_plan_body; mirrors the 400 response of the Express middleware."""

    def __init__(self, details: list[dict]):
        self.details = details


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SchemaValidationError)
    async def schema_error_handler(_req: Request, exc: SchemaValidationError):
        return JSONResponse(
            status_code=400,
            content={"error": "Schema validation failed", "details": exc.details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_req: Request, exc: StarletteHTTPException):
        if config.env != "test":
            logger.error("[ERROR] %s %s", exc.status_code, exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_req: Request, exc: Exception):
        if config.env != "test":
            logger.exception("[ERROR] 500 %s", exc)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})
