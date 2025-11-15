"""Utilities for tracking dataset versions and hashes."""
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.data.curation import DataCuration
from app.utils.hashing import calculate_dataset_hash
from app.core.logging import logger


def get_dataset_version_hash(interval: str = "1d", venue: str | None = None, symbol: str | None = None) -> str:
    """Get hash representing the version of curated datasets used."""
    from app.data.storage import get_curated_path
    from app.core.config import settings

    curation = DataCuration()
    try:
        # Get paths to latest curated datasets
        dataset_paths: list[str] = []

        # Get 1d dataset path
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

        # Get 1h dataset path
        if interval != "1d":
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


def get_params_digest() -> str:
    """Get hash representing the current parameters configuration."""
    from app.utils.hashing import calculate_params_hash
    from app.quant.params import STRATEGY_PARAMS

    try:
        # Convert to dict if needed
        params_dict = dict(STRATEGY_PARAMS) if hasattr(STRATEGY_PARAMS, "items") else STRATEGY_PARAMS
        return calculate_params_hash(params_dict)
    except Exception as e:
        logger.error(f"Error calculating params digest: {e}")
        return "unknown"

