"""
Dataset profiling module for Phase 2.

Responsibilities:
- Validate and parse uploaded XLSX / CSV file bytes
- Infer column types using transparent, deterministic rules
- Compute data-quality statistics (missing values, duplicates)
- Produce structured warnings
- Never store file contents beyond the lifetime of the request
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

import pandas as pd
from pandas import DataFrame

from app.ingestion.bounds import SheetBounds, detect_all_sheet_bounds
from app.recommender import recommend_charts


# ---------------------------------------------------------------------------
# Resource limits (callers may override via config)
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024   # 10 MB
MAX_DATA_ROWS: int = 50_000
MAX_COLUMNS: int = 100
MAX_PREVIEW_ROWS: int = 20

# Guard against zip-bomb style XLSX archives
XLSX_MAX_ARCHIVE_ENTRIES: int = 1_000
XLSX_MAX_EXPANDED_BYTES: int = 200 * 1024 * 1024  # 200 MB expanded


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class DatasetError(Exception):
    """Base class for all dataset validation and parsing errors."""


class FileTooLargeError(DatasetError):
    pass


class UnsupportedFormatError(DatasetError):
    pass


class MalformedFileError(DatasetError):
    pass


class TooManyRowsError(DatasetError):
    pass


class TooManyColumnsError(DatasetError):
    pass


class InvalidSheetError(DatasetError):
    pass


# ---------------------------------------------------------------------------
# XLSX helpers
# ---------------------------------------------------------------------------

def _validate_xlsx_archive(raw: bytes) -> None:
    """
    Inspect the raw ZIP structure of an XLSX workbook before handing it to
    openpyxl.  Catches zip-bomb-style attacks and non-ZIP disguised files.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            entries = zf.infolist()
            if len(entries) > XLSX_MAX_ARCHIVE_ENTRIES:
                raise MalformedFileError(
                    f"XLSX archive contains too many entries "
                    f"({len(entries)} > {XLSX_MAX_ARCHIVE_ENTRIES})."
                )
            total_expanded = sum(e.file_size for e in entries)
            if total_expanded > XLSX_MAX_EXPANDED_BYTES:
                raise MalformedFileError(
                    f"XLSX archive would expand to {total_expanded / 1024 / 1024:.1f} MB, "
                    f"exceeding the {XLSX_MAX_EXPANDED_BYTES // 1024 // 1024} MB limit."
                )
            # Verify required XLSX parts exist
            names = {e.filename for e in entries}
            if "xl/workbook.xml" not in names and "xl/workbook.xml.rels" not in names:
                if not any("workbook" in n for n in names):
                    raise MalformedFileError(
                        "File does not appear to be a valid XLSX workbook "
                        "(missing xl/workbook.xml)."
                    )
    except zipfile.BadZipFile as exc:
        raise MalformedFileError(
            "File cannot be opened as a ZIP archive.  "
            "It may be corrupted, password-protected, or not a real XLSX file."
        ) from exc


