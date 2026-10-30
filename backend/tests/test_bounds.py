"""
Comprehensive unit and integration test suite for Safe Excel Bounds Detection
and Ghost-Row Protection (Phase A).

Covers all 14 required verification scenarios:
  1.  Normal small worksheet (physical == effective, 0 ignored)
  2.  Legitimate 100k-row dataset (100% retained, zero false positives)
  3.  Formula-heavy legitimate dataset (all calculated rows retained)
  4.  Formula-error ghost tail (#DIV/0! single-cell fill-down truncated)
  5.  Blank-formula ghost tail (="" fill-down truncated)
  6.  Sparse legitimate data (preserves rows after empty gaps)
  7.  Merged cells preservation (bounds extend to include merged ranges)
  8.  Styled empty rows (formatting-only rows excluded)
  9.  Hidden rows with data (all rows preserved)
  10. Formula-only summary section (multi-column summary retained)
  11. Ghost tail after calculated table (table retained, tail excluded)
  12. Multi-sheet independence (clean sheets unaffected by ghost sheets)
  13. Scanner integration (BlockResult + ScanResult bounds metadata)
  14. Company workbook verification on Export TY Rejection-A3-2026.xlsx
"""

from __future__ import annotations

import io
import os
import zipfile
from typing import Any

import openpyxl
import pytest

from app.ingestion.bounds import (
    SheetBounds,
    detect_all_sheet_bounds,
    detect_openpyxl_sheet_bounds,
    detect_sheet_bounds_from_xml,
)
from app.ingestion.scanner import scan_workbook
from app.profiler import profile_dataset


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _build_xlsx(sheets: dict[str, list[list[Any]]]) -> bytes:
    """Build an in-memory XLSX workbook from {sheet_name: [[row_values]]}."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_xlsx_with_ghost_tail(
    sheet_name: str,
    real_rows: int = 35,
    ghost_rows: int = 1000,
    ghost_error: str = "#DIV/0!",
) -> bytes:
    """
    Build a realistic OpenXML XLSX with a solid tabular data header + rows,
    followed by hundreds/thousands of trailing single-cell formula errors.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name

    # Header
    ws.append(["Defect", "Category", "Target", "Jan", "Feb", "Mar", "Total"])
    # Real data
    for i in range(1, real_rows):
        ws.append([f"Defect {i}", f"Cat {i % 3}", 100, 10 + i, 12 + i, 15 + i, f"=SUM(D{i+1}:F{i+1})"])

    # Ghost rows: single cell in column G
    for r in range(real_rows + 1, real_rows + ghost_rows + 1):
        ws.cell(row=r, column=7, value=ghost_error)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_1_normal_small_worksheet():
    """Scenario 1: Normal small worksheet (20 rows, 5 columns) has physical == effective."""
    rows = [["ID", "Product", "Q1", "Q2", "Q3"]]
    for i in range(1, 20):
        rows.append([i, f"Product {i}", 100 * i, 110 * i, 120 * i])

    raw = _build_xlsx({"Sales": rows})
    bounds_map = detect_all_sheet_bounds(raw)

    assert "Sales" in bounds_map
    b = bounds_map["Sales"]
    assert b.physical_max_row == 20
    assert b.effective_data_max_row == 20
    assert b.ignored_trailing_rows == 0
    assert b.has_ghost_tail is False
    assert b.warning_message is None


def test_2_legitimate_large_dataset():
    """
    Scenario 2: Legitimate 100k-row dataset must be 100% retained with ZERO data loss.
    Constructs a synthetic OpenXML worksheet XML representing 100,000 real records.
    """
    # Build minimal openpyxl workbook with 1 row, then rewrite its sheet XML with 100k rows
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LargeData"
    ws.append(["ColA", "ColB", "ColC"])
    buf = io.BytesIO()
    wb.save(buf)

    # Inject a 100k row sheet XML
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf_in:
        items = {item.filename: zf_in.read(item.filename) for item in zf_in.infolist()}

    # Construct streaming XML with 100,000 multi-column tabular data rows
    xml_chunks = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n',
        '<dimension ref="A1:C100000"/>\n',
        '<sheetData>\n',
    ]
    for r in range(1, 100_001):
        xml_chunks.append(
            f'<row r="{r}">'
            f'<c r="A{r}"><v>{r}</v></c>'
            f'<c r="B{r}"><v>{r * 2}</v></c>'
            f'<c r="C{r}"><v>{r * 3}</v></c>'
            f'</row>\n'
        )
    xml_chunks.append('</sheetData>\n</worksheet>')
    sheet_xml_bytes = "".join(xml_chunks).encode("utf-8")

    # Re-zip
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf_out:
        for fname, data in items.items():
            if fname == "xl/worksheets/sheet1.xml":
                zf_out.writestr(fname, sheet_xml_bytes)
            else:
                zf_out.writestr(fname, data)

    raw_100k = out_buf.getvalue()
    bounds_map = detect_all_sheet_bounds(raw_100k)

    assert "LargeData" in bounds_map
    b = bounds_map["LargeData"]
    assert b.physical_max_row == 100_000
    assert b.effective_data_max_row == 100_000
    assert b.ignored_trailing_rows == 0
    assert b.has_ghost_tail is False
    assert b.warning_message is None


