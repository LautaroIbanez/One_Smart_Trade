"""Utilities for tracking dataset versions and hashes."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.data.curation import DataCuration
from app.utils.hashing import calculate_dataset_hash
from app.core.logging import logger


def get_dataset_version_hash(interval: str = "1d", venue: str | None = None, symbol: str | None = None, include_both: bool = True) -> str:
    """
    Get hash representing the version of curated datasets used.
    
    Args:
        interval: Primary interval (for backward compatibility)
        venue: Optional venue filter
        symbol: Optional symbol filter
        include_both: If True, always include both 1h and 1d datasets (default: True for recommendations)
    
    Returns:
        SHA-256 hash of dataset files
    """
    from app.data.storage import get_curated_path

    curation = DataCuration()
    try:
        # Get paths to latest curated datasets
        dataset_paths: list[str] = []

        # Always get 1d dataset path
        try:
            if venue and symbol:
                path_1d = get_curated_path(venue=venue, symbol=symbol, interval="1d")
            else:
                # Fallback to legacy path
                path_1d = Path(settings.DATA_DIR) / "curated" / "1d" / "latest.parquet"

            if path_1d.exists():
                dataset_paths.append(str(path_1d))
            else:
                # Try loading to get metadata
                df_1d = curation.get_latest_curated(interval="1d", venue=venue, symbol=symbol)
                if df_1d is not None:
                    # Use file modification time as version indicator
                    dataset_paths.append(f"1d:{df_1d.shape[0]}:{df_1d.index[-1] if len(df_1d) > 0 else ''}")
        except Exception as e:
            logger.warning(f"Could not get 1d dataset path: {e}")

        # Get 1h dataset path if include_both is True or interval is not 1d
        if include_both or interval != "1d":
            try:
                if venue and symbol:
                    path_1h = get_curated_path(venue=venue, symbol=symbol, interval="1h")
                else:
                    # Fallback to legacy path
                    path_1h = Path(settings.DATA_DIR) / "curated" / "1h" / "latest.parquet"

                if path_1h.exists():
                    dataset_paths.append(str(path_1h))
                else:
                    # Try loading to get metadata
                    df_1h = curation.get_latest_curated(interval="1h", venue=venue, symbol=symbol)
                    if df_1h is not None:
                        dataset_paths.append(f"1h:{df_1h.shape[0]}:{df_1h.index[-1] if len(df_1h) > 0 else ''}")
            except Exception as e:
                logger.warning(f"Could not get 1h dataset path: {e}")

        if not dataset_paths:
            # Fallback: use curated directory structure
            data_dir = Path(settings.DATA_DIR) / "curated"
            for pattern in ["**/*1d.parquet", "**/*1h.parquet"]:
                for path in sorted(data_dir.glob(pattern), reverse=True):
                    if path.exists():
                        dataset_paths.append(str(path))
                        # Limit to most recent file per interval
                        break

        return calculate_dataset_hash(dataset_paths) if dataset_paths else "unknown"
    except Exception as e:
        logger.error(f"Error calculating dataset version hash: {e}")
        return "unknown"


def get_ingestion_timestamp(venue: str | None = None, symbol: str | None = None) -> datetime | None:
    """
    Get the ingestion timestamp from the latest curated datasets.
    
    Returns the most recent ingestion timestamp from 1h and 1d datasets.
    This represents when the data used for the recommendation was ingested.
    
    Args:
        venue: Optional venue filter
        symbol: Optional symbol filter
    
    Returns:
        Datetime of most recent ingestion, or None if not found
    """
    from app.data.storage import get_curated_path

    curation = DataCuration()
    timestamps: list[datetime] = []
    
    for interval in ["1d", "1h"]:
        try:
            if venue and symbol:
                path = get_curated_path(venue=venue, symbol=symbol, interval=interval)
            else:
                path = Path(settings.DATA_DIR) / "curated" / interval / "latest.parquet"
            
            # Try to read metadata from .meta.json file
            meta_path = path.with_suffix(".meta.json")
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                        # Try different timestamp fields
                        for field in ["generated_at", "fetched_at", "created_at"]:
                            if field in metadata:
                                ts_str = metadata[field]
                                try:
                                    # Parse ISO format timestamp
                                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                    timestamps.append(ts)
                                    break
                                except (ValueError, AttributeError):
                                    continue
                except Exception as e:
                    logger.debug(f"Could not read metadata from {meta_path}: {e}")
            
            # Fallback: use file modification time
            if path.exists() and not timestamps:
                stat = path.stat()
                ts = datetime.fromtimestamp(stat.st_mtime)
                timestamps.append(ts)
        except Exception as e:
            logger.debug(f"Could not get ingestion timestamp for {interval}: {e}")
    
    if timestamps:
        # Return the most recent timestamp
        return max(timestamps)
    
    return None


def get_params_digest() -> str:
    """
    Get hash representing the current parameters configuration.
    
    Uses SignalConfigManager to ensure consistent digest calculation
    from versioned configuration files.
    """
    from app.quant.config_manager import get_signal_config_digest

    try:
        return get_signal_config_digest()
    except Exception as e:
        logger.error(f"Error calculating params digest: {e}")
        return "unknown"

