"""
Utilities for handling async operations with timeouts and processing status.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar

from app.core.logging import logger

T = TypeVar("T")


async def with_timeout(
    coro: Callable[[], T],
    timeout_seconds: float,
    default_value: T | None = None,
    timeout_message: str = "Operation timed out",
) -> T | None:
    """
    Execute a coroutine with a timeout.
    
    Args:
        coro: Coroutine to execute
        timeout_seconds: Maximum time to wait
        default_value: Value to return if timeout occurs
        timeout_message: Message to log on timeout
    
    Returns:
        Result of coroutine or default_value if timeout
    """
    try:
        return await asyncio.wait_for(coro(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning(f"{timeout_message} (timeout: {timeout_seconds}s)")
        return default_value
    except Exception as exc:
        logger.error(f"Error in async operation: {exc}", exc_info=True)
        raise


class ProcessingResponse:
    """Response indicating an operation is still processing."""
    
    def __init__(self, operation_id: str, message: str = "Processing", estimated_seconds: float | None = None):
        self.status = "processing"
        self.operation_id = operation_id
        self.message = message
        self.estimated_seconds = estimated_seconds
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operation_id": self.operation_id,
            "message": self.message,
            "estimated_seconds": self.estimated_seconds,
        }

