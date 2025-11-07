"""Exception handling middleware for consistent error responses."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import logger


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            # Store status code for metrics
            request.state.status_code = response.status_code
            return response
        except StarletteHTTPException as exc:
            request.state.status_code = exc.status_code
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.detail, "status_code": exc.status_code},
            )
        except RequestValidationError as exc:
            request.state.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"error": "Validation error", "details": exc.errors()},
            )
        except Exception as exc:
            logger.error(f"Unhandled exception: {exc}", exc_info=True)
            request.state.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal server error",
                    "message": str(exc) if logger.level <= 10 else "An error occurred",
                },
            )

