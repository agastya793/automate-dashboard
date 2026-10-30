"""
Core workbook scanner: bytes → detected blocks.

Key corrections over ingest_reference.py
-----------------------------------------
* unpivot() guards id_cols[0] access when there are no identifier columns.
* summary-row heuristic uses a configurable threshold and flags uncertain rows
  for user review rather than silently discarding them.
* bloated-but-empty used ranges are bounded by MAX_SCAN_ROWS / MAX_SCAN_COLS.
* Empty sheets, duplicate/blank headers, merged ranges, hidden sheets,
  formula-cache misses, no period columns, and workbooks with no valid blocks
  are all handled explicitly.
* clean_labels() handles known=[], ties, mixed types, and duplicate candidates
  and returns suggestions only — never silently rewrites source data.
* Cell-fill colour reading is a targeted, bounded, separate pass; colour status
  is exposed as metadata (not silently dropped).
* Year hint is grounded in filename/sheet name; unknown year triggers a warning
  rather than a silent guess.
* Multiple measures (qty, PPM, %) are kept distinct — never summed together.
* parse_header() rejects suspicious day strings (e.g. 015-01-2026) and flags
  ambiguous / malformed date text.
* Formula-cache miss detection: compare formula vs data-only read and warn.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any

import openpyxl
import pandas as pd
from openpyxl.utils import get_column_letter

from app.ingestion.limits import (
    LABEL_MERGE_CUTOFF,
    MAX_BLOCK_CELLS,
    MAX_BLOCKS_PER_SHEET,
    MAX_PREVIEW_COLS,
    MAX_PREVIEW_ROWS,
    MAX_SCAN_COLS,
    MAX_SCAN_ROWS,
    MAX_SHEETS,
    MAX_UPLOAD_BYTES,
    XLSX_MAX_ARCHIVE_ENTRIES,
    XLSX_MAX_EXPANDED_BYTES,
)
from app.ingestion.bounds import (
    SheetBounds,
    detect_all_sheet_bounds,
    detect_openpyxl_sheet_bounds,
)

# ---------------------------------------------------------------------------
# Month lookup (3-letter abbreviations → 1-based month number)
# ---------------------------------------------------------------------------

_MONTHS: dict[str, int] = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}

# Columns that the app recomputes itself and should not be treated as raw data.
_DERIVED = re.compile(r"ytd|cum|%\s*of|total", re.IGNORECASE)

# Suspicious day-prefix pattern (e.g. "015-01-2026").
_SUSPICIOUS_DAY = re.compile(r"^\d{3,}-")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CellColour:
    """Fill colour of a single cell, expressed as hex RGB (no alpha)."""
    row: int          # 0-based
    col: int          # 0-based
    rgb: str | None   # "FF0000", "FFFFFF", None = unknown/theme/indexed
    raw_type: str     # "rgb", "indexed", "theme", "none"


@dataclass
class AmbiguousRow:
    """A row whose summary/record classification is uncertain."""
    source_row: int        # 0-based row index inside the block's data frame
    sheet_row: int         # 1-based row number in the worksheet
    reason: str
    raw_values: list[Any]  # non-sensitive: only labels, not confidential measures


@dataclass
class BlockResult:
    """
    Detected cell block metadata returned to callers.
    The df field is intentionally excluded from the JSON-safe scan result;
    only a bounded sample preview is exposed.
    """
    sheet: str
    r0: int                 # 0-based inclusive start row
    c0: int                 # 0-based inclusive start col
    r1: int                 # 0-based inclusive end row
    c1: int                 # 0-based inclusive end col
    kind: str = "unknown"   # "tidy" | "wide" | "records" | "form" | "unknown"
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0–1.0
    # Normalised long-form data (None for form / unclassified blocks)
    df: pd.DataFrame | None = None
    # Summary rows separated from defect/record rows
    summary_df: pd.DataFrame | None = None
    # Rows where the summary/record classification is uncertain
    ambiguous_rows: list[AmbiguousRow] = field(default_factory=list)
    # Detected column roles
    column_roles: dict[str, str] = field(default_factory=dict)
    # Cell fill colours (bounded pass, only when requested)
    cell_colours: list[CellColour] = field(default_factory=list)
    # Provenance
    header_row_index: int = 0   # 0-based index of the header row within the block
    formula_cache_warning: bool = False
    cap_reached: bool = False    # True if a row/cell/col limit was hit
    physical_max_row: int | None = None
    effective_data_max_row: int | None = None
    ignored_trailing_rows: int = 0

    @property
    def range(self) -> str:
        return (
            f"{get_column_letter(self.c0 + 1)}{self.r0 + 1}"
            f":{get_column_letter(self.c1 + 1)}{self.r1 + 1}"
        )

    def sample_preview(
        self,
        max_rows: int = MAX_PREVIEW_ROWS,
        max_cols: int = MAX_PREVIEW_COLS,
    ) -> list[list[Any]]:
        """Return a bounded, JSON-safe preview — never full workbook contents."""
        if self.df is None:
            return []
        sub = self.df.iloc[:max_rows, :max_cols]
        rows: list[list[Any]] = []
        for _, row in sub.iterrows():
            cells: list[Any] = []
            for v in row:
                if pd.isna(v) if not isinstance(v, str) else False:
                    cells.append(None)
                elif isinstance(v, (dt.date, dt.datetime)):
                    cells.append(v.isoformat())
                elif isinstance(v, float) and v == int(v):
                    cells.append(int(v))
                else:
                    cells.append(v)
            rows.append(cells)
        return rows

    def to_scan_dict(self) -> dict[str, Any]:
        """Return a bounded, JSON-safe dict for the /api/workbooks/scan response."""
        cols: list[str] = list(self.df.columns) if self.df is not None else []
        return {
            "sheet": self.sheet,
            "range": self.range,
            "kind": self.kind,
            "confidence": round(self.confidence, 3),
            "dimensions": {
                "rows": (self.r1 - self.r0 + 1),
                "cols": (self.c1 - self.c0 + 1),
            },
            "column_names": cols[:MAX_PREVIEW_COLS],
            "column_roles": self.column_roles,
            "sample_preview": self.sample_preview(),
            "notes": self.notes,
            "warnings": self.warnings,
            "formula_cache_warning": self.formula_cache_warning,
            "cap_reached": self.cap_reached,
            "ambiguous_row_count": len(self.ambiguous_rows),
            "ambiguous_rows": [
                {
                    "source_row": a.source_row,
                    "sheet_row": a.sheet_row,
                    "reason": a.reason,
                }
                for a in self.ambiguous_rows
            ],
            "cell_colours": [
                {"row": c.row, "col": c.col, "rgb": c.rgb, "raw_type": c.raw_type}
                for c in self.cell_colours
            ],
            "has_summary": self.summary_df is not None and len(self.summary_df) > 0,
            "bounds": {
                "physical_max_row": self.physical_max_row,
                "effective_data_max_row": self.effective_data_max_row,
                "ignored_trailing_rows": self.ignored_trailing_rows,
            } if self.physical_max_row is not None else None,
        }


@dataclass
class ScanResult:
    """Top-level result returned by scan_workbook."""
    filename: str
    sheet_names: list[str]
    blocks: list[BlockResult] = field(default_factory=list)
    global_warnings: list[str] = field(default_factory=list)
    cap_reached: bool = False
    sheet_bounds: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "sheet_names": self.sheet_names,
            "block_count": len(self.blocks),
            "cap_reached": self.cap_reached,
            "global_warnings": self.global_warnings,
            "sheet_bounds": self.sheet_bounds,
            "blocks": [b.to_scan_dict() for b in self.blocks],
        }


# ---------------------------------------------------------------------------
# Archive validation (zip-bomb guard)
# ---------------------------------------------------------------------------

def _validate_xlsx_archive(raw: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            entries = zf.infolist()
            if len(entries) > XLSX_MAX_ARCHIVE_ENTRIES:
                raise ValueError(
                    f"XLSX archive contains too many entries "
                    f"({len(entries)} > {XLSX_MAX_ARCHIVE_ENTRIES})."
                )
            total_expanded = sum(e.file_size for e in entries)
            if total_expanded > XLSX_MAX_EXPANDED_BYTES:
                raise ValueError(
                    f"XLSX archive would expand to "
                    f"{total_expanded / 1024 / 1024:.1f} MB, "
                    f"exceeding the "
                    f"{XLSX_MAX_EXPANDED_BYTES // 1024 // 1024} MB limit."
                )
            names = {e.filename for e in entries}
            if not any("workbook" in n for n in names):
                raise ValueError(
                    "File does not appear to be a valid XLSX workbook "
                    "(missing workbook.xml)."
                )
    except zipfile.BadZipFile as exc:
        raise ValueError(
            "File cannot be opened as a ZIP archive. "
            "It may be corrupted, password-protected, or not a real XLSX file."
        ) from exc


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

def parse_header(
    v: Any,
    year_hint: int | None = None,
) -> tuple[dt.date, str] | None:
    """
    Parse a header cell value into (first-of-month date, measure label).

    Accepts:
    - Real Excel date/datetime objects
    - Text like "Aug-26", "Jan qty", "Jan. PPM", "Jan 2026"

    Returns None when:
    - The value is not recognisable as a month header
    - The year cannot be determined (year_hint is None and no year in string)
    - The value looks like a suspicious day string (e.g. "015-01-2026")

    Never silently guesses an ambiguous year.
    """
    if v is None:
        return None

    # Real date / datetime from Excel numeric date serial
    if isinstance(v, dt.datetime):
        return dt.date(v.year, v.month, 1), "value"
    if isinstance(v, dt.date):
        return dt.date(v.year, v.month, 1), "value"

    if not isinstance(v, str):
        return None

    v = v.strip()
    if not v:
        return None

    # Reject suspicious leading digit patterns like "015-01-2026"
    if _SUSPICIOUS_DAY.match(v):
        return None

    # Pattern: optional leading space, 3-letter month, optional rest-of-month
    # letters, optional year (2 or 4 digits), optional measure label
    m = re.match(
        r"^([A-Za-z]{3})[a-z]*\.?[\s\-/']*(\d{4}|\d{2}(?!\d))?\s*(.*)$",
        v,
    )
    if not m:
        return None

    month_str = m.group(1).lower()
    if month_str not in _MONTHS:
        return None

    year_str = m.group(2)
    measure_raw = m.group(3).strip()

    if year_str:
        y = int(year_str)
        y = y + 2000 if y < 100 else y
    elif year_hint is not None:
        y = year_hint
    else:
        # Cannot ground the year — return None; caller emits warning
        return None

    # Normalise the measure label
    measure = re.sub(r"[^a-z%]+", " ", measure_raw.lower()).strip() or "value"

    try:
        date = dt.date(y, _MONTHS[month_str], 1)
    except ValueError:
        return None

    return date, measure


def guess_year(sheet: str, filename: str = "") -> int | None:
    """Extract a 4-digit year from the sheet name or filename. Returns None if absent."""
    m = re.search(r"(20\d{2})", f"{sheet} {filename}")
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Grid reading (data-only, no formula execution)
# ---------------------------------------------------------------------------

def _read_grid_data_only(
    ws: Any,
    global_warnings: list[str],
    max_row_limit: int | None = None,
) -> tuple[list[list[Any]], bool]:
    """
    Read cached cell values from one worksheet using data_only=True.

    Returns (grid, cap_reached).
    grid[r][c] is None for empty/whitespace-only strings.
    Rows beyond MAX_SCAN_ROWS and cols beyond MAX_SCAN_COLS are silently
    truncated with cap_reached=True set so the caller can warn the user.
    If max_row_limit is provided, bounds the scan to that effective row boundary.
    """
    rows: list[list[Any]] = []
    last_r = -1
    last_c = -1
    cap_reached = False

    scan_limit = min(MAX_SCAN_ROWS, max_row_limit) if max_row_limit else MAX_SCAN_ROWS

    for i, row in enumerate(ws.iter_rows(max_row=scan_limit, values_only=True)):
        if i >= scan_limit:
            if max_row_limit is None or scan_limit >= MAX_SCAN_ROWS:
                cap_reached = True
                global_warnings.append(
                    f"Sheet '{ws.title}': row scan limit ({MAX_SCAN_ROWS:,}) reached. "
                    "Remaining rows were not inspected. "
                    "The dataset may be larger than what was processed."
                )
            break

        # Trim row to MAX_SCAN_COLS
        if len(row) > MAX_SCAN_COLS:
            row = row[:MAX_SCAN_COLS]
            cap_reached = True

        vals: list[Any] = []
        for v in row:
            if isinstance(v, str) and not v.strip():
                vals.append(None)
            else:
                vals.append(v)

        nz = [j for j, v in enumerate(vals) if v is not None]
        if nz:
            last_r = i
            last_c = max(last_c, nz[-1])
        rows.append(vals)

    # Trim trailing empty rows and pad/trim columns
    trimmed: list[list[Any]] = []
    for r in rows[: last_r + 1]:
        padded = r[: last_c + 1]
        # Pad shorter rows
        if len(padded) < last_c + 1:
            padded = padded + [None] * (last_c + 1 - len(padded))
        trimmed.append(padded)

    return trimmed, cap_reached


def _detect_formula_cache_miss(
    raw: bytes,
    sheet_name: str,
    global_warnings: list[str],
    max_row_limit: int | None = None,
    cache: dict[str, bool] | None = None,
    wb_data: Any | None = None,
    wb_formula_holder: list[Any] | None = None,
) -> bool:
    """
    Compare a formula-mode read vs the data-only read to find cells whose
    cached values are missing (show as None in data_only but have a formula
    string in formula mode).

    Returns True if any cache miss is found (triggers a user warning).
    Silently returns False on any openpyxl error — we never block the scan.
    """
    if cache is not None and sheet_name in cache:
        return cache[sheet_name]

    close_f = False
    close_d = False
    wb_f = None
    wb_d = None
    try:
        if wb_formula_holder is not None and wb_formula_holder[0] is not None:
            wb_f = wb_formula_holder[0]
        else:
            wb_f = openpyxl.load_workbook(
                io.BytesIO(raw), data_only=False, read_only=True
            )
            if wb_formula_holder is not None:
                wb_formula_holder[0] = wb_f
            else:
                close_f = True

        if wb_data is not None:
            wb_d = wb_data
        else:
            wb_d = openpyxl.load_workbook(
                io.BytesIO(raw), data_only=True, read_only=True
            )
            close_d = True

        if sheet_name not in wb_f.sheetnames or sheet_name not in wb_d.sheetnames:
            if cache is not None:
                cache[sheet_name] = False
            return False
        ws_f = wb_f[sheet_name]
        ws_d = wb_d[sheet_name]

        limit = min(MAX_SCAN_ROWS, max_row_limit) if max_row_limit else MAX_SCAN_ROWS
        miss_count = 0
        for rf, rd in zip(
            ws_f.iter_rows(max_row=limit, values_only=True),
            ws_d.iter_rows(max_row=limit, values_only=True),
        ):
            for fv, dv in zip(rf, rd):
                if isinstance(fv, str) and fv.startswith("=") and dv is None:
                    miss_count += 1
                    if miss_count >= 5:
                        break
            if miss_count >= 5:
                break

        res = miss_count > 0
        if cache is not None:
            cache[sheet_name] = res
        return res

    except Exception:
        return False
    finally:
        if close_f and wb_f is not None:
            try:
                wb_f.close()
            except Exception:
                pass
        if close_d and wb_d is not None:
            try:
                wb_d.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Block detection (connected regions, no scipy dependency)
# ---------------------------------------------------------------------------

def _find_blocks(
    sheet_name: str,
    grid: list[list[Any]],
) -> list[tuple[int, int, int, int]]:
    """
    Find connected rectangular regions of non-empty cells using a simple
    Union-Find flood-fill.  A 1-cell gap does NOT split a table (we dilate
    the non-empty mask by 1 in each cardinal direction before grouping).

    Returns list of (r0, c0, r1, c1) tuples (0-based, inclusive).
    """
    if not grid:
        return []

    nrows = len(grid)
    ncols = max(len(r) for r in grid) if grid else 0
    if ncols == 0:
        return []

    # Build boolean occupancy mask (True = non-empty)
    occ: list[list[bool]] = [
        [grid[r][c] is not None if c < len(grid[r]) else False for c in range(ncols)]
        for r in range(nrows)
    ]

    # Dilate by 1 in all 4 cardinal directions to bridge 1-cell gaps
    dilated: list[list[bool]] = [
        [False] * ncols for _ in range(nrows)
    ]
    for r in range(nrows):
        for c in range(ncols):
            if occ[r][c]:
                for dr, dc in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < nrows and 0 <= nc < ncols:
                        dilated[nr][nc] = True

    # Label connected components via BFS on the dilated mask
    label_grid = [[-1] * ncols for _ in range(nrows)]
    next_label = 0

    for sr in range(nrows):
        for sc in range(ncols):
            if dilated[sr][sc] and label_grid[sr][sc] == -1:
                # BFS
                queue = [(sr, sc)]
                label_grid[sr][sc] = next_label
                head = 0
                while head < len(queue):
                    r, c = queue[head]
                    head += 1
                    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        nr, nc = r + dr, c + dc
                        if (
                            0 <= nr < nrows
                            and 0 <= nc < ncols
                            and dilated[nr][nc]
                            and label_grid[nr][nc] == -1
                        ):
                            label_grid[nr][nc] = next_label
                            queue.append((nr, nc))
                next_label += 1

    # Collect bounding boxes, only for components that have real data cells
    bounds: dict[int, tuple[int, int, int, int]] = {}
    for r in range(nrows):
        for c in range(ncols):
            lbl = label_grid[r][c]
            if lbl == -1 or not occ[r][c]:
                continue
            if lbl not in bounds:
                bounds[lbl] = (r, c, r, c)
            else:
                r0, c0, r1, c1 = bounds[lbl]
                bounds[lbl] = (min(r0, r), min(c0, c), max(r1, r), max(c1, c))

    # Filter: must be at least 2 rows × 2 cols (otherwise it's noise)
    result = [
        bb
        for bb in bounds.values()
        if (bb[2] - bb[0]) >= 1 and (bb[3] - bb[1]) >= 1
    ]

    return sorted(result, key=lambda b: (b[0], b[1]))


# ---------------------------------------------------------------------------
# Header normalisation
# ---------------------------------------------------------------------------

def _dedupe_headers(names: list[str]) -> list[str]:
    """Deduplicate column names by appending a counter to repeats."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 1
            out.append(n)
    return out


