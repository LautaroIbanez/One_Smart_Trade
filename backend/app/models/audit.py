"""Audit and snapshot models."""
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class RecommendationSnapshot:
    """Immutable snapshot of a recommendation with metadata."""

    payload: dict[str, Any]
    code_commit: str
    dataset_hash: str
    params_hash: str


class ExportAuditRequest(BaseModel):
    """Request parameters for export audit."""

    filters: dict[str, Any] = Field(default_factory=dict, description="Applied filters")
    format: str = Field(..., description="Export format (csv|parquet)")
    record_count: int = Field(..., description="Number of records exported")


class ExportAuditResponse(BaseModel):
    """Export audit record response."""

    id: int
    timestamp: str
    filters: dict[str, Any]
    format: str
    record_count: int
    file_hash: str
    file_size_bytes: int
    export_params: dict[str, Any]



