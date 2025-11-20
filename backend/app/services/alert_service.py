"""Simple alert dispatcher for operational notifications."""
from __future__ import annotations

from typing import Any

from app.core.logging import logger, sanitize_log_extra


class AlertService:
    """Dispatch alerts via structured logging (extendable to email/webhook)."""

    def notify(self, category: str, message: str, *, payload: dict[str, Any] | None = None, level: str = "warning") -> None:
        extra = {"category": category}
        if payload:
            extra.update(payload)
        # Sanitize payload to prevent reserved LogRecord collisions in structured logs.
        extra = sanitize_log_extra(extra)
        log_message = message
        if level == "error":
            logger.error(log_message, extra=extra)
        elif level == "info":
            logger.info(log_message, extra=extra)
        else:
            logger.warning(log_message, extra=extra)