def _load_xlsx(
    raw: bytes,
    sheet_name: str | None,
    max_rows: int,
    max_cols: int,
) -> tuple[list[str], str, DataFrame]:
    """
    Return (sheet_names, selected_sheet_name, dataframe).
    Uses openpyxl's read_only / data_only modes — never evaluates macros.
    Applies bounds detection to guard against bloated accidental ghost-row fill-downs.
    """
    _validate_xlsx_archive(raw)

    sheet_bounds_map = detect_all_sheet_bounds(raw)

    try:
        xl = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
    except Exception as exc:
        msg = str(exc).lower()
        if "encrypted" in msg or "password" in msg:
            raise MalformedFileError(
                "The workbook appears to be password-protected or encrypted."
            ) from exc
        raise MalformedFileError(f"Cannot open XLSX workbook: {exc}") from exc

    sheet_names: list[str] = xl.sheet_names

    if not sheet_names:
        raise MalformedFileError("The workbook contains no readable worksheets.")

    if sheet_name is not None:
        if sheet_name not in sheet_names:
            raise InvalidSheetError(
                f"Worksheet '{sheet_name}' was not found. "
                f"Available worksheets: {', '.join(sheet_names)}."
            )
        selected = sheet_name
    else:
        selected = sheet_names[0]

    bounds = sheet_bounds_map.get(selected)
    parse_kwargs: dict[str, Any] = {"engine": "openpyxl"}
    if bounds and bounds.has_ghost_tail:
        parse_kwargs["nrows"] = bounds.effective_data_max_row

    try:
        # Read with data_only=True so formula cells yield their last saved value
        # (or NaN).  We never execute formulas.
        df: DataFrame = xl.parse(
            selected,
            **parse_kwargs,
        )
    except Exception as exc:
        raise MalformedFileError(
            f"Failed to parse worksheet '{selected}': {exc}"
        ) from exc

    if bounds:
        df.attrs["sheet_bounds"] = bounds

    return sheet_names, selected, df


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _load_csv(raw: bytes, max_rows: int, max_cols: int) -> DataFrame:
    """Parse a UTF-8 or UTF-8-BOM CSV file."""
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise MalformedFileError(
            "Could not decode the CSV file as UTF-8.  "
            "Please save the file with UTF-8 encoding and try again."
        )

    try:
        df: DataFrame = pd.read_csv(
            io.StringIO(text),
            dtype=str,          # read everything as str initially; type inference below
            keep_default_na=False,  # we will handle NA ourselves
            na_values=["", "NA", "N/A", "NULL", "null", "None", "NaN", "nan", "#N/A"],
        )
    except Exception as exc:
        raise MalformedFileError(f"Cannot parse CSV content: {exc}") from exc

    return df


# ---------------------------------------------------------------------------
# Column type inference
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"),           # ISO date
    re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$"),          # d/m/y or m/d/y
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]\d{2}:\d{2}"),  # datetime
]

_CURRENCY_PATTERNS = [
    re.compile(r"^\s*[$€£¥₹]\s*-?[\d,]+(\.\d+)?\s*$"),
    re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*[$€£¥₹]\s*$"),
]

_PERCENT_PATTERNS = [
    re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*%\s*$"),
]

_CURRENCY_NAME_HINTS = re.compile(
    r"(?:price|amount|revenue|cost|fee|salary|spend|sales|budget|income|expense|total_usd|balance)$",
    re.IGNORECASE,
)

_PERCENT_NAME_HINTS = re.compile(
    r"(?:pct|percent|percentage|margin|rate|ratio|growth|discount|share)$",
    re.IGNORECASE,
)

_BOOL_VALUES = {
    "true", "false", "yes", "no", "1", "0",
    "y", "n", "t", "f", "on", "off",
}

_IDENTIFIER_NAME_HINTS = re.compile(
    r"(?:id|code|ref|sku|zip|postal|pin|ean|barcode|isbn|phone|mobile|"
    r"account|serial|batch|lot|order|invoice|ticket)$",
    re.IGNORECASE,
)


def _looks_like_identifier(col_name: str, series: "pd.Series[Any]") -> bool:
    """
    Returns True when a column looks like a categorical identifier rather than
    a numeric measure.  Heuristics:
    - Column name matches common identifier patterns.
    - All non-null values are integers but have leading zeros (e.g. postal codes).
    - Cardinality is high relative to row count but string-like patterns dominate.
    """
    if _IDENTIFIER_NAME_HINTS.search(col_name):
        return True
    # Leading-zero integers → identifier
    non_null = series.dropna().astype(str)
    if len(non_null) > 0 and non_null.str.match(r"^0\d+$").any():
        return True
    return False


