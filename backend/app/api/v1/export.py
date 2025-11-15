"""Export endpoints for recommendations with audit trail."""
import io
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Query, Response, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select, desc
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.crud import get_recommendation_history
from app.db.models import ExportAuditORM, RecommendationORM
from app.models.audit import ExportAuditRequest, ExportAuditResponse
from app.utils.hashing import calculate_file_md5, calculate_file_sha256

router = APIRouter()


def _apply_filters(query, filters: dict[str, Any]) -> Any:
    """Apply filters to SQLAlchemy query."""
    if filters.get("date_from"):
        date_from = datetime.fromisoformat(filters["date_from"])
        query = query.where(RecommendationORM.created_at >= date_from)

    if filters.get("date_to"):
        date_to = datetime.fromisoformat(filters["date_to"])
        query = query.where(RecommendationORM.created_at <= date_to)

    if filters.get("signal"):
        signals = filters["signal"] if isinstance(filters["signal"], list) else [filters["signal"]]
        query = query.where(RecommendationORM.signal.in_(signals))

    if filters.get("status"):
        statuses = filters["status"] if isinstance(filters["status"], list) else [filters["status"]]
        query = query.where(RecommendationORM.status.in_(statuses))

    if filters.get("exit_reason"):
        exit_reasons = (
            filters["exit_reason"] if isinstance(filters["exit_reason"], list) else [filters["exit_reason"]]
        )
        query = query.where(RecommendationORM.exit_reason.in_(exit_reasons))

    if filters.get("min_confidence") is not None:
        query = query.where(RecommendationORM.confidence >= float(filters["min_confidence"]))

    if filters.get("limit"):
        query = query.limit(int(filters["limit"]))

    return query


def _recommendation_to_dict(rec: RecommendationORM) -> dict[str, Any]:
    """Convert RecommendationORM to dictionary for export."""
    return {
        "id": rec.id,
        "date": rec.date,
        "signal": rec.signal,
        "entry_min": rec.entry_min,
        "entry_max": rec.entry_max,
        "entry_optimal": rec.entry_optimal,
        "stop_loss": rec.stop_loss,
        "take_profit": rec.take_profit,
        "stop_loss_pct": rec.stop_loss_pct,
        "take_profit_pct": rec.take_profit_pct,
        "confidence": rec.confidence,
        "current_price": rec.current_price,
        "market_timestamp": rec.market_timestamp,
        "spot_source": rec.spot_source,
        "status": rec.status,
        "opened_at": rec.opened_at.isoformat() if rec.opened_at else None,
        "closed_at": rec.closed_at.isoformat() if rec.closed_at else None,
        "exit_reason": rec.exit_reason,
        "exit_price": rec.exit_price,
        "exit_price_pct": rec.exit_price_pct,
        "code_commit": rec.code_commit,
        "dataset_version": rec.dataset_version,
        "params_digest": rec.params_digest,
        "created_at": rec.created_at.isoformat(),
        "indicators": rec.indicators,
        "risk_metrics": rec.risk_metrics,
        "factors": rec.factors,
        "signal_breakdown": rec.signal_breakdown,
        "analysis": rec.analysis,
    }


def _export_to_csv(recommendations: list[RecommendationORM]) -> bytes:
    """Export recommendations to CSV format."""
    data = [_recommendation_to_dict(rec) for rec in recommendations]
    df = pd.DataFrame(data)

    # Flatten nested JSON columns
    for col in ["indicators", "risk_metrics", "factors", "signal_breakdown"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: str(x) if x else "")

    buffer = io.BytesIO()
    df.to_csv(buffer, index=False, encoding="utf-8")
    return buffer.getvalue()


def _export_to_parquet(recommendations: list[RecommendationORM]) -> bytes:
    """Export recommendations to Parquet format."""
    data = [_recommendation_to_dict(rec) for rec in recommendations]
    df = pd.DataFrame(data)

    # Convert nested dicts to JSON strings for parquet
    for col in ["indicators", "risk_metrics", "factors", "signal_breakdown"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: str(x) if x else "")

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
    return buffer.getvalue()


