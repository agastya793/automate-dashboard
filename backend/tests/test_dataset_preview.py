"""
Phase 2 backend tests — dataset upload and profiling.

Run from the `backend` directory with the venv activated:
    pytest tests/test_dataset_preview.py -v

Test coverage:
 1. Valid CSV file (UTF-8)
 2. Valid XLSX with multiple worksheets
 3. Select a non-default worksheet
 4. Empty file
 5. Unsupported file extension (.xls)
 6. Malformed workbook (invalid bytes disguised as XLSX)
 7. Oversized upload (>10 MB limit)
 8. Row limit exceeded (>50 000 rows)
 9. Column limit exceeded (>100 columns)
10. Missing values and duplicate rows
11. Invalid worksheet name
12. UTF-8-BOM CSV
13. CSV with undecodable bytes
14. /health endpoint still works
"""

from __future__ import annotations

import io
import os
import zipfile
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Override limits to small values for fast tests
os.environ.setdefault("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
os.environ.setdefault("MAX_DATA_ROWS", "50000")
os.environ.setdefault("MAX_COLUMNS", "100")
os.environ.setdefault("MAX_PREVIEW_ROWS", "20")

from app.main import app  # noqa: E402 — must come after env setup

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_csv_bytes(rows: list[list[Any]], header: list[str] | None = None) -> bytes:
    df = pd.DataFrame(rows, columns=header or [f"col_{i}" for i in range(len(rows[0]))])
    return df.to_csv(index=False).encode("utf-8")


def _make_xlsx_bytes(
    sheets: dict[str, pd.DataFrame],
) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


def _upload(
    filename: str,
    content: bytes,
    sheet_name: str | None = None,
) -> Any:
    files = {"file": (filename, content, "application/octet-stream")}
    data = {}
    if sheet_name is not None:
        data["sheet_name"] = sheet_name
    return client.post("/api/datasets/preview", files=files, data=data)


# ---------------------------------------------------------------------------
# Test 1 — Valid CSV file
# ---------------------------------------------------------------------------

def test_valid_csv():
    content = _make_csv_bytes(
        rows=[[1, "Alice", "2024-01-15"], [2, "Bob", "2024-02-20"]],
        header=["id", "name", "date"],
    )
    resp = _upload("sample.csv", content)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_type"] == "csv"
    assert body["filename"] == "sample.csv"
    assert body["row_count"] == 2
    assert body["column_count"] == 3
    assert len(body["preview_rows"]) == 2
    assert body["sheet_names"] == []
    assert body["selected_sheet"] is None


# ---------------------------------------------------------------------------
# Test 2 — Valid XLSX with multiple worksheets (uses first sheet by default)
# ---------------------------------------------------------------------------

def test_valid_xlsx_multiple_sheets():
    df1 = pd.DataFrame({"product": ["A", "B"], "sales": [100, 200]})
    df2 = pd.DataFrame({"region": ["North", "South"], "revenue": [500, 600]})
    content = _make_xlsx_bytes({"Products": df1, "Regions": df2})
    resp = _upload("report.xlsx", content)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_type"] == "xlsx"
    assert set(body["sheet_names"]) == {"Products", "Regions"}
    assert body["selected_sheet"] == "Products"
    assert body["column_names"] == ["product", "sales"]


# ---------------------------------------------------------------------------
# Test 3 — Select a non-default worksheet
# ---------------------------------------------------------------------------

def test_select_non_default_sheet():
    df1 = pd.DataFrame({"a": [1, 2]})
    df2 = pd.DataFrame({"x": ["foo", "bar"], "y": [10, 20]})
    content = _make_xlsx_bytes({"Sheet1": df1, "Details": df2})
    resp = _upload("report.xlsx", content, sheet_name="Details")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["selected_sheet"] == "Details"
    assert body["column_names"] == ["x", "y"]
    assert body["row_count"] == 2


# ---------------------------------------------------------------------------
# Test 4 — Empty file
# ---------------------------------------------------------------------------

def test_empty_file():
    resp = _upload("empty.csv", b"")
    assert resp.status_code == 422, resp.text


def test_empty_xlsx():
    # A valid empty XLSX (header row only, no data rows)
    df = pd.DataFrame(columns=["col1", "col2"])
    content = _make_xlsx_bytes({"Sheet1": df})
    resp = _upload("empty.xlsx", content)
    # An empty DataFrame with headers — row_count == 0, column_count > 0
    # Our profiler raises MalformedFileError for df.empty → 422
    assert resp.status_code in (200, 422)


# ---------------------------------------------------------------------------
# Test 5 — Unsupported file extension (.xls)
# ---------------------------------------------------------------------------

def test_unsupported_extension_xls():
    resp = _upload("legacy.xls", b"not real content")
    assert resp.status_code == 415, resp.text
    assert ".xls" in resp.json()["detail"].lower() or "legacy" in resp.json()["detail"].lower() or "xls" in resp.json()["detail"].lower()


def test_unsupported_extension_pdf():
    resp = _upload("report.pdf", b"%PDF-1.4 content")
    assert resp.status_code == 415, resp.text


def test_unsupported_extension_xlsm():
    resp = _upload("macro.xlsm", b"fake content")
    assert resp.status_code == 415, resp.text


# ---------------------------------------------------------------------------
# Test 6 — Malformed workbook (random bytes with .xlsx extension)
# ---------------------------------------------------------------------------

def test_malformed_xlsx():
    resp = _upload("bad.xlsx", b"this is not a zip file at all")
    assert resp.status_code == 422, resp.text
    assert "zip" in resp.json()["detail"].lower() or "corrupt" in resp.json()["detail"].lower() or "cannot" in resp.json()["detail"].lower()


def test_malformed_xlsx_valid_zip_but_no_workbook():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("random.txt", "hello world")
    resp = _upload("bad.xlsx", buf.getvalue())
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Test 7 — Oversized upload
# ---------------------------------------------------------------------------

def test_oversized_upload():
    # 11 MB of zeros — exceeds 10 MB limit
    big = b"A" * (11 * 1024 * 1024)
    resp = _upload("big.csv", big)
    assert resp.status_code == 413, resp.text


# ---------------------------------------------------------------------------
# Test 8 — Row limit exceeded
# ---------------------------------------------------------------------------

def test_too_many_rows(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, "MAX_DATA_ROWS", 5)

    rows = [[i, f"name_{i}"] for i in range(10)]
    content = _make_csv_bytes(rows, header=["id", "name"])
    files = {"file": ("big_rows.csv", content, "application/octet-stream")}
    resp = client.post("/api/datasets/preview", files=files)
    assert resp.status_code == 422, resp.text
    assert "row" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 9 — Column limit exceeded
# ---------------------------------------------------------------------------

def test_too_many_columns(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, "MAX_COLUMNS", 3)

    header = [f"col_{i}" for i in range(10)]
    rows = [[f"val_{i}_{j}" for j in range(10)] for i in range(5)]
    content = _make_csv_bytes(rows, header=header)
    files = {"file": ("wide.csv", content, "application/octet-stream")}
    resp = client.post("/api/datasets/preview", files=files)
    assert resp.status_code == 422, resp.text
    assert "column" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 10 — Missing values and duplicate rows
# ---------------------------------------------------------------------------

def test_missing_values_and_duplicates():
    content = (
        "name,score,department\n"
        "Alice,95,Engineering\n"
        "Bob,,Engineering\n"     # missing score
        "Charlie,80,\n"          # missing department
        "Alice,95,Engineering\n" # duplicate of row 1
    ).encode("utf-8")
    resp = _upload("data.csv", content)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["duplicate_row_count"] == 1

    col_map = {c["name"]: c for c in body["columns"]}
    assert col_map["score"]["missing_count"] == 1
    assert col_map["department"]["missing_count"] == 1


# ---------------------------------------------------------------------------
# Test 11 — Invalid worksheet name
# ---------------------------------------------------------------------------

def test_invalid_sheet_name():
    df = pd.DataFrame({"x": [1, 2]})
    content = _make_xlsx_bytes({"Sheet1": df})
    resp = _upload("report.xlsx", content, sheet_name="DoesNotExist")
    assert resp.status_code == 422, resp.text
    assert "DoesNotExist" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 12 — UTF-8-BOM CSV
# ---------------------------------------------------------------------------

def test_utf8_bom_csv():
    # Write BOM-prefixed CSV
    content = "\ufeffname,value\nAlice,10\nBob,20\n".encode("utf-8-sig")
    resp = _upload("bom.csv", content)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # BOM should be stripped — column name should be 'name', not '\ufeffname'
    assert "name" in body["column_names"]
    assert "\ufeffname" not in body["column_names"]


# ---------------------------------------------------------------------------
# Test 13 — Undecodable CSV bytes
# ---------------------------------------------------------------------------

def test_undecodable_csv():
    # latin-1 encoded bytes that are not valid UTF-8
    content = "name,value\nAl\xefce,10\n".encode("latin-1")
    resp = _upload("latin.csv", content)
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Test 14 — /health endpoint still works
# ---------------------------------------------------------------------------

def test_health_endpoint_still_works():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "business-reporting-dashboard-api"