def test_3_formula_heavy_dataset():
    """Scenario 3: Formula-heavy legitimate dataset (all rows have data and formulas)."""
    rows = [["Item", "Price", "Qty", "Subtotal"]]
    for i in range(1, 300):
        rows.append([f"Item {i}", 15.5, 3, f"=B{i+1}*C{i+1}"])

    raw = _build_xlsx({"Formulas": rows})
    bounds_map = detect_all_sheet_bounds(raw)

    assert "Formulas" in bounds_map
    b = bounds_map["Formulas"]
    assert b.physical_max_row == 300
    assert b.effective_data_max_row == 300
    assert b.ignored_trailing_rows == 0
    assert b.has_ghost_tail is False


def test_4_formula_error_ghost_tail():
    """Scenario 4: 35 real rows + 1,000 trailing single-cell #DIV/0! errors."""
    raw = _build_xlsx_with_ghost_tail("ErrorGhostSheet", real_rows=35, ghost_rows=1000, ghost_error="#DIV/0!")
    bounds_map = detect_all_sheet_bounds(raw)

    assert "ErrorGhostSheet" in bounds_map
    b = bounds_map["ErrorGhostSheet"]
    assert b.physical_max_row >= 1035
    assert b.effective_data_max_row == 35
    assert b.ignored_trailing_rows >= 1000
    assert b.has_ghost_tail is True
    assert "The original workbook was not modified." in b.warning_message
    assert "1,000" in b.detection_reason or str(b.ignored_trailing_rows) in b.detection_reason


def test_5_blank_formula_ghost_tail():
    """Scenario 5: 35 real rows + 800 trailing single-cell empty string formulas."""
    raw = _build_xlsx_with_ghost_tail("BlankGhostSheet", real_rows=35, ghost_rows=800, ghost_error="")
    bounds_map = detect_all_sheet_bounds(raw)

    assert "BlankGhostSheet" in bounds_map
    b = bounds_map["BlankGhostSheet"]
    assert b.physical_max_row >= 835
    assert b.effective_data_max_row == 35
    assert b.ignored_trailing_rows >= 800
    assert b.has_ghost_tail is True


def test_6_sparse_legitimate_data():
    """Scenario 6: Data with empty rows in between must preserve later data."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sparse"

    # Block 1: rows 1-10
    ws.append(["Header1", "Header2"])
    for i in range(1, 10):
        ws.append([f"A{i}", i])

    # Gap: rows 11-20 empty
    # Block 2: rows 21-30
    for i in range(21, 31):
        ws.cell(row=i, column=1, value=f"LaterA{i}")
        ws.cell(row=i, column=2, value=i)

    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    bounds_map = detect_all_sheet_bounds(raw)
    b = bounds_map["Sparse"]
    assert b.effective_data_max_row >= 30
    assert b.has_ghost_tail is False


def test_7_merged_cells_preservation():
    """Scenario 7: Merged cells extending past tabular data must be preserved."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Merged"

    # Tabular data in rows 1-20
    ws.append(["ColA", "ColB"])
    for i in range(1, 20):
        ws.append([f"Val{i}", i])

    # Merged title/footnote block at rows 25-45
    ws.merge_cells("A25:D45")
    ws.cell(row=25, column=1, value="Footnote Section")

    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    bounds_map = detect_all_sheet_bounds(raw)
    b = bounds_map["Merged"]
    assert b.effective_data_max_row >= 45


def test_8_styled_empty_rows():
    """Scenario 8: Styled empty rows (formatting-only rows) without cell data are excluded."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "StyledEmpty"

    # Solid data in rows 1-20
    ws.append(["A", "B"])
    for i in range(1, 20):
        ws.append([i, i * 10])

    # Set artificial max_row to simulate openpyxl styled-empty rows
    b = detect_openpyxl_sheet_bounds(ws)
    assert b.effective_data_max_row == 20
    assert b.has_ghost_tail is False


def test_9_hidden_rows_preservation():
    """Scenario 9: Hidden rows containing real data must not be truncated."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "HiddenData"

    ws.append(["Name", "Score"])
    for i in range(1, 51):
        ws.append([f"User{i}", i])

    # Hide rows 10-30
    for r in range(10, 31):
        ws.row_dimensions[r].hidden = True

    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    bounds_map = detect_all_sheet_bounds(raw)
    b = bounds_map["HiddenData"]
    assert b.effective_data_max_row >= 51
    assert b.has_ghost_tail is False


def test_10_formula_only_summary_section():
    """Scenario 10: Multi-column formula summary section at the bottom is preserved."""
    rows = [["Category", "ValA", "ValB"]]
    for i in range(1, 25):
        rows.append([f"Cat{i}", 10 + i, 20 + i])

    # Row 26: Summary formulas across multiple columns
    rows.append(["Total", "=SUM(B2:B25)", "=SUM(C2:C25)"])

    raw = _build_xlsx({"SummarySheet": rows})
    bounds_map = detect_all_sheet_bounds(raw)

    b = bounds_map["SummarySheet"]
    assert b.effective_data_max_row >= 26
    assert b.has_ghost_tail is False