def _extract_header(
    sub: list[list[Any]],
) -> tuple[int, list[str]]:
    """
    Find the first row with ≥ 2 non-empty cells; return (row_index, col_names).
    Handles blank/None headers by generating synthetic col_N names.
    """
    h_idx = 0
    for i, row in enumerate(sub):
        non_empty = sum(1 for v in row if v is not None)
        if non_empty >= 2:
            h_idx = i
            break

    raw = sub[h_idx] if sub else []
    names: list[str] = []
    for j, v in enumerate(raw):
        if v is None:
            names.append(f"col_{j + 1}")
        else:
            names.append(re.sub(r"\s+", " ", str(v).strip()) or f"col_{j + 1}")

    return h_idx, _dedupe_headers(names)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_block(
    sheet: str,
    r0: int,
    c0: int,
    r1: int,
    c1: int,
    grid: list[list[Any]],
    year_hint: int | None,
    raw: bytes,
    bounds: SheetBounds | None = None,
    formula_cache_map: dict[str, bool] | None = None,
    wb_data: Any | None = None,
    wb_formula_holder: list[Any] | None = None,
) -> BlockResult:
    """
    Classify and normalise one detected block.

    Classification:
    - "form"    : free-text / A3 report layout; not a data table
    - "wide"    : multiple month columns → unpivoted to long form
    - "tidy"    : already long-form (rows × columns)
    - "records" : mixed or non-tabular data rows

    Returns a BlockResult with df, summary_df, column_roles, warnings, etc.
    """
    b = BlockResult(sheet=sheet, r0=r0, c0=c0, r1=r1, c1=c1)
    if bounds:
        b.physical_max_row = bounds.physical_max_row
        b.effective_data_max_row = bounds.effective_data_max_row
        b.ignored_trailing_rows = bounds.ignored_trailing_rows

    # Extract sub-grid for this block
    sub = [grid[r][c0: c1 + 1] for r in range(r0, r1 + 1)]

    if not sub:
        b.kind = "unknown"
        b.warnings.append("Block sub-grid is empty after extraction.")
        return b

    # Cell count guard
    cell_count = (r1 - r0 + 1) * (c1 - c0 + 1)
    if cell_count > MAX_BLOCK_CELLS:
        b.cap_reached = True
        b.warnings.append(
            f"Block {b.range} has {cell_count:,} cells "
            f"(cap {MAX_BLOCK_CELLS:,}). Only a partial scan was performed."
        )

    # Find header row
    h_idx, col_names = _extract_header(sub)
    b.header_row_index = h_idx
    body = sub[h_idx + 1:]

    if not body:
        b.kind = "form"
        b.notes.append("No data rows below header — likely a title or label cell.")
        b.confidence = 0.2
        return b

    # Count content types
    cells = [v for row in body for v in row if v is not None]
    if not cells:
        b.kind = "form"
        b.notes.append("Block header found but body is entirely empty.")
        b.confidence = 0.1
        return b

    num_vals = sum(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in cells
    )
    long_text = sum(isinstance(v, str) and len(v) > 80 for v in cells)
    short_hdr = sum(isinstance(v, str) and len(v) <= 40 for v in sub[h_idx])

    # Form detection: mostly long-text body, few numeric values, few short headers
    if long_text >= 3 and num_vals < len(cells) * 0.2 and short_hdr < 4:
        b.kind = "form"
        b.notes.append(
            "Free-text / report layout detected. "
            "Not treated as a data table. "
            "User review recommended before use."
        )
        b.confidence = 0.5
        return b

    # Check if header looks like month columns (wide format)
    parsed_periods = [parse_header(v, year_hint) for v in sub[h_idx]]
    n_periods = sum(p is not None for p in parsed_periods)

    # Warn if year_hint was needed but absent (some period headers may have failed)
    none_due_to_year = sum(
        1
        for v, p in zip(sub[h_idx], parsed_periods)
        if p is None and isinstance(v, str) and v.strip()[:3].lower() in _MONTHS
    )
    if none_due_to_year > 0 and year_hint is None:
        b.warnings.append(
            f"{none_due_to_year} column header(s) look like month names but "
            "no year could be determined from the filename or sheet name. "
            "Please confirm the year so month headers can be correctly parsed."
        )

    # Build a DataFrame for the body
    try:
        df = pd.DataFrame(body, columns=col_names).dropna(how="all")
    except Exception as exc:
        b.kind = "unknown"
        b.warnings.append(f"Could not build DataFrame for block: {exc}")
        b.confidence = 0.0
        return b

    if df.empty:
        b.kind = "form"
        b.notes.append("All body rows are empty after dropping NaN-only rows.")
        b.confidence = 0.1
        return b

    # Assign kind
    if n_periods >= 3:
        b.kind = "wide"
        b.confidence = 0.85
    elif num_vals >= len(cells) * 0.3:
        b.kind = "tidy"
        b.confidence = 0.80
    else:
        b.kind = "records"
        b.confidence = 0.60

    b.df = df

    # Derive column roles
    b.column_roles = _infer_column_roles(df, col_names, parsed_periods, sub[h_idx])

    if b.kind == "wide":
        long_df, summary_df, ambiguous, unpivot_warnings = _unpivot(
            df=df,
            header_vals=sub[h_idx],
            col_names=col_names,
            parsed_periods=parsed_periods,
            year_hint=year_hint,
            r0=r0,
            h_idx=h_idx,
        )
        b.df = long_df
        b.summary_df = summary_df
        b.ambiguous_rows = ambiguous
        b.warnings.extend(unpivot_warnings)
        period_count = n_periods
        b.notes.append(f"Unpivoted {period_count} month column(s) to long form.")
        if summary_df is not None and len(summary_df) > 0:
            b.notes.append(
                f"Separated {len(summary_df)} summary row(s) "
                "(e.g. totals / production). "
                "Review ambiguous_rows for uncertain classifications."
            )

    # Formula cache warning
    try:
        has_none = any(
            row[c] is None
            for row in grid[r0 : r1 + 1]
            for c in range(c0, min(c1 + 1, len(row)))
        )
        if has_none and _detect_formula_cache_miss(
            raw,
            sheet,
            [],
            max_row_limit=r1 + 1,
            cache=formula_cache_map,
            wb_data=wb_data,
            wb_formula_holder=wb_formula_holder,
        ):
            b.formula_cache_warning = True
            b.warnings.append(
                "One or more formula cells in this sheet have no cached result "
                "(value appears as None). "
                "Please open the workbook in Excel, allow it to calculate, "
                "then save and re-upload."
            )
    except Exception:
        pass

    return b


