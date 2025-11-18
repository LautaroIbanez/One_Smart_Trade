"""Export endpoints for recommendations with audit trail."""
import io
import json
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Query, Response, HTTPException, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select, desc, case, func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.logging import logger
from app.db.crud import get_recommendation_history
from app.db.models import ExportAuditORM, RecommendationORM
from app.models.audit import ExportAuditRequest, ExportAuditResponse
from app.utils.hashing import calculate_file_md5, calculate_file_sha256, calculate_params_hash

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


def _calculate_tracking_error(rec: RecommendationORM) -> dict[str, Any]:
    """Calculate tracking error metrics for a recommendation."""
    tracking_error_pct = None
    tracking_error_bps = None
    if rec.exit_price and rec.exit_reason:
        target_price = None
        if rec.exit_reason.upper() in ("TP", "TAKE_PROFIT", "take_profit"):
            target_price = rec.take_profit
        elif rec.exit_reason.upper() in ("SL", "STOP_LOSS", "stop_loss"):
            target_price = rec.stop_loss
        
        if target_price and target_price > 0:
            tracking_error_pct = abs((rec.exit_price - target_price) / target_price) * 100.0
            tracking_error_bps = tracking_error_pct * 100.0
    
    return {
        "tracking_error_pct": round(tracking_error_pct, 4) if tracking_error_pct is not None else None,
        "tracking_error_bps": round(tracking_error_bps, 2) if tracking_error_bps is not None else None,
    }


def _calculate_equity_realistic(rec: RecommendationORM, initial_equity: float = 1.0) -> float:
    """Calculate realistic equity based on exit_price_pct."""
    if rec.exit_price_pct is not None:
        return initial_equity * (1 + (rec.exit_price_pct / 100.0))
    return initial_equity


def _extract_execution_metrics(rec: RecommendationORM) -> dict[str, Any]:
    """Extract execution metrics from recommendation data."""
    snapshot = rec.snapshot_json or {}
    risk_metrics = rec.risk_metrics or {}
    
    # Extract fill quality from snapshot or risk_metrics
    fill_quality = None
    if "execution_stats" in snapshot:
        exec_stats = snapshot["execution_stats"]
        fill_quality = {
            "fill_rate": exec_stats.get("fill_rate"),
            "partial_fills": exec_stats.get("partial_fills", 0),
            "rejected_orders": exec_stats.get("rejected_orders", 0),
        }
    elif "fill_quality" in risk_metrics:
        fill_quality = risk_metrics["fill_quality"]
    
    # Extract orderbook fallback count
    orderbook_fallback_count = None
    if "execution_stats" in snapshot:
        orderbook_fallback_count = snapshot["execution_stats"].get("orderbook_fallback_count")
    elif "orderbook_fallback_count" in risk_metrics:
        orderbook_fallback_count = risk_metrics["orderbook_fallback_count"]
    
    return {
        "fill_quality": fill_quality,
        "orderbook_fallback_count": orderbook_fallback_count,
    }


def _calculate_snapshot_hash(rec: RecommendationORM) -> str:
    """Calculate hash of snapshot_json for integrity verification."""
    if not rec.snapshot_json:
        return ""
    try:
        snapshot_str = json.dumps(rec.snapshot_json, sort_keys=True, default=str)
        return calculate_file_sha256(snapshot_str.encode())
    except Exception:
        return ""


def _recommendation_to_dict(rec: RecommendationORM, cumulative_equity: float = 1.0) -> dict[str, Any]:
    """Convert RecommendationORM to dictionary for export with execution metrics."""
    tracking_error = _calculate_tracking_error(rec)
    execution_metrics = _extract_execution_metrics(rec)
    equity_realistic = _calculate_equity_realistic(rec, cumulative_equity)
    snapshot_hash = _calculate_snapshot_hash(rec)
    
    base_dict = {
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
        "confidence_calibrated": rec.confidence_calibrated,
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
        # Execution metrics
        "tracking_error_pct": tracking_error["tracking_error_pct"],
        "tracking_error_bps": tracking_error["tracking_error_bps"],
        "equity_realistic": round(equity_realistic, 6),
        "fill_quality": execution_metrics["fill_quality"],
        "orderbook_fallback_count": execution_metrics["orderbook_fallback_count"],
        # Snapshot hashes
        "snapshot_hash": snapshot_hash,
        "snapshot_has_worm": bool(rec.snapshot_json and rec.snapshot_json.get("worm_uuid")),
    }
    return base_dict