def _infer_column_type(col_name: str, series: "pd.Series[Any]") -> str:
    """
    Infer a human-readable type label for a pandas Series.
    Returns one of: date, numeric, currency, percentage, categorical, identifier, text, boolean
    """
    # Already typed by pandas (e.g. from XLSX numeric/date cells)
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_float_dtype(series) or pd.api.types.is_integer_dtype(series):
        if _looks_like_identifier(col_name, series):
            return "identifier"
        if _CURRENCY_NAME_HINTS.search(col_name):
            return "currency"
        if _PERCENT_NAME_HINTS.search(col_name):
            return "percentage"
        return "numeric"

    # For object/string columns, work on non-null string values
    non_null = series.dropna().astype(str).str.strip()
    if len(non_null) == 0:
        return "text"

    n = len(non_null)

    # Percentage string check
    pct_matches = sum(bool(_PERCENT_PATTERNS[0].match(v)) for v in non_null.head(100))
    if pct_matches / min(n, 100) >= 0.7:
        return "percentage"

    # Currency string check
    cur_matches = sum(any(p.match(v) for p in _CURRENCY_PATTERNS) for v in non_null.head(100))
    if cur_matches / min(n, 100) >= 0.7:
        return "currency"

    # Boolean check
    lower = non_null.str.lower()
    if lower.isin(_BOOL_VALUES).all():
        return "boolean"

    # Date pattern check (sample up to 200 values)
    sample = non_null.head(200)
    date_matches = sum(
        any(p.match(v) for p in _DATE_PATTERNS) for v in sample
    )
    if date_matches / len(sample) >= 0.8:
        return "date"

    # Numeric check
    numeric_mask = pd.to_numeric(non_null.str.replace(",", "", regex=False), errors="coerce").notna()
    numeric_ratio = numeric_mask.sum() / n
    if numeric_ratio >= 0.9:
        if _looks_like_identifier(col_name, series):
            return "identifier"
        if _CURRENCY_NAME_HINTS.search(col_name):
            return "currency"
        if _PERCENT_NAME_HINTS.search(col_name):
            return "percentage"
        return "numeric"

    # Category: low cardinality relative to row count
    unique_ratio = non_null.nunique() / n
    if n >= 5 and unique_ratio <= 0.2:
        return "categorical"

    # Identifier heuristics on string columns
    if _looks_like_identifier(col_name, series):
        return "identifier"

    # Long average text → text
    avg_len = non_null.str.len().mean()
    if avg_len > 30:
        return "text"

    return "categorical"


# ---------------------------------------------------------------------------
# Data-quality profiling
# ---------------------------------------------------------------------------

def _profile_columns(
    df: DataFrame,
) -> list[dict[str, Any]]:
    """Return per-column statistics."""
    total = len(df)
    result = []
    for col in df.columns:
        series = df[col]
        missing_count = int(series.isna().sum())
        missing_pct = round(missing_count / total * 100, 2) if total > 0 else 0.0
        inferred = _infer_column_type(str(col), series)
        unique_count = int(series.nunique(dropna=True))
        
        # Sample values
        sample_vals: list[Any] = []
        for val in series.dropna().head(3):
            if pd.isna(val):
                continue
            if isinstance(val, float) and val == int(val):
                sample_vals.append(int(val))
            else:
                try:
                    sample_vals.append(val.isoformat())
                except AttributeError:
                    sample_vals.append(str(val) if not isinstance(val, (int, float, bool)) else val)

        result.append(
            {
                "name": str(col),
                "inferred_type": inferred,
                "missing_count": missing_count,
                "missing_pct": missing_pct,
                "missing_percentage": missing_pct,
                "unique_count": unique_count,
                "sample_values": sample_vals,
            }
        )
    return result


