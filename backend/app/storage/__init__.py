"""
Storage Package (Milestone 3)

Vendor-agnostic storage layer. Defaults to LocalStorageBackend (STORAGE_BACKEND=local).
"""

from __future__ import annotations

import os
from functools import lru_cache

from app.storage.base import (
    ObjectNotFoundError,
    PathTraversalError,
    StorageBackend,
    StorageError,
    validate_object_key,
)
from app.storage.local import LocalStorageBackend
from app.storage.parquet import (
    dataframe_to_parquet,
    read_parquet_to_dataframe,
    save_dataframe_as_parquet,
)


@lru_cache(maxsize=1)
def get_storage_backend() -> StorageBackend:
    """
    Factory resolving the active storage backend from environment.
    Defaults strictly to 'local' filesystem backend.
    """
    backend_type = os.getenv("STORAGE_BACKEND", "local").strip().lower()
    if backend_type == "local":
        return LocalStorageBackend()
    else:
        # Default fallback to local to avoid unverified cloud dependencies
        return LocalStorageBackend()


# Default singleton instance
storage: StorageBackend = get_storage_backend()

__all__ = [
    "StorageBackend",
    "LocalStorageBackend",
    "StorageError",
    "ObjectNotFoundError",
    "PathTraversalError",
    "validate_object_key",
    "dataframe_to_parquet",
    "save_dataframe_as_parquet",
    "read_parquet_to_dataframe",
    "get_storage_backend",
    "storage",
]
