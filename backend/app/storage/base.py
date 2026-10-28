"""
Storage Abstraction Layer - Base Interface (Milestone 3)

Provides a vendor-agnostic interface for storing and retrieving private raw
workbooks, normalized Parquet datasets, and export artifacts.
Defaults to local filesystem storage with no cloud dependencies.
"""

from __future__ import annotations

import abc
import os
import re
from pathlib import Path
from typing import BinaryIO, Optional


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class ObjectNotFoundError(StorageError):
    """Raised when the requested object key does not exist."""
    pass


class PathTraversalError(StorageError):
    """Raised when an object key attempts to traverse outside permitted storage roots."""
    pass


# Safe key pattern: alphanumeric segments separated by single forward slashes, hyphens, underscores, dots
_SAFE_KEY_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\.\-]+)*$")


def validate_object_key(key: str) -> str:
    """
    Validate that an object key is clean, safe, and does not contain path traversal attempts.
    """
    clean_key = (key or "").strip().replace("\\", "/").lstrip("/")
    if not clean_key:
        raise PathTraversalError("Object key cannot be empty.")
    if ".." in clean_key.split("/"):
        raise PathTraversalError(f"Path traversal detected in key: '{key}'")
    if not _SAFE_KEY_REGEX.match(clean_key):
        raise PathTraversalError(f"Invalid characters in object key: '{key}'")
    return clean_key


class StorageBackend(abc.ABC):
    """Abstract storage backend interface."""

    @abc.abstractmethod
    def put_object(self, key: str, data: bytes | BinaryIO) -> str:
        """
        Store data at the specified object key atomically.
        Returns the confirmed object key.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_object(self, key: str) -> bytes:
        """
        Retrieve raw bytes for an object key.
        Raises ObjectNotFoundError if key does not exist.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_object_stream(self, key: str) -> BinaryIO:
        """
        Open a binary stream for reading an object.
        Caller is responsible for closing the stream.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def object_exists(self, key: str) -> bool:
        """Return True if an object exists at key."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_object(self, key: str) -> bool:
        """
        Delete an object at key.
        Returns True if deleted, False if object did not exist.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_local_path(self, key: str) -> Path:
        """
        Return the local filesystem Path to the object for DuckDB or PyArrow.
        Raises ObjectNotFoundError if object does not exist.
        """
        raise NotImplementedError

    def generate_key(self, category: str, entity_id: str, filename: str) -> str:
        """
        Generate an opaque, organized storage key.
        Example: uploads/a1b2c3d4/original.xlsx
        """
        safe_category = re.sub(r"[^a-zA-Z0-9_\-]", "", category.strip().lower())
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(entity_id).strip())
        
        # Extract and sanitize extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".xlsx", ".csv", ".parquet", ".pdf", ".png", ".pptx", ".json"):
            ext = ".bin"
        
        base_name = "original" if category == "uploads" else ("normalized" if category == "datasets" else "artifact")
        return f"{safe_category}/{safe_id}/{base_name}{ext}"