def _get_metadata_from_recommendations(recommendations: list[RecommendationORM]) -> dict[str, str]:
    """Extract metadata from recommendations."""
    metadata: dict[str, str] = {}

    # Get unique values
    commits = {rec.code_commit for rec in recommendations if rec.code_commit}
    dataset_versions = {rec.dataset_version for rec in recommendations if rec.dataset_version}
    params_digests = {rec.params_digest for rec in recommendations if rec.params_digest}

    if len(commits) == 1:
        metadata["commit_hash"] = list(commits)[0]
    elif commits:
        metadata["commit_hash"] = "multiple"

    if len(dataset_versions) == 1:
        metadata["dataset_hash"] = list(dataset_versions)[0]
    elif dataset_versions:
        metadata["dataset_hash"] = "multiple"

    if len(params_digests) == 1:
        metadata["params_hash"] = list(params_digests)[0]
    elif params_digests:
        metadata["params_hash"] = "multiple"

    return metadata


@router.get("/export")
async def export_recommendations(
    format: str = Query("csv", regex="^(csv|parquet)$"),
    date_from: str | None = Query(None, description="Start date (ISO format)"),
    date_to: str | None = Query(None, description="End date (ISO format)"),
    signal: str | None = Query(None, description="Filter by signal (BUY|SELL|HOLD)"),
    status: str | None = Query(None, description="Filter by status (open|closed|inactive)"),
    exit_reason: str | None = Query(None, description="Filter by exit reason"),
    min_confidence: float | None = Query(None, ge=0, le=100, description="Minimum confidence"),
    limit: int | None = Query(None, ge=1, le=10000, description="Maximum number of records"),
) -> Response:
    """
    Export recommendations with filters and audit trail.

    Returns CSV or Parquet file with Content-Disposition and Content-MD5 headers.
    Includes metadata: commit_hash, dataset_hash, params_hash.
    """
    filters: dict[str, Any] = {
        "date_from": date_from,
        "date_to": date_to,
        "signal": signal,
        "status": status,
        "exit_reason": exit_reason,
        "min_confidence": min_confidence,
        "limit": limit,
    }

    # Remove None values
    filters = {k: v for k, v in filters.items() if v is not None}

    try:
        with SessionLocal() as db:
            # Build query
            query = select(RecommendationORM).order_by(desc(RecommendationORM.created_at))

            # Apply filters
            query = _apply_filters(query, filters)

            # Execute query
            recommendations = list(db.execute(query).scalars().all())

            if not recommendations:
                raise HTTPException(status_code=404, detail="No recommendations found matching filters")

            # Export to requested format
            if format == "csv":
                content = _export_to_csv(recommendations)
                media_type = "text/csv"
                file_ext = "csv"
            else:  # parquet
                content = _export_to_parquet(recommendations)
                media_type = "application/octet-stream"
                file_ext = "parquet"

            # Calculate hashes
            md5_hash = calculate_file_md5(content)
            sha256_hash = calculate_file_sha256(content)

            # Get metadata
            metadata = _get_metadata_from_recommendations(recommendations)

            # Create audit record
            export_audit = ExportAuditORM(
                filters=filters,
                format=format,
                record_count=len(recommendations),
                file_hash=sha256_hash,
                file_size_bytes=len(content),
                export_params=metadata,
            )
            db.add(export_audit)
            db.commit()
            logger.info(f"Export audit recorded: {export_audit.id}, {len(recommendations)} records, format={format}")

            # Generate filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"recommendations_{timestamp}.{file_ext}"

            # Create response with headers
            return Response(
                content=content,
                media_type=media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-MD5": md5_hash,
                    "X-Export-Metadata": str(metadata),
                    "X-Export-Record-Count": str(len(recommendations)),
                    "X-Export-File-Hash": sha256_hash,
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/export/audit", response_model=list[ExportAuditResponse])
async def get_export_audit(limit: int = Query(100, ge=1, le=1000)) -> list[ExportAuditResponse]:
    """Get export audit trail."""
    with SessionLocal() as db:
        stmt = select(ExportAuditORM).order_by(desc(ExportAuditORM.timestamp)).limit(limit)
        audits = list(db.execute(stmt).scalars().all())

        return [
            ExportAuditResponse(
                id=audit.id,
                timestamp=audit.timestamp.isoformat(),
                filters=audit.filters,
                format=audit.format,
                record_count=audit.record_count,
                file_hash=audit.file_hash,
                file_size_bytes=audit.file_size_bytes,
                export_params=audit.export_params,
            )
            for audit in audits
        ]

