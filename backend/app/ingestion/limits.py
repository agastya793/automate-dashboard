"""
Centralised, environment-driven resource limits for the ingestion pipeline.

All values can be overridden by environment variables so production deployments
can tune caps without code changes.  Callers should import from here rather than
re-declaring their own magic numbers.
"""

from __future__ import annotations

import os


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


# Maximum rows the scanner will iterate in a single worksheet.
# Protects against bloated used-ranges (e.g. 573 k styled-but-empty rows).
MAX_SCAN_ROWS: int = _int_env("INGEST_MAX_SCAN_ROWS", 200_000)

# Maximum columns the scanner will consider per row.
MAX_SCAN_COLS: int = _int_env("INGEST_MAX_SCAN_COLS", 1_000)

# Maximum non-empty cells in a single block before it is capped.
MAX_BLOCK_CELLS: int = _int_env("INGEST_MAX_BLOCK_CELLS", 500_000)

# Maximum number of blocks returned per worksheet.
MAX_BLOCKS_PER_SHEET: int = _int_env("INGEST_MAX_BLOCKS_PER_SHEET", 50)

# Maximum number of worksheets processed.
MAX_SHEETS: int = _int_env("INGEST_MAX_SHEETS", 50)

# Maximum expanded bytes for the XLSX ZIP archive (zip-bomb guard).
XLSX_MAX_EXPANDED_BYTES: int = _int_env(
    "INGEST_XLSX_MAX_EXPANDED_BYTES", 50 * 1024 * 1024
)

# Maximum ZIP archive entries (zip-bomb guard).
XLSX_MAX_ARCHIVE_ENTRIES: int = _int_env("INGEST_XLSX_MAX_ARCHIVE_ENTRIES", 1_000)

# Maximum upload bytes — kept at 10 MiB until background workers are operational.
MAX_UPLOAD_BYTES: int = _int_env("INGEST_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)

# Maximum rows returned in a block sample preview.
MAX_PREVIEW_ROWS: int = _int_env("INGEST_MAX_PREVIEW_ROWS", 5)

# Maximum columns returned in a block sample preview.
MAX_PREVIEW_COLS: int = _int_env("INGEST_MAX_PREVIEW_COLS", 20)

# Edit-distance cutoff for label-merge suggestions.
LABEL_MERGE_CUTOFF: int = _int_env("INGEST_LABEL_MERGE_CUTOFF", 2)
