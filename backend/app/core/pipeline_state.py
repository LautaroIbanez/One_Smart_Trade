"""Lightweight state tracking for long-running startup pipelines.

This module provides a minimal, dependency-free way to record whether the
deterministic daily pipeline (triggered on startup) is still running. The
state is intentionally simple so that routers can quickly short-circuit and
return a 202/processing response instead of allowing requests to time out
while the pipeline warms up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class PipelineStatus:
    """Represents the status of the startup pipeline."""

    running: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "details": self.details,
        }


_status = PipelineStatus()


def mark_running(**details: Any) -> None:
    """Mark the pipeline as running with optional details."""

    global _status
    _status.running = True
    _status.started_at = datetime.utcnow()
    _status.completed_at = None
    _status.error = None
    _status.details = details


def mark_completed(**details: Any) -> None:
    """Mark the pipeline as completed successfully."""

    global _status
    _status.running = False
    _status.completed_at = datetime.utcnow()
    _status.error = None
    _status.details = details


def mark_failed(error: str, **details: Any) -> None:
    """Mark the pipeline as failed with an error message."""

    global _status
    _status.running = False
    _status.completed_at = datetime.utcnow()
    _status.error = error
    _status.details = details


def get_status() -> PipelineStatus:
    """Return the current pipeline status object."""

    return _status


def is_running() -> bool:
    """Convenience helper for checking running state."""

    return _status.running

