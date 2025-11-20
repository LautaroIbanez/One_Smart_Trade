"""Structured logging configuration."""
import logging
import sys
from typing import Any

from pythonjsonlogger import jsonlogger

from app.core.config import settings

RESERVED_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
}


def setup_logging() -> logging.Logger:
    """Configure structured JSON logging."""
    root_logger = logging.getLogger()
    desired_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(desired_level)

    stream_handler_exists = any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)

    if not stream_handler_exists:
        log_handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d"
        )
        log_handler.setFormatter(formatter)
        root_logger.addHandler(log_handler)

    # Prevent double logging through parent loggers (e.g., uvicorn)
    root_logger.propagate = False

    return root_logger

logger = setup_logging()


def sanitize_log_extra(extra: dict[str, Any] | None, *, prefix: str = "extra_") -> dict[str, Any]:
    """
    Remove or rename reserved LogRecord attributes from a logging extra payload.

    Reserved keys like "message" or "lineno" would overwrite core logging fields—
    always sanitize external payloads before passing them to logger.*.
    """
    if not extra:
        return {}

    sanitized: dict[str, Any] = {}
    for key, value in extra.items():
        if key in RESERVED_LOG_RECORD_ATTRS:
            sanitized[f"{prefix}{key}"] = value
        else:
            sanitized[key] = value
    return sanitized

