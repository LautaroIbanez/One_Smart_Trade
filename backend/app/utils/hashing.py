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
    """Calculate SHA-256 hash of dataset files or metadata."""
    if not dataset_paths:
        return "unknown"

    hasher = hashlib.sha256()
    for path_str in sorted(dataset_paths):
        path = Path(path_str)
        if path.exists():
            try:
                stat = path.stat()
                # Include path and modification time in hash
                hasher.update(f"{path}:{stat.st_mtime}".encode())
                # For parquet files, also hash first N bytes as sample
                if path.suffix == ".parquet":
                    with open(path, "rb") as f:
                        sample = f.read(1024)
                        hasher.update(sample)
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



