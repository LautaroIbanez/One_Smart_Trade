"""Transparency dashboard and monitoring endpoints."""
from fastapi import APIRouter, HTTPException
from typing import Any

from app.core.logging import logger
from app.services.transparency_service import TransparencyService

router = APIRouter()
transparency_service = TransparencyService()


@router.get("/dashboard")
async def get_transparency_dashboard() -> dict[str, Any]:
    """
    Get transparency dashboard with all verification statuses.
    
    Returns:
    - Semaphore status (overall and per-check)
    - Current hashes (code_commit, dataset_version, params_digest)
    - Hash verifications
    - Rolling tracking error (7d, 30d, 90d)
    - Drawdown divergence
    - Audit status
    """
    try:
        return await transparency_service.get_dashboard_data()
    except Exception as e:
        logger.error(f"Error generating transparency dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/semaphore")
async def get_transparency_semaphore() -> dict[str, Any]:
    """
    Get transparency semaphore status (quick health check).
    
    Returns overall status and per-check statuses.
    """
    try:
        semaphore = await transparency_service.get_semaphore()
        from dataclasses import asdict
        return asdict(semaphore)
    except Exception as e:
        logger.error(f"Error getting transparency semaphore: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hashes/verify")
async def verify_hashes() -> dict[str, Any]:
    """Verify current hashes against stored hashes."""
    try:
        verifications = transparency_service.verify_hashes()
        from dataclasses import asdict
        return {
            "verifications": [asdict(v) for v in verifications],
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error verifying hashes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tracking-error/rolling")
async def get_tracking_error_rolling(period_days: int = 30) -> dict[str, Any]:
    """Get rolling tracking error metrics for specified period."""
    try:
        result = await transparency_service.get_tracking_error_rolling(period_days)
        if not result:
            raise HTTPException(status_code=404, detail="Insufficient data for tracking error calculation")
        from dataclasses import asdict
        return asdict(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating rolling tracking error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drawdown/divergence")
async def get_drawdown_divergence() -> dict[str, Any]:
    """Get divergence between theoretical and realistic drawdown."""
    try:
        result = await transparency_service.get_drawdown_divergence()
        if not result:
            raise HTTPException(status_code=404, detail="Insufficient data for drawdown divergence calculation")
        from dataclasses import asdict
        return asdict(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating drawdown divergence: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/status")
async def get_audit_status() -> dict[str, Any]:
    """Get export audit status and hash change history."""
    try:
        return transparency_service.get_audit_status()
    except Exception as e:
        logger.error(f"Error getting audit status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