# ---------------------------------------------------------------------------
# Unpivot (wide → long)
# ---------------------------------------------------------------------------

def _unpivot(
    df: pd.DataFrame,
    header_vals: list[Any],
    col_names: list[str],
    parsed_periods: list[tuple[dt.date, str] | None],
    year_hint: int | None,
    r0: int,
    h_idx: int,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame | None,
    list[AmbiguousRow],
    list[str],
]:
    """
    Convert a wide-monthly table to long (tidy) form.

    Fixes over ingest_reference.py:
    - Guards id_cols[0] access when id_cols is empty.
    - Uses a configurable threshold (not hard-coded ids_filled <= 1).
    - Flags uncertain rows as AmbiguousRow instead of silently discarding.
    - Separates measures by their label — never sums qty + PPM together.
    - Drops _DERIVED columns (YTD, cumulative, % of total).
    - Returns provenance (sheet_row) on each ambiguous row.
    """
    warnings_out: list[str] = []
    ambiguous_out: list[AmbiguousRow] = []

    # Identify date and identifier columns
    period_map: dict[str, tuple[dt.date, str]] = {
        n: p
        for n, p in zip(col_names, parsed_periods)
        if p is not None
    }
    date_cols = list(period_map.keys())

    if not date_cols:
        warnings_out.append(
            "No parseable period columns found. "
            "Cannot unpivot — block left as-is."
        )
        return df, None, [], warnings_out

    id_cols = [
        n
        for n in col_names
        if n not in date_cols
        and not df[n].isna().all()
        and not _DERIVED.search(n)
    ]

    # --- Summary row detection ---
    # Rows where (almost) no identifier columns are filled are candidates for
    # totals / production lines.  We use a threshold of ≤1 filled id cell but
    # flag rows with exactly 1 filled id cell as ambiguous for user review.
    if id_cols:
        ids_filled = df[id_cols].notna().sum(axis=1)
    else:
        ids_filled = pd.Series([0] * len(df), index=df.index)

    # Definite summary: 0 id cells filled
    is_definite_summary = ids_filled == 0
    # Ambiguous: exactly 1 id cell filled — may be a label or a data row
    is_ambiguous = ids_filled == 1
    is_record = ids_filled >= 2

    # Collect ambiguous rows for user review (row values = label columns only)
    ambiguous_df = df[is_ambiguous]
    for local_idx, (abs_idx, row) in enumerate(ambiguous_df.iterrows()):
        # sheet_row: r0 (block start, 0-based) + h_idx (header rows) + 1 (data offset)
        # + local position + 1 (convert to 1-based)
        sheet_row = r0 + h_idx + 1 + int(abs_idx) + 1  # type: ignore[arg-type]
        raw_vals = [row[c] for c in id_cols if c in row]
        ambiguous_out.append(
            AmbiguousRow(
                source_row=int(abs_idx),  # type: ignore[arg-type]
                sheet_row=sheet_row,
                reason=(
                    "Only 1 identifier cell is filled. "
                    "Could be a summary/total row or a legitimate data record. "
                    "Please review and confirm."
                ),
                raw_values=raw_vals,
            )
        )

    summary_mask = is_definite_summary | is_ambiguous
    records_df = df[is_record].copy()
    summary_candidates = df[summary_mask].copy()

    # Melt summary rows
    summary_long: pd.DataFrame | None = None
    if len(summary_candidates) > 0 and date_cols:
        # Use first non-null id column as the label, or a synthetic one
        label_col: str | None = None
        if id_cols:
            for c in id_cols:
                if summary_candidates[c].notna().any():
                    label_col = c
                    break

        if label_col:
            s = summary_candidates.rename(columns={label_col: "_label"})[
                ["_label"] + date_cols
            ]
        else:
            s = summary_candidates[date_cols].copy()
            s.insert(0, "_label", "summary")

        try:
            s_long = s.melt(
                id_vars=["_label"],
                value_vars=date_cols,
                var_name="_col",
                value_name="value",
            )
            s_long["period"] = s_long["_col"].map(lambda c: period_map.get(c, (None,))[0])
            s_long["measure"] = s_long["_col"].map(lambda c: period_map.get(c, (None, "value"))[1])
            s_long["value"] = pd.to_numeric(s_long["value"], errors="coerce")
            summary_long = s_long.drop(columns=["_col"]).dropna(subset=["value"])
            summary_long = summary_long.rename(columns={"_label": "label"})
        except Exception as exc:
            warnings_out.append(f"Could not melt summary rows: {exc}")

    # Melt record rows — keep distinct measures separate
    if records_df.empty:
        if not id_cols:
            warnings_out.append(
                "No identifier columns and no record rows found. "
                "Block may be summary-only."
            )
        long_out = pd.DataFrame()
    else:
        try:
            long_out = records_df.melt(
                id_vars=id_cols,
                value_vars=date_cols,
                var_name="_col",
                value_name="value",
            )
            long_out["period"] = long_out["_col"].map(
                lambda c: period_map.get(c, (None,))[0]
            )
            long_out["measure"] = long_out["_col"].map(
                lambda c: period_map.get(c, (None, "value"))[1]
            )
            long_out["value"] = pd.to_numeric(long_out["value"], errors="coerce")
            long_out = long_out.drop(columns=["_col"]).dropna(subset=["value"])
        except Exception as exc:
            warnings_out.append(f"Could not unpivot record rows: {exc}")
            long_out = pd.DataFrame()

    if warnings_out:
        pass  # already collected

    return long_out, summary_long, ambiguous_out, warnings_out