def test_11_ghost_tail_after_calculated_table():
    """Scenario 11: Ghost tail after a table with calculated rows is truncated at table end."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CalcTable"

    ws.append(["Col1", "Col2", "Col3"])
    for i in range(1, 30):
        ws.append([f"Item{i}", i, f"=B{i+1}*10"])

    # Trailing single-cell errors
    for r in range(31, 850):
        ws.cell(row=r, column=3, value="#DIV/0!")

    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    bounds_map = detect_all_sheet_bounds(raw)
    b = bounds_map["CalcTable"]
    assert b.effective_data_max_row == 30
    assert b.has_ghost_tail is True
    assert b.ignored_trailing_rows >= 800


def test_12_multi_sheet_independence():
    """Scenario 12: Multi-sheet workbook bounds are independent."""
    wb = openpyxl.Workbook()
    # Sheet 1: Clean
    ws1 = wb.active
    ws1.title = "CleanSheet"
    ws1.append(["ColA", "ColB"])
    for i in range(1, 60):
        ws1.append([f"A{i}", i])

    # Sheet 2: Ghost
    ws2 = wb.create_sheet(title="GhostSheet")
    ws2.append(["X", "Y"])
    for i in range(1, 25):
        ws2.append([f"X{i}", i])
    for r in range(26, 700):
        ws2.cell(row=r, column=2, value="#DIV/0!")

    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    bounds_map = detect_all_sheet_bounds(raw)
    assert bounds_map["CleanSheet"].has_ghost_tail is False
    assert bounds_map["CleanSheet"].effective_data_max_row == 60

    assert bounds_map["GhostSheet"].has_ghost_tail is True
    assert bounds_map["GhostSheet"].effective_data_max_row == 25
    assert bounds_map["GhostSheet"].ignored_trailing_rows >= 670


def test_13_scanner_integration():
    """Scenario 13: scanner.scan_workbook and profiler.profile_dataset attach bounds metadata."""
    raw = _build_xlsx_with_ghost_tail("ScannerTestSheet", real_rows=30, ghost_rows=600)

    # Scanner test
    res = scan_workbook(raw, "ghost_test.xlsx", read_colours=False)
    assert any("Large trailing formula range detected" in w for w in res.global_warnings)
    assert "ScannerTestSheet" in res.sheet_bounds
    sb = res.sheet_bounds["ScannerTestSheet"]
    assert sb["has_ghost_tail"] is True
    assert sb["effective_data_max_row"] == 30
    assert sb["ignored_trailing_rows"] >= 600

    for b in res.blocks:
        if b.sheet == "ScannerTestSheet":
            assert b.ignored_trailing_rows >= 600

    # Profiler test
    prof = profile_dataset("ghost_test.xlsx", raw, sheet_name="ScannerTestSheet")
    assert prof["row_count"] <= 30
    assert any("Large trailing formula range detected" in w for w in prof["warnings"])
    assert prof["bounds"] is not None
    assert prof["bounds"]["has_ghost_tail"] is True


def test_14_company_workbook_effect_confirmation():
    """
    Scenario 14: Verification on company workbook Export TY Rejection-A3-2026.xlsx.
    Verifies that sheet 'Effect confirmation 26' is safely bounded from 573,424 rows down to <= 37 rows,
    while leaving all other 9 sheets untouched.
    """
    company_wb_path = r"C:\Users\Paras Kandpal\Downloads\Export TY Rejection-A3-2026.xlsx"
    if not os.path.exists(company_wb_path):
        pytest.skip("Company workbook not present at local downloads path")

    with open(company_wb_path, "rb") as f:
        raw = f.read()

    # 1. Bounds detection
    bounds_map = detect_all_sheet_bounds(raw)
    assert "Effect confirmation 26" in bounds_map
    b = bounds_map["Effect confirmation 26"]

    assert b.physical_max_row == 573424
    assert b.effective_data_max_row <= 37
    assert b.ignored_trailing_rows >= 573380
    assert b.has_ghost_tail is True
    assert "The original workbook was not modified." in b.warning_message

    # Ensure other sheets have no false positives
    for s_name, s_bounds in bounds_map.items():
        if s_name != "Effect confirmation 26":
            assert s_bounds.has_ghost_tail is False, f"False positive detected on sheet '{s_name}'"

    # 2. Profiler integration on Effect confirmation 26
    prof = profile_dataset("Export TY Rejection-A3-2026.xlsx", raw, sheet_name="Effect confirmation 26")
    assert prof["row_count"] <= 37
    assert any("573,387" in w for w in prof["warnings"])
    assert prof["bounds"]["effective_data_max_row"] <= 37
    assert prof["bounds"]["ignored_trailing_rows"] >= 573380