def _build_warnings(
    df: DataFrame,
    column_profiles: list[dict[str, Any]],
) -> list[str]:
    """Produce plain-language data-quality warnings."""
    warnings: list[str] = []

    # Sheet bounds / ghost tail warning
    bounds = getattr(df, "attrs", {}).get("sheet_bounds")
    if bounds and getattr(bounds, "has_ghost_tail", False) and getattr(bounds, "warning_message", None):
        warnings.append(bounds.warning_message)

    total = len(df)

    # Duplicate rows
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        warnings.append(
            f"{dup_count} duplicate row{'s' if dup_count != 1 else ''} detected. "
            "These are exact copies of other rows and may inflate aggregated totals."
        )

    # Completely empty columns
    empty_cols = [p["name"] for p in column_profiles if p["unique_count"] == 0]
    if empty_cols:
        names = ", ".join(f"'{c}'" for c in empty_cols[:5])
        warnings.append(
            f"Column{'s' if len(empty_cols) != 1 else ''} {names} "
            f"{'are' if len(empty_cols) != 1 else 'is'} entirely empty (100% missing values)."
        )

    # High missing value columns (>= 30%)
    high_missing = [
        p for p in column_profiles
        if p["missing_pct"] >= 30.0 and p["unique_count"] > 0
    ]
    for p in high_missing[:5]:
        warnings.append(
            f"Column '{p['name']}' has {p['missing_pct']}% missing values "
            f"({p['missing_count']} of {total} rows)."
        )

    # Duplicate column headers
    seen: set[str] = set()
    dupes: list[str] = []
    for col in df.columns:
        name = str(col)
        if name in seen:
            dupes.append(name)
        seen.add(name)
    if dupes:
        warnings.append(
            f"Duplicate column header{'s' if len(dupes) != 1 else ''} found: "
            + ", ".join(f"'{d}'" for d in dupes[:5])
            + ". Rename them before proceeding."
        )

    # Possible missing or shifted header
    unnamed_cols = [c for c in df.columns if str(c).startswith("Unnamed:")]
    if len(unnamed_cols) >= len(df.columns) / 2 and len(df.columns) > 1:
        warnings.append(
            "Possible missing or shifted header row: multiple columns are named 'Unnamed'. "
            "The first row of the table may not be headers."
        )

    # Columns that look like identifiers inferred as numbers
    suspicious = [
        p for p in column_profiles
        if p["inferred_type"] == "identifier"
    ]
    if suspicious:
        names = ", ".join(f"'{p['name']}'" for p in suspicious[:3])
        warnings.append(
            f"Column{'s' if len(suspicious) != 1 else ''} {names} "
            "appear to be identifier codes (e.g. postal codes, product codes), "
            "not numeric measures. They will not be treated as numbers."
        )

    return warnings