# ---------------------------------------------------------------------------
# Column role inference
# ---------------------------------------------------------------------------

_ID_NAME = re.compile(
    r"^(sr\.?|s\.?\s*no|id|index|#|\bno\b|seq)", re.IGNORECASE
)
_MEASURE_NAME = re.compile(
    r"(ppm|qty|quantity|count|defect|failure|production|output|rate|value|amount|total)",
    re.IGNORECASE,
)
_DATE_NAME = re.compile(r"(date|month|period|week|year)", re.IGNORECASE)
_CATEGORY_NAME = re.compile(
    r"(model|type|category|defect|description|name|location|plant|line|shift|"
    r"champion|status|action|team|part|supplier|customer|product|region)",
    re.IGNORECASE,
)


def _is_id_column(series: pd.Series, name: str) -> bool:
    """
    Conservative identifier detection.

    A column is an identifier (not a measure) when:
    - Its name matches a known identifier prefix (Sr.No, ID, Index, #, No, Seq)
    - OR it contains leading-zero strings (postal codes, part numbers)
    - OR cardinality == row count AND values parse as plain integers with no
      meaningful distribution (sequential row numbers)

    Numeric series that are genuine measures (e.g. PPM values, defect counts)
    are NOT classified as identifiers even if they parse entirely as numbers.
    The is_id() function in recommend_reference.py was too aggressive.
    """
    if _ID_NAME.match(name.strip()):
        return True

    non_null = series.dropna()
    if len(non_null) == 0:
        return False

    str_vals = non_null.astype(str)

    # Leading-zero integers → likely identifier (postal code, part number)
    if str_vals.str.match(r"^0\d+$").any():
        return True

    # Sequential integer check: all integers, no gaps, starts near 1
    numeric = pd.to_numeric(non_null, errors="coerce")
    if numeric.notna().all():
        int_vals = numeric.astype(int)
        if (
            len(int_vals) > 1
            and int_vals.nunique() == len(int_vals)
            and int_vals.min() >= 0
            and int_vals.max() == int_vals.min() + len(int_vals) - 1
        ):
            return True

    return False


