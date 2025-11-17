"""Persistence helpers for champion campaign records."""
from __future__ import annotations

from typing import Any

from app.core.database import SessionLocal
from app.core.logging import logger
from app.db import crud


def persist_campaign_record(record: dict[str, Any]) -> None:
    """Persist campaign evaluation records, promoting champions when required."""
    if not record:
        return

    status = record.get("status")
    if status != "improved":
        return

    with SessionLocal() as db:
        try:
            champion = crud.record_champion_promotion(db, record)
            logger.info(
                "Champion promoted",
                extra={
                    "params_id": champion.params_id,
                    "score": champion.score,
                    "objective": champion.objective,
                    "promoted_at": champion.promoted_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.exception("Failed to persist champion promotion", extra={"error": str(exc)})




