"""Transparency monitoring service for automated verification and dashboard."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Any
from enum import Enum

from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.config import settings
from app.db.models import RecommendationORM, ExportAuditORM
from app.utils.hashing import (
    get_git_commit_hash,
    calculate_file_sha256,
    calculate_params_hash,
)
from app.utils.dataset_metadata import get_dataset_version_hash, get_params_digest
from app.services.performance_service import PerformanceService
from app.backtesting.tracking_error import TrackingErrorCalculator


class VerificationStatus(str, Enum):
    """Status of a verification check."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass
class HashVerification:
    """Result of a hash verification check."""
    hash_type: str  # code_commit, dataset_version, params_digest
    current_hash: str
    stored_hash: str | None
    status: VerificationStatus
    message: str
    timestamp: str


@dataclass
class TrackingErrorRolling:
    """Rolling tracking error metrics."""
    period_days: int
    mean_deviation: float
    max_divergence: float
    correlation: float
    rmse: float
    annualized_tracking_error: float
    timestamp: str


@dataclass
class DrawdownDivergence:
    """Divergence between theoretical and realistic drawdown."""
    theoretical_max_dd: float
    realistic_max_dd: float
    divergence_pct: float
    timestamp: str


@dataclass
class TransparencySemaphore:
    """Semaphore status for transparency checks."""
    overall_status: VerificationStatus
    hash_verification: VerificationStatus
    dataset_verification: VerificationStatus
    params_verification: VerificationStatus
    tracking_error_status: VerificationStatus
    drawdown_divergence_status: VerificationStatus
    audit_status: VerificationStatus
    last_verification: str
    details: dict[str, Any]