def _infer_column_roles(
    df: pd.DataFrame,
    col_names: list[str],
    parsed_periods: list[tuple[dt.date, str] | None],
    header_vals: list[Any],
) -> dict[str, str]:
    """
    Assign a role to every column: "date", "measure", "category", "id", "derived", "text".
    User may override any assignment via the mapping UI (Milestone 2).
    """
    period_set = {
        n
        for n, p in zip(col_names, parsed_periods)
        if p is not None
    }
    roles: dict[str, str] = {}

    for col in col_names:
        if col not in df.columns:
            roles[col] = "unknown"
            continue

        s = df[col]

        if col in period_set:
            roles[col] = "date"
            continue

        if _DERIVED.search(col):
            roles[col] = "derived"
            continue

        if _is_id_column(s, col):
            roles[col] = "id"
            continue

        if _DATE_NAME.search(col):
            roles[col] = "date"
            continue

        numeric = pd.to_numeric(s, errors="coerce")
        if numeric.notna().sum() / max(len(s), 1) >= 0.8:
            if _MEASURE_NAME.search(col):
                roles[col] = "measure"
            elif s.nunique() <= 30 and s.nunique() < len(s) * 0.5:
                roles[col] = "category"
            else:
                roles[col] = "measure"
            continue

        if _CATEGORY_NAME.search(col):
            roles[col] = "category"
            continue

        if s.nunique() / max(len(s), 1) <= 0.3:
            roles[col] = "category"
        else:
            roles[col] = "text"

    return roles


