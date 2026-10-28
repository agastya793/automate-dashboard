"""
Local Filesystem Storage Backend (Milestone 3)

Implements private local filesystem storage under a configurable root directory.
Features:
- Strict path-traversal prevention.
- Atomic writes via temporary files and os.replace.
- Automatic parent directory creation.
- Bounded chunk streaming.
- Safe cleanup of incomplete writes on failure.
"""

from __future__ import annotations

import io
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Optional

from app.storage.base import (
    ObjectNotFoundError,
    PathTraversalError,
    StorageBackend,
    StorageError,
    validate_object_key,
)

DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "storage"


class LocalStorageBackend(StorageBackend):
    """Stores files on the local filesystem."""

    def __init__(self, root_dir: Optional[Path | str] = None):
        if root_dir is None:
            configured = os.getenv("STORAGE_LOCAL_ROOT") or os.getenv("LOCAL_STORAGE_DIR")
            self.root_dir = Path(configured).resolve() if configured else DEFAULT_STORAGE_ROOT.resolve()
        else:
            self.root_dir = Path(root_dir).resolve()
        
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        """
        Resolve key to an absolute Path and verify it does not escape the storage root.
        """
        clean_key = validate_object_key(key)
        target_path = (self.root_dir / clean_key).resolve()

        # Strict containment check
        try:
            target_path.relative_to(self.root_dir)
        except ValueError as exc:
            raise PathTraversalError(f"Access denied: Key '{key}' escapes storage root.") from exc

        return target_path

    def put_object(self, key: str, data: bytes | BinaryIO) -> str:
        """
        Atomically write data to key.
        Writes to a temporary file in the target directory first, then renames.
        """
        target_path = self._resolve_path(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_filename = f".tmp.{uuid.uuid4().hex}"
        tmp_path = target_path.parent / tmp_filename

        try:
            with open(tmp_path, "wb") as f:
                if isinstance(data, (bytes, bytearray)):
                    f.write(data)
                else:
                    shutil.copyfileobj(data, f, length=64 * 1024)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace (atomic on POSIX and Windows in modern Python)
            os.replace(tmp_path, target_path)
            return key
        except Exception as exc:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise StorageError(f"Failed to write object '{key}': {exc}") from exc

    def get_object(self, key: str) -> bytes:
        """Read full object bytes."""
        target_path = self._resolve_path(key)
        if not target_path.is_file():
            raise ObjectNotFoundError(f"Object '{key}' not found at {target_path}")
        try:
            return target_path.read_bytes()
        except Exception as exc:
            raise StorageError(f"Failed to read object '{key}': {exc}") from exc

    def get_object_stream(self, key: str) -> BinaryIO:
        """Open a binary stream for reading an object."""
        target_path = self._resolve_path(key)
        if not target_path.is_file():
            raise ObjectNotFoundError(f"Object '{key}' not found at {target_path}")
        return open(target_path, "rb")

    def object_exists(self, key: str) -> bool:
        """Check if object exists."""
        try:
            target_path = self._resolve_path(key)
            return target_path.is_file()
        except PathTraversalError:
            return False

    def delete_object(self, key: str) -> bool:
        """Delete an object if it exists."""
        try:
            target_path = self._resolve_path(key)
            if target_path.is_file():
                target_path.unlink()
                return True
            return False
        except (ObjectNotFoundError, PathTraversalError):
            return False
        except Exception as exc:
            raise StorageError(f"Failed to delete object '{key}': {exc}") from exc

    def get_local_path(self, key: str) -> Path:
        """Get the absolute filesystem path for DuckDB / Parquet queries."""
        target_path = self._resolve_path(key)
        if not target_path.is_file():
            raise ObjectNotFoundError(f"Object '{key}' not found at {target_path}")
        return target_path
