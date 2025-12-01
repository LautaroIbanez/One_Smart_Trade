from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from app.core.logging import logger

DATA_ROOT = Path("data")
RAW_ROOT = DATA_ROOT / "raw"
CURATED_ROOT = DATA_ROOT / "curated"


def ensure_dirs() -> None:
    """Ensure base data directories exist."""
    for directory in (RAW_ROOT, CURATED_ROOT):
        directory.mkdir(parents=True, exist_ok=True)


def get_raw_path(venue: str, symbol: str, interval: str, *, filename: str | None = None) -> Path:
    """Get normalized raw data path: {venue}/{symbol}/{interval}/{filename}."""
    if filename is None:
        filename = "latest.parquet"
    return RAW_ROOT / venue / symbol / interval / filename


def get_curated_path(venue: str, symbol: str, interval: str, *, filename: str | None = None) -> Path:
    """Get normalized curated data path: {venue}/{symbol}/{interval}/{filename}."""
    if filename is None:
        filename = "latest.parquet"
    return CURATED_ROOT / venue / symbol / interval / filename


def ensure_partition_dirs(venue: str, symbol: str, interval: str) -> tuple[Path, Path]:
    """Ensure partition directories exist for both raw and curated data."""
    raw_path = get_raw_path(venue, symbol, interval)
    curated_path = get_curated_path(venue, symbol, interval)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    curated_path.parent.mkdir(parents=True, exist_ok=True)
    return raw_path, curated_path


def write_parquet(
    df: pd.DataFrame,
    path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    validate_schema: bool = True,
    required_columns: list[str] | None = None,
) -> dict[str, Any]:
    """
    Write DataFrame to parquet with metadata and audit logging.
    
    Args:
        df: DataFrame to write
        path: Path where parquet will be written
        metadata: Optional metadata to include in .meta.json file
        validate_schema: If True, validate schema before writing (default: True)
        required_columns: List of required columns for validation (default: common OHLCV columns)
        
    Returns:
        Dict with write results: {"path": str, "checksum": str, "rows": int, "metadata": dict}
        
    Raises:
        ParquetSchemaError: If schema validation fails
    """
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # BE-DATA-02: Validate schema before writing
    if validate_schema:
        try:
            validation_result = validate_parquet_schema(
                df,
                path,
                required_columns=required_columns,
                strict=True,  # Raise error on schema issues
            )
            if not validation_result["valid"]:
                # This should not happen if strict=True (raises exception), but log anyway
                logger.error(
                    "Schema validation failed but no exception raised",
                    extra={
                        "path": str(path),
                        "validation_result": validation_result,
                    },
                )
        except ParquetSchemaError as exc:
            # Log actionable error with details
            logger.error(
                f"Parquet schema validation failed: {exc.message}",
                extra={
                    "path": str(path),
                    "error": exc.message,
                    "details": exc.details,
                    "actionable_error": True,
                },
            )
            raise
    
    df.to_parquet(path, compression="snappy", index=False)
    checksum = _checksum(path)
    payload = dict(metadata or {})
    payload["checksum"] = checksum
    payload.setdefault("rows", len(df))
    meta_path = path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_audit_log(path, payload)
    return {
        "path": str(path),
        "checksum": checksum,
        "rows": len(df),
        "metadata": payload,
    }


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