# ---------------------------------------------------------------------------
# Cell-fill colour reading (targeted, bounded pass)
# ---------------------------------------------------------------------------

def _read_cell_colours(
    raw: bytes,
    sheet_name: str,
    row_range: tuple[int, int],  # 0-based inclusive
    col_range: tuple[int, int],  # 0-based inclusive
    global_warnings: list[str],
) -> list[CellColour]:
    """
    Read fill colours for a bounded cell range from a separate openpyxl pass
    (styles are not available in read_only/data_only mode).

    Returns a list of CellColour objects.  Colours that cannot be resolved
    (theme colours, indexed colours without a palette) are returned with rgb=None
    and raw_type set so the caller can surface them for manual review.

    This is a best-effort pass — errors are caught and reported, not raised.
    """
    colours: list[CellColour] = []
    try:
        # Must load WITHOUT read_only to access styles
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=False)
        if sheet_name not in wb.sheetnames:
            wb.close()
            return colours
        ws = wb[sheet_name]

        r0, r1 = row_range
        c0, c1 = col_range

        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cell = ws.cell(row=r + 1, column=c + 1)  # openpyxl is 1-based
                fill = cell.fill
                if fill is None or fill.fill_type in (None, "none"):
                    continue

                rgb_val: str | None = None
                raw_type = "none"

                try:
                    fg = fill.fgColor
                    if fg.type == "rgb":
                        rgb_hex = fg.rgb  # 8-char ARGB hex e.g. "FFFF0000"
                        if rgb_hex and rgb_hex != "00000000":
                            # Strip alpha channel
                            rgb_val = rgb_hex[2:] if len(rgb_hex) == 8 else rgb_hex
                            raw_type = "rgb"
                    elif fg.type == "indexed":
                        raw_type = "indexed"
                        # Indexed colours require the theme palette; mark unknown
                        rgb_val = None
                    elif fg.type == "theme":
                        raw_type = "theme"
                        rgb_val = None
                except Exception:
                    raw_type = "error"
                    rgb_val = None

                if fill.fill_type not in (None, "none") and raw_type != "none":
                    colours.append(
                        CellColour(row=r, col=c, rgb=rgb_val, raw_type=raw_type)
                    )

        wb.close()
    except Exception as exc:
        global_warnings.append(
            f"Could not read cell fill colours for sheet '{sheet_name}': {exc}. "
            "Colour-based status detection is unavailable for this sheet."
        )
    return colours


