from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


WORM_ROOT = Path(os.getenv("WORM_STORAGE_DIR", Path(__file__).resolve().parents[3] / "data" / "worm"))
WORM_ROOT.mkdir(parents=True, exist_ok=True)


def _hash_bytes(content: bytes, algo: Literal["md5", "sha256"] = "sha256") -> str:
    h = hashlib.new(algo)
    h.update(content)
    return h.hexdigest()


@dataclass
class StoredArtifact:
    path: Path
    md5: str
    sha256: str
    size: int


def store_artifact(content: bytes, *, prefix: str, ext: str) -> StoredArtifact:
    """
    Store content in WORM directory with immutable filename.
    Uses O_EXCL to prevent overwrites.
    """
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"{prefix}_{ts}.{ext.lstrip('.')}"
    fpath = WORM_ROOT / fname
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(fpath, flags, 0o644), "wb") as fh:
        fh.write(content)
    return StoredArtifact(
        path=fpath,
        md5=_hash_bytes(content, "md5"),
        sha256=_hash_bytes(content, "sha256"),
        size=len(content),
    )