class ParquetSchemaError(Exception):
    """Raised when parquet schema validation fails."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


def validate_parquet_schema(
    df: pd.DataFrame,
    path: Path,
    *,
    required_columns: list[str] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """
    Validate parquet schema consistency before writing.
    
    Args:
        df: DataFrame to validate
        path: Path where parquet will be written
        required_columns: List of required column names (default: common OHLCV columns)
        strict: If True, raise error on schema mismatch; if False, log warning
        
    Returns:
        Dict with validation results: {"valid": bool, "existing_schema": dict, "new_schema": dict, "issues": list}
        
    Raises:
        ParquetSchemaError: If schema validation fails and strict=True
    """
    if required_columns is None:
        # Common required columns for OHLCV data
        required_columns = ["open_time", "open", "high", "low", "close", "volume"]
    
    validation_result = {
        "valid": True,
        "existing_schema": None,
        "new_schema": {
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "row_count": len(df),
        },
        "issues": [],
    }
    
    # Check required columns
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        issue = f"Missing required columns: {missing_columns}"
        validation_result["issues"].append(issue)
        validation_result["valid"] = False
        if strict:
            raise ParquetSchemaError(
                f"Schema validation failed: {issue}",
                details={
                    "missing_columns": missing_columns,
                    "required_columns": required_columns,
                    "available_columns": list(df.columns),
                },
            )
    
    # Check if existing file exists and compare schema
    if path.exists():
        try:
            existing_parquet = pq.ParquetFile(path)
            existing_schema = existing_parquet.schema_arrow
            existing_columns = [field.name for field in existing_schema]
            
            validation_result["existing_schema"] = {
                "columns": existing_columns,
                "schema_fields": [{"name": field.name, "type": str(field.type)} for field in existing_schema],
            }
            
            # Compare column sets
            new_columns = set(df.columns)
            existing_columns_set = set(existing_columns)
            
            # Check for missing columns in new schema
            missing_in_new = existing_columns_set - new_columns
            if missing_in_new:
                issue = f"Existing file has columns not in new data: {sorted(missing_in_new)}"
                validation_result["issues"].append(issue)
                validation_result["valid"] = False
                if strict:
                    raise ParquetSchemaError(
                        f"Schema drift detected: {issue}",
                        details={
                            "missing_in_new": sorted(missing_in_new),
                            "existing_columns": sorted(existing_columns),
                            "new_columns": sorted(df.columns),
                        },
                    )
            
            # Check for new columns (warn but don't fail - schema evolution is allowed)
            new_columns_added = new_columns - existing_columns_set
            if new_columns_added:
                logger.info(
                    f"New columns detected in schema (schema evolution): {sorted(new_columns_added)}",
                    extra={
                        "path": str(path),
                        "new_columns": sorted(new_columns_added),
                        "existing_columns": sorted(existing_columns),
                    },
                )
            
            # Check for type mismatches in common columns
            common_columns = new_columns & existing_columns_set
            type_mismatches = []
            for col in common_columns:
                existing_field = next((f for f in existing_schema if f.name == col), None)
                if existing_field:
                    new_dtype = str(df[col].dtype)
                    existing_type = str(existing_field.type)
                    # Allow some flexibility (e.g., int64 vs int32, float64 vs float32)
                    if not _dtypes_compatible(new_dtype, existing_type):
                        type_mismatches.append({
                            "column": col,
                            "existing_type": existing_type,
                            "new_type": new_dtype,
                        })
            
            if type_mismatches:
                issue = f"Type mismatches detected: {type_mismatches}"
                validation_result["issues"].append(issue)
                validation_result["valid"] = False
                if strict:
                    raise ParquetSchemaError(
                        f"Schema type mismatch: {issue}",
                        details={
                            "type_mismatches": type_mismatches,
                            "path": str(path),
                        },
                    )
        except Exception as exc:
            # If we can't read existing file, log warning but don't fail (file might be corrupted)
            logger.warning(
                f"Could not read existing parquet schema for validation: {exc}",
                extra={"path": str(path), "error": str(exc)},
            )
            validation_result["issues"].append(f"Could not read existing schema: {exc}")
            # Don't fail validation if we can't read existing file - might be first write
    
    return validation_result


def _dtypes_compatible(new_dtype: str, existing_type: str) -> bool:
    """Check if two dtypes are compatible (allowing some flexibility)."""
    # Normalize type strings
    new_dtype = new_dtype.lower()
    existing_type = existing_type.lower()
    
    # Exact match
    if new_dtype == existing_type:
        return True
    
    # Integer types are compatible
    if "int" in new_dtype and "int" in existing_type:
        return True
    
    # Float types are compatible
    if "float" in new_dtype and "float" in existing_type:
        return True
    
    # String/object types are compatible
    if ("object" in new_dtype or "string" in new_dtype) and ("object" in existing_type or "string" in existing_type):
        return True
    
    # Datetime types are compatible
    if "datetime" in new_dtype and "datetime" in existing_type:
        return True
    
    # Timestamp types are compatible
    if "timestamp" in new_dtype and "timestamp" in existing_type:
        return True
    
    return False


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_audit_log(path: Path, payload: dict[str, Any]) -> None:
    try:
        log_entry = {
            "path": str(path),
            "checksum": payload.get("checksum"),
            "rows": payload.get("rows", payload.get("metadata", {}).get("rows")),
            "metadata": payload,
        }
        log_dir = path.parent
        log_file = log_dir / "data_audit.log"
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_entry, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to append audit log", extra={"path": str(path), "error": str(exc)})