class TransparencyService:
    """Service for transparency monitoring and verification."""

    def __init__(self):
        self.performance_service = PerformanceService()

    def verify_hashes(self) -> list[HashVerification]:
        """Verify current hashes against stored hashes in recommendations."""
        verifications = []
        
        with SessionLocal() as db:
            # Get most recent recommendation
            stmt = select(RecommendationORM).order_by(desc(RecommendationORM.created_at)).limit(1)
            latest_rec = db.execute(stmt).scalars().first()
            
            if not latest_rec:
                return [
                    HashVerification(
                        hash_type="code_commit",
                        current_hash="",
                        stored_hash=None,
                        status=VerificationStatus.UNKNOWN,
                        message="No recommendations found",
                        timestamp=datetime.utcnow().isoformat(),
                    )
                ]
            
            # Verify code commit
            current_commit = get_git_commit_hash()
            stored_commit = latest_rec.code_commit
            commit_status = VerificationStatus.PASS
            commit_message = "Code commit matches"
            if stored_commit and current_commit != stored_commit:
                commit_status = VerificationStatus.WARN
                commit_message = f"Code commit changed: {stored_commit[:8]} -> {current_commit[:8]}"
            
            verifications.append(
                HashVerification(
                    hash_type="code_commit",
                    current_hash=current_commit,
                    stored_hash=stored_commit,
                    status=commit_status,
                    message=commit_message,
                    timestamp=datetime.utcnow().isoformat(),
                )
            )
            
            # Verify dataset version
            current_dataset = get_dataset_version_hash()
            stored_dataset = latest_rec.dataset_version
            dataset_status = VerificationStatus.PASS
            dataset_message = "Dataset version matches"
            if stored_dataset and current_dataset != stored_dataset:
                dataset_status = VerificationStatus.WARN
                dataset_message = f"Dataset version changed: {stored_dataset[:16]} -> {current_dataset[:16]}"
            
            verifications.append(
                HashVerification(
                    hash_type="dataset_version",
                    current_hash=current_dataset,
                    stored_hash=stored_dataset,
                    status=dataset_status,
                    message=dataset_message,
                    timestamp=datetime.utcnow().isoformat(),
                )
            )
            
            # Verify params digest
            current_params = get_params_digest()
            stored_params = latest_rec.params_digest
            params_status = VerificationStatus.PASS
            params_message = "Params digest matches"
            if stored_params and current_params != stored_params:
                params_status = VerificationStatus.WARN
                params_message = f"Params digest changed: {stored_params[:16]} -> {current_params[:16]}"
            
            verifications.append(
                HashVerification(
                    hash_type="params_digest",
                    current_hash=current_params,
                    stored_hash=stored_params,
                    status=params_status,
                    message=params_message,
                    timestamp=datetime.utcnow().isoformat(),
                )
            )
        
        return verifications

    def get_tracking_error_rolling(self, period_days: int = 30) -> TrackingErrorRolling | None:
        """Get rolling tracking error metrics for the specified period."""
        try:
            with SessionLocal() as db:
                # Get recommendations from the period
                cutoff_date = datetime.utcnow() - timedelta(days=period_days)
                stmt = (
                    select(RecommendationORM)
                    .where(RecommendationORM.created_at >= cutoff_date)
                    .where(RecommendationORM.status == "closed")
                    .where(RecommendationORM.exit_price.isnot(None))
                    .order_by(RecommendationORM.created_at)
                )
                recs = list(db.execute(stmt).scalars().all())
                
                if len(recs) < 2:
                    return None
                
                # Build equity curves from recommendations
                equity_theoretical = [1.0]
                equity_realistic = [1.0]
                
                for rec in recs:
                    # Calculate theoretical return
                    theoretical_return = 0.0
                    if rec.exit_reason and rec.exit_price_pct is not None:
                        # Use exit_price_pct as realistic, calculate theoretical from target
                        target_price = None
                        entry = rec.entry_optimal
                        if rec.exit_reason.upper() in ("TP", "TAKE_PROFIT"):
                            target_price = rec.take_profit
                        elif rec.exit_reason.upper() in ("SL", "STOP_LOSS"):
                            target_price = rec.stop_loss
                        
                        if target_price and entry:
                            if rec.signal == "BUY":
                                theoretical_return = ((target_price - entry) / entry) * 100.0
                            elif rec.signal == "SELL":
                                theoretical_return = ((entry - target_price) / entry) * 100.0
                    
                    realistic_return = rec.exit_price_pct or 0.0
                    
                    equity_theoretical.append(equity_theoretical[-1] * (1 + theoretical_return / 100.0))
                    equity_realistic.append(equity_realistic[-1] * (1 + realistic_return / 100.0))
                
                # Calculate tracking error
                if len(equity_theoretical) > 1 and len(equity_realistic) > 1:
                    calc = TrackingErrorCalculator.from_curves(
                        theoretical=equity_theoretical,
                        realistic=equity_realistic,
                    )
                    
                    return TrackingErrorRolling(
                        period_days=period_days,
                        mean_deviation=calc.mean_divergence_bps / 100.0,  # Convert bps to percentage
                        max_divergence=calc.max_divergence_bps / 100.0,
                        correlation=calc.correlation if hasattr(calc, "correlation") else 0.0,
                        rmse=calc.rmse if hasattr(calc, "rmse") else 0.0,
                        annualized_tracking_error=calc.annualized_tracking_error,
                        timestamp=datetime.utcnow().isoformat(),
                    )
        except Exception as e:
            logger.error(f"Error calculating rolling tracking error: {e}", exc_info=True)
        
        return None

    def get_drawdown_divergence(self) -> DrawdownDivergence | None:
        """Get divergence between theoretical and realistic drawdown."""
        try:
            result = self.performance_service.get_summary()
            
            tracking_error_metrics = result.get("tracking_error_metrics", {})
            theoretical_max_dd = tracking_error_metrics.get("theoretical_max_drawdown", 0.0)
            realistic_max_dd = tracking_error_metrics.get("realistic_max_drawdown", 0.0)
            
            if theoretical_max_dd == 0:
                return None
            
            divergence_pct = abs(realistic_max_dd - theoretical_max_dd) / abs(theoretical_max_dd) * 100.0
            
            return DrawdownDivergence(
                theoretical_max_dd=theoretical_max_dd,
                realistic_max_dd=realistic_max_dd,
                divergence_pct=divergence_pct,
                timestamp=datetime.utcnow().isoformat(),
            )
        except Exception as e:
            logger.error(f"Error calculating drawdown divergence: {e}", exc_info=True)
            return None

    def get_audit_status(self) -> dict[str, Any]:
        """Get status of export audits."""
        try:
            with SessionLocal() as db:
                # Get recent exports
                stmt = (
                    select(ExportAuditORM)
                    .order_by(desc(ExportAuditORM.timestamp))
                    .limit(100)
                )
                audits = list(db.execute(stmt).scalars().all())
                
                # Get hash changes
                hash_changes = []
                seen_hashes = {}
                for audit in audits:
                    export_params = audit.export_params or {}
                    commit_hash = export_params.get("commit_hash")
                    dataset_hash = export_params.get("dataset_hash")
                    params_hash = export_params.get("params_hash")
                    
                    if commit_hash and commit_hash != "multiple":
                        if "commit" in seen_hashes and seen_hashes["commit"] != commit_hash:
                            hash_changes.append({
                                "type": "code_commit",
                                "old": seen_hashes["commit"],
                                "new": commit_hash,
                                "timestamp": audit.timestamp.isoformat(),
                            })
                        seen_hashes["commit"] = commit_hash
                    
                    if dataset_hash and dataset_hash != "multiple":
                        if "dataset" in seen_hashes and seen_hashes["dataset"] != dataset_hash:
                            hash_changes.append({
                                "type": "dataset_version",
                                "old": seen_hashes["dataset"],
                                "new": dataset_hash,
                                "timestamp": audit.timestamp.isoformat(),
                            })
                        seen_hashes["dataset"] = dataset_hash
                    
                    if params_hash and params_hash != "multiple":
                        if "params" in seen_hashes and seen_hashes["params"] != params_hash:
                            hash_changes.append({
                                "type": "params_digest",
                                "old": seen_hashes["params"],
                                "new": params_hash,
                                "timestamp": audit.timestamp.isoformat(),
                            })
                        seen_hashes["params"] = params_hash
                
                return {
                    "total_exports": len(audits),
                    "recent_exports_24h": len([a for a in audits if (datetime.utcnow() - a.timestamp).total_seconds() < 86400]),
                    "hash_changes": hash_changes[-10:],  # Last 10 changes
                    "last_export": audits[0].timestamp.isoformat() if audits else None,
                }
        except Exception as e:
            logger.error(f"Error getting audit status: {e}", exc_info=True)
            return {
                "total_exports": 0,
                "recent_exports_24h": 0,
                "hash_changes": [],
                "last_export": None,
            }

    def get_semaphore(self) -> TransparencySemaphore:
        """Get overall transparency semaphore status."""
        verifications = self.verify_hashes()
        
        # Determine status for each check
        hash_status = VerificationStatus.PASS
        dataset_status = VerificationStatus.PASS
        params_status = VerificationStatus.PASS
        
        for v in verifications:
            if v.hash_type == "code_commit":
                hash_status = v.status
            elif v.hash_type == "dataset_version":
                dataset_status = v.status
            elif v.hash_type == "params_digest":
                params_status = v.status
        
        # Check tracking error
        tracking_error_30d = self.get_tracking_error_rolling(30)
        tracking_error_status = VerificationStatus.PASS
        if tracking_error_30d:
            if tracking_error_30d.annualized_tracking_error > 5.0:  # 5% threshold
                tracking_error_status = VerificationStatus.WARN
            if tracking_error_30d.annualized_tracking_error > 10.0:  # 10% threshold
                tracking_error_status = VerificationStatus.FAIL
            if tracking_error_30d.correlation < 0.90:
                tracking_error_status = VerificationStatus.WARN
        
        # Check drawdown divergence
        drawdown_div = self.get_drawdown_divergence()
        drawdown_status = VerificationStatus.PASS
        if drawdown_div:
            if drawdown_div.divergence_pct > 10.0:  # 10% divergence
                drawdown_status = VerificationStatus.WARN
            if drawdown_div.divergence_pct > 20.0:  # 20% divergence
                drawdown_status = VerificationStatus.FAIL
        
        # Audit status
        audit_status = VerificationStatus.PASS
        audit_info = self.get_audit_status()
        if audit_info["total_exports"] == 0:
            audit_status = VerificationStatus.WARN
        
        # Overall status (worst of all)
        overall_status = max(
            [hash_status, dataset_status, params_status, tracking_error_status, drawdown_status, audit_status],
            key=lambda s: ["pass", "warn", "fail", "unknown"].index(s.value),
        )
        
        return TransparencySemaphore(
            overall_status=overall_status,
            hash_verification=hash_status,
            dataset_verification=dataset_status,
            params_verification=params_status,
            tracking_error_status=tracking_error_status,
            drawdown_divergence_status=drawdown_status,
            audit_status=audit_status,
            last_verification=datetime.utcnow().isoformat(),
            details={
                "hash_verifications": [asdict(v) for v in verifications],
                "tracking_error_30d": asdict(tracking_error_30d) if tracking_error_30d else None,
                "drawdown_divergence": asdict(drawdown_div) if drawdown_div else None,
                "audit_info": audit_info,
            },
        )

    def get_dashboard_data(self) -> dict[str, Any]:
        """Get complete transparency dashboard data."""
        semaphore = self.get_semaphore()
        tracking_error_7d = self.get_tracking_error_rolling(7)
        tracking_error_30d = self.get_tracking_error_rolling(30)
        tracking_error_90d = self.get_tracking_error_rolling(90)
        drawdown_div = self.get_drawdown_divergence()
        audit_info = self.get_audit_status()
        verifications = self.verify_hashes()
        
        # Get current hashes
        current_hashes = {
            "code_commit": get_git_commit_hash(),
            "dataset_version": get_dataset_version_hash(),
            "params_digest": get_params_digest(),
        }
        
        return {
            "semaphore": asdict(semaphore),
            "current_hashes": current_hashes,
            "hash_verifications": [asdict(v) for v in verifications],
            "tracking_error_rolling": {
                "7d": asdict(tracking_error_7d) if tracking_error_7d else None,
                "30d": asdict(tracking_error_30d) if tracking_error_30d else None,
                "90d": asdict(tracking_error_90d) if tracking_error_90d else None,
            },
            "drawdown_divergence": asdict(drawdown_div) if drawdown_div else None,
            "audit_status": audit_info,
            "timestamp": datetime.utcnow().isoformat(),
        }