def _make_preview_rows(df: DataFrame, max_rows: int) -> list[list[Any]]:
    """Convert first N rows to a JSON-safe list of lists."""
    preview = df.head(max_rows)
    rows = []
    for _, row in preview.iterrows():
        cells = []
        for val in row:
            if pd.isna(val):
                cells.append(None)
            elif isinstance(val, float) and val == int(val):
                # Avoid 1.0 where 1 is more readable
                cells.append(int(val))
            else:
                try:
                    # Timestamps → ISO strings
                    cells.append(val.isoformat())
                except AttributeError:
                    cells.append(val)
        rows.append(cells)
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_and_validate_dataset(
    filename: str,
    raw: bytes,
    sheet_name: str | None = None,
    *,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    max_data_rows: int = MAX_DATA_ROWS,
    max_columns: int = MAX_COLUMNS,
) -> tuple[DataFrame, list[dict[str, Any]], str | None, list[str], str]:
    """
    Loads, parses, and validates dataset within resource limits.
    Returns (df, column_profiles, selected_sheet, sheet_names, file_type).
    Raises DatasetError subclasses for known failure modes.
    """
    # 1. Size limit (server-side)
    if len(raw) > max_upload_bytes:
        raise FileTooLargeError(
            f"File size ({len(raw) / 1024 / 1024:.1f} MB) exceeds the "
            f"{max_upload_bytes // 1024 // 1024} MB upload limit."
        )

    lower_name = filename.lower()

    # 2. Determine file type and parse
    sheet_names: list[str] = []
    selected_sheet: str | None = None

    if lower_name.endswith(".xlsx"):
        file_type = "xlsx"
        sheet_names, selected_sheet, df = _load_xlsx(
            raw, sheet_name, max_data_rows, max_columns
        )
        # Cast object columns to str so profiling is consistent
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype(str).replace("nan", pd.NA)

    elif lower_name.endswith(".csv"):
        file_type = "csv"
        df = _load_csv(raw, max_data_rows, max_columns)

    elif lower_name.endswith(".xls"):
        raise UnsupportedFormatError(
            "Legacy .xls format is not supported. "
            "Please save the workbook as .xlsx and upload again."
        )
    elif lower_name.endswith(".xlsm"):
        raise UnsupportedFormatError(
            ".xlsm files contain macros and are not accepted. "
            "Please save as .xlsx (macro-free) and upload again."
        )
    else:
        raise UnsupportedFormatError(
            f"Unsupported file type.  Only .xlsx and .csv files are accepted.  "
            f"Received: '{filename}'."
        )

    # 3. Row / column limits (after parse, server-enforced)
    if df.shape[1] > max_columns:
        raise TooManyColumnsError(
            f"The dataset has {df.shape[1]} columns, exceeding the "
            f"{max_columns}-column limit."
        )

    if len(df) > max_data_rows:
        raise TooManyRowsError(
            f"The dataset has {len(df):,} data rows, exceeding the "
            f"{max_data_rows:,}-row limit."
        )

    # 4. Empty dataset
    if df.empty or df.shape[1] == 0:
        raise MalformedFileError(
            "The file appears to be empty or contains no readable columns."
        )

    column_profiles = _profile_columns(df)
    return df, column_profiles, selected_sheet, sheet_names, file_type


def profile_dataset(
    filename: str,
    raw: bytes,
    sheet_name: str | None = None,
    *,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    max_data_rows: int = MAX_DATA_ROWS,
    max_columns: int = MAX_COLUMNS,
    max_preview_rows: int = MAX_PREVIEW_ROWS,
) -> dict[str, Any]:
    """
    Main entry point.  Returns a structured dict ready for JSON serialisation.
    Raises DatasetError subclasses for known failure modes.
    """
    df, column_profiles, selected_sheet, sheet_names, file_type = load_and_validate_dataset(
        filename=filename,
        raw=raw,
        sheet_name=sheet_name,
        max_upload_bytes=max_upload_bytes,
        max_data_rows=max_data_rows,
        max_columns=max_columns,
    )
    n_rows, n_cols = df.shape
    dup_count = int(df.duplicated().sum())
    total_missing = sum(p["missing_count"] for p in column_profiles)
    warnings = _build_warnings(df, column_profiles)
    preview_rows = _make_preview_rows(df, max_preview_rows)
    recommendations = recommend_charts(df, column_profiles)
    bounds = getattr(df, "attrs", {}).get("sheet_bounds")

    return {
        "filename": filename,
        "file_name": filename,
        "file_type": file_type,
        "file_size_bytes": len(raw),
        "sheet_names": sheet_names,
        "available_worksheets": sheet_names,
        "selected_sheet": selected_sheet,
        "selected_worksheet": selected_sheet,
        "row_count": n_rows,
        "total_rows": n_rows,
        "column_count": n_cols,
        "total_columns": n_cols,
        "column_names": [str(c) for c in df.columns],
        "columns": column_profiles,
        "duplicate_row_count": dup_count,
        "total_missing_cells": total_missing,
        "preview_rows": preview_rows,
        "warnings": warnings,
        "chart_recommendations": recommendations,
        "bounds": bounds.to_dict() if bounds else None,
        "sheet_bounds": bounds.to_dict() if bounds else None,
    }