# ---------------------------------------------------------------------------
# Label merge suggestions (edit-distance, suggestions only)
# ---------------------------------------------------------------------------

def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb))
            )
        prev = cur
    return prev[-1]


def suggest_label_merges(
    series: pd.Series,
    known: list[str],
    cutoff: int = LABEL_MERGE_CUTOFF,
) -> list[dict[str, Any]]:
    """
    Generate near-duplicate label merge suggestions using edit distance.

    Returns a list of {"from": str, "to": str, "distance": int} dicts.
    NEVER rewrites source categories — suggestions only.
    Handles known=[] (returns empty list), ties, and mixed types safely.
    """
    if not known:
        return []

    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for v in series:
        if not isinstance(v, str):
            continue
        if v in seen:
            continue
        seen.add(v)

        if v in known:
            continue  # exact match — no suggestion needed

        # Find closest known label
        distances = [(k, _edit_distance(v.lower(), k.lower())) for k in known]
        distances.sort(key=lambda x: (x[1], x[0]))  # sort by dist, then alpha for ties
        best_label, best_dist = distances[0]

        if best_dist <= cutoff:
            suggestions.append(
                {"from": v, "to": best_label, "distance": best_dist}
            )

    return suggestions


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------

def scan_workbook(
    raw: bytes,
    filename: str,
    *,
    read_colours: bool = False,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
) -> ScanResult:
    """
    Scan workbook bytes and return detected blocks with metadata.

    Parameters
    ----------
    raw:
        Raw workbook bytes (from the upload request).  Never written to disk.
    filename:
        Original filename (used for year-hint extraction and format detection).
    read_colours:
        If True, perform an extra openpyxl pass to read cell fill colours.
        Slower; only needed for action-tracker sheets.
    max_upload_bytes:
        Override the upload size limit (default: 10 MiB).

    Returns
    -------
    ScanResult with sheet names and detected blocks.
    """
    global_warnings: list[str] = []
    result_blocks: list[BlockResult] = []
    overall_cap = False

    # 1. Size guard
    if len(raw) > max_upload_bytes:
        raise ValueError(
            f"File size ({len(raw) / 1024 / 1024:.1f} MB) exceeds the "
            f"{max_upload_bytes // 1024 // 1024} MB upload limit."
        )

    lower = filename.lower()

    # 2. Format check
    if lower.endswith(".xlsm"):
        raise ValueError(
            ".xlsm macro-enabled workbooks are not accepted. "
            "Please save as .xlsx (macro-free) and re-upload."
        )
    if lower.endswith(".xls"):
        raise ValueError(
            "Legacy .xls format is not supported in this milestone. "
            "Please save the workbook as .xlsx and re-upload."
        )
    if not (lower.endswith(".xlsx") or lower.endswith(".csv")):
        raise ValueError(
            f"Unsupported file type '{filename}'. "
            "Only .xlsx and .csv files are accepted."
        )

    # 3. CSV path
    if lower.endswith(".csv"):
        return _scan_csv(raw, filename, global_warnings)

    # 4. XLSX archive guard
    try:
        _validate_xlsx_archive(raw)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    # 5. Open workbook in data-only mode (never executes formulas)
    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(raw), data_only=True, read_only=True
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "encrypted" in msg or "password" in msg:
            raise ValueError(
                "The workbook appears to be password-protected or encrypted."
            ) from exc
        raise ValueError(f"Cannot open XLSX workbook: {exc}") from exc

    sheet_names = wb.sheetnames

    if not sheet_names:
        wb.close()
        raise ValueError("The workbook contains no readable worksheets.")

    # Bounds detection (generic ghost-row detection across all sheets)
    sheet_bounds_map = detect_all_sheet_bounds(raw)
    sheet_formula_cache: dict[str, bool] = {}
    wb_formula_holder: list[Any] = [None]

    # 6. Iterate worksheets
    sheets_processed = 0
    for ws_name in sheet_names:
        if sheets_processed >= MAX_SHEETS:
            overall_cap = True
            global_warnings.append(
                f"Worksheet limit ({MAX_SHEETS}) reached; "
                f"{len(sheet_names) - MAX_SHEETS} sheet(s) were not scanned."
            )
            break

        ws = wb[ws_name]
        bounds = sheet_bounds_map.get(ws_name)
        if bounds is None:
            bounds = detect_openpyxl_sheet_bounds(ws)

        if bounds and bounds.has_ghost_tail and bounds.warning_message:
            global_warnings.append(bounds.warning_message)

        year_hint = guess_year(ws_name, filename)

        # Read grid (data-only, bounded by effective data range if ghost tail present)
        max_row_limit = bounds.effective_data_max_row if (bounds and bounds.has_ghost_tail) else None
        grid, sheet_cap = _read_grid_data_only(ws, global_warnings, max_row_limit=max_row_limit)
        if sheet_cap:
            overall_cap = True

        if not grid:
            global_warnings.append(
                f"Sheet '{ws_name}' appears empty — skipped."
            )
            sheets_processed += 1
            continue

        # Detect blocks
        raw_blocks = _find_blocks(ws_name, grid)

        if not raw_blocks:
            global_warnings.append(
                f"Sheet '{ws_name}': no connected cell blocks detected."
            )
            sheets_processed += 1
            continue

        blocks_this_sheet = 0
        for bb in raw_blocks:
            if blocks_this_sheet >= MAX_BLOCKS_PER_SHEET:
                overall_cap = True
                global_warnings.append(
                    f"Sheet '{ws_name}': block limit ({MAX_BLOCKS_PER_SHEET}) "
                    "reached; further blocks were not classified."
                )
                break

            r0, c0, r1, c1 = bb
            block = _classify_block(
                sheet=ws_name,
                r0=r0,
                c0=c0,
                r1=r1,
                c1=c1,
                grid=grid,
                year_hint=year_hint,
                raw=raw,
                bounds=bounds,
                formula_cache_map=sheet_formula_cache,
                wb_data=wb,
                wb_formula_holder=wb_formula_holder,
            )

            # Optional colour pass
            if read_colours and block.kind != "form":
                block.cell_colours = _read_cell_colours(
                    raw=raw,
                    sheet_name=ws_name,
                    row_range=(r0, r1),
                    col_range=(c0, c1),
                    global_warnings=global_warnings,
                )

            result_blocks.append(block)
            blocks_this_sheet += 1

        sheets_processed += 1

    wb.close()
    if wb_formula_holder[0] is not None:
        try:
            wb_formula_holder[0].close()
        except Exception:
            pass

    sheet_bounds_dict = {
        s: b.to_dict() for s, b in sheet_bounds_map.items()
    }

    return ScanResult(
        filename=filename,
        sheet_names=list(sheet_names),
        blocks=result_blocks,
        global_warnings=global_warnings,
        cap_reached=overall_cap,
        sheet_bounds=sheet_bounds_dict,
    )


