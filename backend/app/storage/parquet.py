"""
Parquet Serialization Utilities (Milestone 3)

Provides deterministic conversion of normalized pandas DataFrames into
compact Apache Parquet files and persistence via the storage abstraction.
"""

from __future__ import annotations

import io
from typing import Optional

import pandas as pd

from app.storage.base import StorageBackend


def dataframe_to_parquet(df: pd.DataFrame) -> bytes:
    """
    Serialize a pandas DataFrame to Apache Parquet binary bytes using PyArrow.
    Preserves data types and handles missing values properly.
    """
    clean_df = df.copy()

    # Ensure all column names are strings
    clean_df.columns = [str(c) for c in clean_df.columns]

    # Convert object columns containing dates to datetime if possible
    for col in clean_df.columns:
        if clean_df[col].dtype == object:
            # Check if non-null values are dates/datetimes
            sample = clean_df[col].dropna().head(10)
            if not sample.empty:
                first = sample.iloc[0]
                import datetime as dt
                if isinstance(first, (dt.date, dt.datetime)):
                    clean_df[col] = pd.to_datetime(clean_df[col], errors="coerce")

    buf = io.BytesIO()
    clean_df.to_parquet(buf, engine="pyarrow", index=False, compression="snappy")
    return buf.getvalue()


def save_dataframe_as_parquet(
    df: pd.DataFrame,
    storage: StorageBackend,
    key: str,
) -> str:
    """
    Serialize DataFrame to Parquet and persist it atomically using the storage backend.
    Returns the confirmed object key.
    """
    parquet_bytes = dataframe_to_parquet(df)
    return storage.put_object(key, parquet_bytes)


def read_parquet_to_dataframe(
    storage: StorageBackend,
    key: str,
) -> pd.DataFrame:
    """
    Read a Parquet object from the storage backend into a pandas DataFrame.
    """
    # If the storage backend provides a local path, read directly from disk (fastest)
    try:
        path = storage.get_local_path(key)
        return pd.read_parquet(path, engine="pyarrow")
    except Exception:
        # Fall back to reading stream/bytes
        data = storage.get_object(key)
        return pd.read_parquet(io.BytesIO(data), engine="pyarrow")
