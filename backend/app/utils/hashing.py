"""Hash calculation utilities for auditability."""
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from app.core.logging import logger


def get_git_commit_hash() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Could not get git commit hash: {e}")
        return "unknown"


def calculate_dataset_hash(dataset_paths: list[str] | None = None) -> str:
    """
    Calculate SHA-256 hash of dataset files for deterministic versioning.
    
    Uses file checksum for reproducibility: same file content produces same hash.
    This ensures that reproducing a recommendation with the same dataset version
    will produce identical results.
    """
    if not dataset_paths:
        return "unknown"

    hasher = hashlib.sha256()
    for path_str in sorted(dataset_paths):
        path = Path(path_str)
        if path.exists():
            try:
                # Include normalized path in hash
                normalized_path = str(path.resolve())
                hasher.update(normalized_path.encode())
                
                # For parquet files, hash the entire file content for determinism
                if path.suffix == ".parquet":
                    with open(path, "rb") as f:
                        # Read file in chunks to handle large files
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            hasher.update(chunk)
                else:
                    # For non-parquet files, use file modification time as fallback
                    stat = path.stat()
                    hasher.update(f"{stat.st_mtime}".encode())
            except Exception as e:
                logger.warning(f"Could not hash dataset file {path}: {e}")

    return hasher.hexdigest()[:64]


def calculate_params_hash(params: dict[str, Any]) -> str:
    """Calculate SHA-256 hash of parameters dictionary."""
    # Normalize dict by sorting keys and converting to JSON
    normalized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()[:64]


def calculate_file_md5(content: bytes) -> str:
    """Calculate MD5 hash of file content."""
    return hashlib.md5(content).hexdigest()


def calculate_file_sha256(content: bytes) -> str:
    """Calculate SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()[:64]