def _export_to_csv(recommendations: list[RecommendationORM]) -> bytes:
    """Export recommendations to CSV format."""
    cumulative_equity = 1.0
    data = []
    for rec in recommendations:
        data.append(_recommendation_to_dict(rec, cumulative_equity))
        # Update cumulative equity for next iteration
        if rec.exit_price_pct is not None:
            cumulative_equity *= (1 + (rec.exit_price_pct / 100.0))
    df = pd.DataFrame(data)

    # Flatten nested JSON columns
    for col in ["indicators", "risk_metrics", "factors", "signal_breakdown", "fill_quality"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, dict) else (str(x) if x else ""))

    buffer = io.BytesIO()
    df.to_csv(buffer, index=False, encoding="utf-8")
    return buffer.getvalue()


def _export_to_parquet(recommendations: list[RecommendationORM]) -> bytes:
    """Export recommendations to Parquet format."""
    cumulative_equity = 1.0
    data = []
    for rec in recommendations:
        data.append(_recommendation_to_dict(rec, cumulative_equity))
        # Update cumulative equity for next iteration
        if rec.exit_price_pct is not None:
            cumulative_equity *= (1 + (rec.exit_price_pct / 100.0))
    df = pd.DataFrame(data)

    # Convert nested dicts to JSON strings for parquet
    for col in ["indicators", "risk_metrics", "factors", "signal_breakdown", "fill_quality"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, dict) else (str(x) if x else ""))

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
    x_user_id: str | None = Header(None, alias="X-User-Id", description="User ID for audit trail"),
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

            # Create audit record with user tracking
            export_audit = ExportAuditORM(
                filters=filters,
                format=format,
                record_count=len(recommendations),
                file_hash=sha256_hash,
                file_size_bytes=len(content),
                export_params={**metadata, "exported_by": x_user_id or "anonymous"},
                exported_by=x_user_id or settings.DEFAULT_USER_ID,
            )
            db.add(export_audit)
            db.commit()
            logger.info(f"Export audit recorded: {export_audit.id}, {len(recommendations)} records, format={format}, user={x_user_id or 'anonymous'}")

            # Generate filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"recommendations_{timestamp}.{file_ext}"

            # Count recommendations with execution metrics
            has_execution_metrics = sum(1 for rec in recommendations if rec.snapshot_json and "execution_stats" in rec.snapshot_json)
            has_tracking_error = sum(1 for rec in recommendations if rec.exit_price and rec.exit_reason)
            
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
                    "X-Export-Audit-Id": str(export_audit.id),
                    "X-Export-Has-Execution-Metrics": str(has_execution_metrics),
                    "X-Export-Has-Tracking-Error": str(has_tracking_error),
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
                exported_by=getattr(audit, "exported_by", "anonymous"),
            )
            for audit in audits
        ]


@router.get("/export/manifest")
async def get_export_manifest(
    export_id: int | None = Query(None, description="Specific export ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of exports to include"),
) -> dict[str, Any]:
    """
    Get export manifest with all export records and their verification hashes.
    
    Returns a manifest that can be used to verify the integrity of exported datasets.
    """
    with SessionLocal() as db:
        if export_id:
            stmt = select(ExportAuditORM).where(ExportAuditORM.id == export_id)
            audits = list(db.execute(stmt).scalars().all())
        else:
            stmt = select(ExportAuditORM).order_by(desc(ExportAuditORM.timestamp)).limit(limit)
            audits = list(db.execute(stmt).scalars().all())
        
        manifest = {
            "manifest_version": "1.0",
            "generated_at": datetime.utcnow().isoformat(),
            "total_exports": len(audits),
            "exports": [
                {
                    "export_id": audit.id,
                    "timestamp": audit.timestamp.isoformat(),
                    "exported_by": getattr(audit, "exported_by", "anonymous"),
                    "format": audit.format,
                    "record_count": audit.record_count,
                    "file_size_bytes": audit.file_size_bytes,
                    "file_hash_sha256": audit.file_hash,
                    "filters": audit.filters,
                    "export_params": audit.export_params,
                    "verification": {
                        "hash_algorithm": "SHA-256",
                        "hash": audit.file_hash,
                        "can_verify": True,
                    },
                }
                for audit in audits
            ],
        }
        
        # Calculate manifest hash for integrity
        manifest_str = json.dumps(manifest, sort_keys=True, default=str)
        manifest_hash = calculate_file_sha256(manifest_str.encode())
        manifest["manifest_hash"] = manifest_hash
        
        return manifest

