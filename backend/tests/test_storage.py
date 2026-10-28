"""
Tests for Storage Abstraction and Local Filesystem Backend (Milestone 3).
"""

import io
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from app.storage import (
    LocalStorageBackend,
    ObjectNotFoundError,
    PathTraversalError,
    StorageError,
    dataframe_to_parquet,
    read_parquet_to_dataframe,
    save_dataframe_as_parquet,
    validate_object_key,
)


@pytest.fixture
def temp_storage():
    """Create a temporary storage backend for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    backend = LocalStorageBackend(root_dir=temp_dir)
    yield backend
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestKeyValidation:

    def test_valid_keys(self):
        assert validate_object_key("uploads/123/original.xlsx") == "uploads/123/original.xlsx"
        assert validate_object_key("datasets/abc-def/normalized.parquet") == "datasets/abc-def/normalized.parquet"
        assert validate_object_key("reports/q1.pdf") == "reports/q1.pdf"

    def test_path_traversal_rejected(self):
        with pytest.raises(PathTraversalError):
            validate_object_key("../../etc/passwd")

        with pytest.raises(PathTraversalError):
            validate_object_key("uploads/../../../secret.txt")

        with pytest.raises(PathTraversalError):
            validate_object_key("..")

        with pytest.raises(PathTraversalError):
            validate_object_key("")

    def test_invalid_characters_rejected(self):
        with pytest.raises(PathTraversalError):
            validate_object_key("uploads/bad*name/file.txt")


class TestLocalStorageBackend:

    def test_put_and_get_object(self, temp_storage: LocalStorageBackend):
        key = "uploads/u-1/original.xlsx"
        data = b"PK\x03\x04synthetic_excel_content"

        saved_key = temp_storage.put_object(key, data)
        assert saved_key == key
        assert temp_storage.object_exists(key) is True

        retrieved = temp_storage.get_object(key)
        assert retrieved == data

    def test_put_stream_and_get_stream(self, temp_storage: LocalStorageBackend):
        key = "datasets/d-1/data.bin"
        content = b"Streamed binary data" * 100
        stream = io.BytesIO(content)

        temp_storage.put_object(key, stream)
        assert temp_storage.object_exists(key) is True

        with temp_storage.get_object_stream(key) as reader:
            assert reader.read() == content

    def test_get_nonexistent_object_raises(self, temp_storage: LocalStorageBackend):
        with pytest.raises(ObjectNotFoundError):
            temp_storage.get_object("uploads/missing/original.xlsx")

    def test_delete_object(self, temp_storage: LocalStorageBackend):
        key = "uploads/del-1/file.txt"
        temp_storage.put_object(key, b"to delete")
        assert temp_storage.object_exists(key) is True

        deleted = temp_storage.delete_object(key)
        assert deleted is True
        assert temp_storage.object_exists(key) is False

        # Deleting non-existent returns False
        assert temp_storage.delete_object(key) is False

    def test_reject_path_traversal_on_put_and_get(self, temp_storage: LocalStorageBackend):
        with pytest.raises(PathTraversalError):
            temp_storage.put_object("../../outside.txt", b"danger")

        with pytest.raises(PathTraversalError):
            temp_storage.get_object("../../outside.txt")

    def test_atomic_write_no_temp_leftover(self, temp_storage: LocalStorageBackend):
        key = "uploads/atomic/file.bin"
        data = b"Atomic content"
        temp_storage.put_object(key, data)

        path = temp_storage.get_local_path(key)
        assert path.exists()

        # Ensure no .tmp files exist in parent
        tmp_files = list(path.parent.glob(".tmp.*"))
        assert len(tmp_files) == 0

    def test_get_local_path(self, temp_storage: LocalStorageBackend):
        key = "datasets/d-2/table.parquet"
        temp_storage.put_object(key, b"PAR1")

        path = temp_storage.get_local_path(key)
        assert isinstance(path, Path)
        assert path.is_file()

    def test_generate_key(self, temp_storage: LocalStorageBackend):
        k1 = temp_storage.generate_key("uploads", "u-1234", "Report.xlsx")
        assert k1 == "uploads/u-1234/original.xlsx"

        k2 = temp_storage.generate_key("datasets", "d-5678", "table.parquet")
        assert k2 == "datasets/d-5678/normalized.parquet"


class TestParquetStorage:

    def test_dataframe_to_parquet_and_read(self, temp_storage: LocalStorageBackend):
        df = pd.DataFrame(
            {
                "Month": ["Jan-26", "Feb-26", "Mar-26"],
                "Defect": ["Scratch", "Dent", "Scratch"],
                "Count": [10, 5, 12],
                "PPM": [120.5, 60.2, 144.6],
            }
        )

        key = "datasets/p-1/normalized.parquet"
        saved_key = save_dataframe_as_parquet(df, temp_storage, key)
        assert saved_key == key
        assert temp_storage.object_exists(key) is True

        read_df = read_parquet_to_dataframe(temp_storage, key)
        assert len(read_df) == 3
        assert list(read_df.columns) == ["Month", "Defect", "Count", "PPM"]
        assert read_df["Count"].tolist() == [10, 5, 12]