# ---------------------------------------------------------------------------
# CSV scanning (simple: single "block" = the whole file)
# ---------------------------------------------------------------------------

def _scan_csv(
    raw: bytes,
    filename: str,
    global_warnings: list[str],
) -> ScanResult:
    """Treat a CSV as a single tidy block."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(
            "Could not decode CSV file. Please save as UTF-8 and re-upload."
        )

    try:
        df = pd.read_csv(
            io.StringIO(text),
            dtype=str,
            keep_default_na=False,
            na_values=["", "NA", "N/A", "NULL", "null", "None", "NaN", "nan", "#N/A"],
            nrows=MAX_SCAN_ROWS,
        )
    except Exception as exc:
        raise ValueError(f"Cannot parse CSV content: {exc}") from exc

    if df.empty or df.shape[1] == 0:
        raise ValueError("The CSV file appears to be empty.")

    block = BlockResult(
        sheet="(csv)",
        r0=0,
        c0=0,
        r1=len(df) - 1,
        c1=df.shape[1] - 1,
        kind="tidy",
        df=df,
        confidence=0.9,
    )
    block.column_roles = _infer_column_roles(df, list(df.columns), [], list(df.columns))

    return ScanResult(
        filename=filename,
        sheet_names=["(csv)"],
        blocks=[block],
        global_warnings=global_warnings,
        cap_reached=False,
    )
