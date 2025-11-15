"""WORM (Write Once Read Many) storage for immutable snapshots."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.utils.hashing import calculate_file_sha256, calculate_file_sha256 as hash_bytes


class WormRepository:
    """Write Once Read Many repository for immutable snapshots."""

    def __init__(self, base_dir: Path | None = None) -> None:
        """
        Initialize WORM repository.

        Args:
            base_dir: Base directory for snapshots (defaults to data/snapshots)
        """
        if base_dir is None:
            base_dir = Path(settings.DATA_DIR) / "snapshots"
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_snapshot(
        self,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Write an immutable snapshot to WORM storage.

        Args:
            payload: Data to snapshot
            metadata: Additional metadata (hashes, timestamps, etc.)

        Returns:
            Dict with snapshot info: {path, uuid, hash, date}
        """
        timestamp = datetime.utcnow()
        date_str = timestamp.strftime("%Y-%m-%d")
        snapshot_uuid = str(uuid.uuid4())
        filename = f"{date_str}-{snapshot_uuid}.json"

        # Create date-based subdirectory
        date_dir = self.base_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        snapshot_path = date_dir / filename

        # Prepare snapshot document
        snapshot = {
            "uuid": snapshot_uuid,
            "timestamp": timestamp.isoformat(),
            "payload": payload,
            "metadata": metadata or {},
        }


        # Write snapshot
        try:
            with snapshot_path.open("w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str, ensure_ascii=False)

            # Calculate hash
            file_hash = calculate_file_sha256(snapshot_path.read_bytes())

            # Update metadata with file hash
            snapshot["metadata"]["file_hash"] = file_hash
            with snapshot_path.open("w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str, ensure_ascii=False)

            logger.info(
                "Snapshot written to WORM storage",
                extra={
                    "uuid": snapshot_uuid,
                    "path": str(snapshot_path),
                    "hash": file_hash,
                },
            )

            return {
                "uuid": snapshot_uuid,
                "path": str(snapshot_path),
                "hash": file_hash,
                "date": date_str,
                "timestamp": timestamp.isoformat(),
                "file_hash": file_hash,
            }
        except Exception as e:
            logger.error(f"Failed to write snapshot: {e}", exc_info=True)
            raise

    def read_snapshot(self, uuid: str | None = None, path: Path | str | None = None) -> dict[str, Any] | None:
        """
        Read a snapshot by UUID or path.

        Args:
            uuid: Snapshot UUID
            path: Direct path to snapshot file

        Returns:
            Snapshot dict or None if not found
        """
        if path:
            snapshot_path = Path(path)
        elif uuid:
            # Search for snapshot by UUID
            snapshot_path = self._find_by_uuid(uuid)
            if snapshot_path is None:
                return None
        else:
            raise ValueError("Either uuid or path must be provided")

        if not snapshot_path.exists():
            logger.warning(f"Snapshot not found: {snapshot_path}")
            return None

        try:
            with snapshot_path.open("r", encoding="utf-8") as f:
                snapshot = json.load(f)

            # Verify hash if stored in metadata
            file_hash = calculate_file_sha256(snapshot_path.read_bytes())
            stored_hash = snapshot.get("metadata", {}).get("file_hash")
            if stored_hash and stored_hash != file_hash:
                logger.warning(f"Snapshot hash mismatch: {snapshot_path} (stored: {stored_hash}, calculated: {file_hash})")
            # Add calculated hash to snapshot
            snapshot["_calculated_hash"] = file_hash

            return snapshot
        except Exception as e:
            logger.error(f"Failed to read snapshot: {e}", exc_info=True)
            return None

    def _find_by_uuid(self, uuid: str) -> Path | None:
        """Find snapshot file by UUID (searches all date directories)."""
        for date_dir in sorted(self.base_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            for snapshot_file in date_dir.glob(f"*-{uuid}.json"):
                return snapshot_file
        return None

    def list_snapshots(
        self,
        date: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List snapshots, optionally filtered by date.

        Args:
            date: Filter by date (YYYY-MM-DD)
            limit: Maximum number of snapshots to return

        Returns:
            List of snapshot info dicts
        """
        snapshots: list[dict[str, Any]] = []

        if date:
            date_dir = self.base_dir / date
            if date_dir.exists():
                search_dirs = [date_dir]
            else:
                return []
        else:
            search_dirs = sorted([d for d in self.base_dir.iterdir() if d.is_dir()], reverse=True)

        for date_dir in search_dirs:
            for snapshot_file in sorted(date_dir.glob("*.json"), reverse=True):
                try:
                    with snapshot_file.open("r", encoding="utf-8") as f:
                        snapshot = json.load(f)
                    file_hash = calculate_file_sha256(snapshot_file.read_bytes())

                    snapshots.append({
                        "uuid": snapshot.get("uuid"),
                        "path": str(snapshot_file),
                        "hash": file_hash,
                        "date": date_dir.name,
                        "timestamp": snapshot.get("timestamp"),
                    })

                    if len(snapshots) >= limit:
                        return snapshots
                except Exception as e:
                    logger.warning(f"Failed to read snapshot {snapshot_file}: {e}")

        return snapshots

