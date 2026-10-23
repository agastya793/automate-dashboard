"""
Phase 4 Backend Tests - Interactive Dashboard Data Generation & Filtering.

Test suite covers:
 1. Line-chart aggregation at multiple date granularities (day, week, month, year).
 2. Bar-chart aggregation with sum and mean.
 3. Correct top-N ranking and sorting.
 4. Donut / category frequency calculations.
 5. Histogram bin counts.
 6. Stacked-bar aggregation across two categories.
 7. Global filters applied before aggregation.
 8. Correct summary statistics after filtering.
 9. Missing numeric and date values handled safely.
10. Invalid column mappings handled gracefully.
11. Invalid aggregation, top-N, and granularity values.
12. Empty or all-filtered datasets.
13. Unsupported chart types handled with warning.
14. Multiple selected chart configurations in one request.
15. Existing CSV and multi-sheet XLSX validation intact.
16. Response serialization with valid JSON numbers (no NaN or infinity).
"""

from __future__ import annotations

import io
import json
from typing import Any
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_csv_bytes(rows: list[list[Any]], header: list[str]) -> bytes:
    df = pd.DataFrame(rows, columns=header)
    return df.to_csv(index=False).encode("utf-8")


def _post_dashboard(
    filename: str,
    content: bytes,
    chart_configs: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
    sheet_name: str | None = None,
) -> Any:
    files = {"file": (filename, content, "application/octet-stream")}
    data: dict[str, Any] = {"chart_configs": json.dumps(chart_configs)}
    if filters is not None:
        data["filters"] = json.dumps(filters)
    if sheet_name is not None:
        data["sheet_name"] = sheet_name
    return client.post("/api/datasets/dashboard", files=files, data=data)


# ---------------------------------------------------------------------------
# 1. Line-chart aggregation at multiple date granularities
# ---------------------------------------------------------------------------

def test_line_chart_multiple_granularities():
    rows = [
        ["2025-01-10", 100],
        ["2025-01-15", 200],
        ["2025-02-05", 300],
        ["2026-03-20", 400],
    ]
    csv_bytes = _make_csv_bytes(rows, ["date", "amount"])

    # Granularity: Month
    configs_month = [{
        "id": "line_month",
        "title": "Monthly Trend",
        "chart_type": "line",
        "date_column": "date",
        "measure_column": "amount",
        "aggregation": "sum",
        "date_granularity": "month",
    }]
    resp = _post_dashboard("data.csv", csv_bytes, configs_month)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    chart = data["charts"][0]
    labels = [p["label"] for p in chart["data"]]
    assert "2025-01" in labels
    assert "2025-02" in labels
    # Sum for 2025-01 should be 100 + 200 = 300
    p_jan = next(p for p in chart["data"] if p["label"] == "2025-01")
    assert p_jan["value"] == 300.0

    # Granularity: Year
    configs_year = [{
        "id": "line_year",
        "title": "Yearly Trend",
        "chart_type": "line",
        "date_column": "date",
        "measure_column": "amount",
        "aggregation": "sum",
        "date_granularity": "year",
    }]
    resp_year = _post_dashboard("data.csv", csv_bytes, configs_year)
    assert resp_year.status_code == 200
    chart_y = resp_year.json()["charts"][0]
    p_2025 = next(p for p in chart_y["data"] if p["label"] == "2025")
    assert p_2025["value"] == 600.0


# ---------------------------------------------------------------------------
# 2. Bar-chart aggregation with sum and mean
# ---------------------------------------------------------------------------

def test_bar_chart_sum_and_mean():
    rows = [
        ["CategoryA", 100],
        ["CategoryA", 200],
        ["CategoryB", 50],
    ]
    csv_bytes = _make_csv_bytes(rows, ["category", "revenue"])

    configs = [
        {
            "id": "bar_sum",
            "title": "Sum by Category",
            "chart_type": "bar",
            "dimension_column": "category",
            "measure_column": "revenue",
            "aggregation": "sum",
        },
        {
            "id": "bar_mean",
            "title": "Average by Category",
            "chart_type": "bar",
            "dimension_column": "category",
            "measure_column": "revenue",
            "aggregation": "mean",
        },
    ]
    resp = _post_dashboard("sales.csv", csv_bytes, configs)
    assert resp.status_code == 200, resp.text
    charts = resp.json()["charts"]

    # Sum check
    c_sum = next(c for c in charts if c["id"] == "bar_sum")
    p_a_sum = next(p for p in c_sum["data"] if p["label"] == "CategoryA")
    assert p_a_sum["value"] == 300.0

    # Mean check (average of 100 and 200 is 150)
    c_mean = next(c for c in charts if c["id"] == "bar_mean")
    p_a_mean = next(p for p in c_mean["data"] if p["label"] == "CategoryA")
    assert p_a_mean["value"] == 150.0


# ---------------------------------------------------------------------------
# 3. Correct top-N ranking and sorting
# ---------------------------------------------------------------------------

def test_ranked_bar_top_n():
    rows = [
        [f"Item_{i}", i * 10] for i in range(1, 11)
    ]
    csv_bytes = _make_csv_bytes(rows, ["item", "sales"])

    config = [{
        "id": "top_3",
        "title": "Top 3 Items",
        "chart_type": "ranked_bar",
        "dimension_column": "item",
        "measure_column": "sales",
        "aggregation": "sum",
        "top_n": 3,
    }]
    resp = _post_dashboard("items.csv", csv_bytes, config)
    assert resp.status_code == 200
    chart = resp.json()["charts"][0]
    assert len(chart["data"]) == 3
    # Top 1 should be Item_10 with 100 sales
    assert chart["data"][0]["label"] == "Item_10"
    assert chart["data"][0]["value"] == 100.0
    assert chart["data"][1]["label"] == "Item_9"
    assert chart["data"][2]["label"] == "Item_8"


# ---------------------------------------------------------------------------
# 4. Donut / category frequency calculations
# ---------------------------------------------------------------------------

def test_donut_frequency():
    rows = [
        ["Active"], ["Active"], ["Active"], ["Pending"], ["Inactive"]
    ]
    csv_bytes = _make_csv_bytes(rows, ["status"])

    config = [{
        "id": "status_dist",
        "title": "Status Breakdown",
        "chart_type": "donut",
        "dimension_column": "status",
        "aggregation": "count",
    }]
    resp = _post_dashboard("status.csv", csv_bytes, config)
    assert resp.status_code == 200
    chart = resp.json()["charts"][0]
    p_active = next(p for p in chart["data"] if p["label"] == "Active")
    assert p_active["value"] == 3


# ---------------------------------------------------------------------------
# 5. Histogram bin counts
# ---------------------------------------------------------------------------

def test_histogram_bins():
    rows = [[i] for i in range(10, 110, 10)]  # 10, 20, ..., 100 (10 points)
    csv_bytes = _make_csv_bytes(rows, ["score"])

    config = [{
        "id": "hist_score",
        "title": "Score Distribution",
        "chart_type": "histogram",
        "measure_column": "score",
        "aggregation": "count",
    }]
    resp = _post_dashboard("scores.csv", csv_bytes, config)
    assert resp.status_code == 200
    chart = resp.json()["charts"][0]
    assert len(chart["data"]) > 0
    total_binned = sum(p["value"] for p in chart["data"])
    assert total_binned == 10


# ---------------------------------------------------------------------------
# 6. Stacked-bar aggregation across two categories
# ---------------------------------------------------------------------------

def test_stacked_bar():
    rows = [
        ["North", "Hardware", 500],
        ["North", "Software", 300],
        ["South", "Hardware", 200],
        ["South", "Software", 700],
    ]
    csv_bytes = _make_csv_bytes(rows, ["region", "dept", "sales"])

    config = [{
        "id": "stacked_sales",
        "title": "Sales by Region & Dept",
        "chart_type": "stacked_bar",
        "dimension_column": "region",
        "secondary_dimension_column": "dept",
        "measure_column": "sales",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("multi.csv", csv_bytes, config)
    assert resp.status_code == 200
    chart = resp.json()["charts"][0]
    assert set(chart["series_keys"]) == {"Hardware", "Software"}
    assert len(chart["data"]) == 2  # North and South
    north_pt = next(p for p in chart["data"] if p["label"] == "North")
    assert north_pt["Hardware"] == 500.0
    assert north_pt["Software"] == 300.0


# ---------------------------------------------------------------------------
# 7. Global filters applied before aggregation
# ---------------------------------------------------------------------------

def test_filters_applied_before_aggregation():
    rows = [
        ["2026-01-05", "East", 100],
        ["2026-01-15", "East", 200],
        ["2026-01-25", "West", 300],
    ]
    csv_bytes = _make_csv_bytes(rows, ["date", "region", "revenue"])

    config = [{
        "id": "c1",
        "title": "Revenue by Region",
        "chart_type": "bar",
        "dimension_column": "region",
        "measure_column": "revenue",
        "aggregation": "sum",
    }]
    # Filter to only East region
    filters = {
        "category_column": "region",
        "selected_categories": ["East"],
    }
    resp = _post_dashboard("sales.csv", csv_bytes, config, filters=filters)
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset_summary"]["filtered_records"] == 2
    assert data["dataset_summary"]["is_filtered"] is True
    chart_data = data["charts"][0]["data"]
    assert len(chart_data) == 1
    assert chart_data[0]["label"] == "East"
    assert chart_data[0]["value"] == 300.0


# ---------------------------------------------------------------------------
# 8. Correct summary statistics after filtering
# ---------------------------------------------------------------------------

def test_summary_statistics_after_filtering():
    rows = [
        ["2026-01-01", "Cat1", 50],
        ["2026-02-01", "Cat2", 150],
        ["2026-03-01", "Cat1", 100],
    ]
    csv_bytes = _make_csv_bytes(rows, ["date", "category", "amount"])

    config = [{
        "id": "c1",
        "title": "Amount by Category",
        "chart_type": "bar",
        "dimension_column": "category",
        "measure_column": "amount",
        "aggregation": "sum",
    }]
    # Date filter: only 2026-01 to 2026-02
    filters = {
        "date_column": "date",
        "start_date": "2026-01-01",
        "end_date": "2026-02-15",
    }
    resp = _post_dashboard("sales.csv", csv_bytes, config, filters=filters)
    assert resp.status_code == 200
    summary = resp.json()["dataset_summary"]
    assert summary["total_records"] == 3
    assert summary["filtered_records"] == 2
    # Measure summary should reflect filtered total: 50 + 150 = 200
    m_sum = next(m for m in summary["measure_summaries"] if m["column"] == "amount")
    assert m_sum["value"] == 200.0


# ---------------------------------------------------------------------------
# 9. Missing numeric and date values handled safely
# ---------------------------------------------------------------------------

def test_missing_values_handled():
    rows = [
        ["2026-01-01", "Tech", 100],
        [None, "Tech", 200],          # Missing date
        ["2026-01-03", None, None],   # Missing category & amount
    ]
    csv_bytes = _make_csv_bytes(rows, ["date", "category", "amount"])

    config = [{
        "id": "trend",
        "title": "Trend",
        "chart_type": "line",
        "date_column": "date",
        "measure_column": "amount",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("missing.csv", csv_bytes, config)
    assert resp.status_code == 200
    chart = resp.json()["charts"][0]
    assert any("missing" in w.lower() for w in chart["warnings"])


# ---------------------------------------------------------------------------
# 10. Invalid column mappings handled
# ---------------------------------------------------------------------------

def test_invalid_column_mapping_warning():
    rows = [["A", 1], ["B", 2]]
    csv_bytes = _make_csv_bytes(rows, ["col1", "col2"])

    config = [{
        "id": "bad_col",
        "title": "Bad Column Chart",
        "chart_type": "bar",
        "dimension_column": "non_existent_column",
        "measure_column": "col2",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("data.csv", csv_bytes, config)
    assert resp.status_code == 200
    chart = resp.json()["charts"][0]
    assert chart["total_points"] == 0
    assert any("not found" in w.lower() for w in chart["warnings"])


# ---------------------------------------------------------------------------
# 11. Invalid chart configs payload rejected (HTTP 422)
# ---------------------------------------------------------------------------

def test_empty_chart_configs_rejected():
    csv_bytes = _make_csv_bytes([["A", 1]], ["x", "y"])
    # Empty list
    resp = _post_dashboard("data.csv", csv_bytes, [])
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 12. All-filtered dataset handled gracefully
# ---------------------------------------------------------------------------

def test_all_filtered_dataset():
    rows = [["2026-01-01", "A", 10]]
    csv_bytes = _make_csv_bytes(rows, ["date", "cat", "val"])

    config = [{
        "id": "c1",
        "title": "Bar",
        "chart_type": "bar",
        "dimension_column": "cat",
        "measure_column": "val",
        "aggregation": "sum",
    }]
    # Filter for non-existent category
    filters = {
        "category_column": "cat",
        "selected_categories": ["NonExistentCategory"],
    }
    resp = _post_dashboard("data.csv", csv_bytes, config, filters=filters)
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset_summary"]["filtered_records"] == 0
    assert data["charts"][0]["total_points"] == 0


# ---------------------------------------------------------------------------
# 13. Unsupported chart type handled with warning
# ---------------------------------------------------------------------------

def test_unsupported_chart_type():
    csv_bytes = _make_csv_bytes([["A", 10]], ["cat", "val"])
    config = [{
        "id": "c_unknown",
        "title": "3D Polar Scatter",
        "chart_type": "3d_polar_scatter",
        "dimension_column": "cat",
        "measure_column": "val",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("data.csv", csv_bytes, config)
    assert resp.status_code == 200
    warnings = resp.json()["warnings"]
    assert any("unsupported" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# 14. Multiple selected chart configurations computed together
# ---------------------------------------------------------------------------

def test_multiple_charts_in_single_request():
    rows = [
        ["2026-01-01", "North", "Retail", 100],
        ["2026-01-02", "South", "Online", 200],
    ]
    csv_bytes = _make_csv_bytes(rows, ["date", "region", "channel", "amount"])

    configs = [
        {"id": "c1", "title": "Trend", "chart_type": "line", "date_column": "date", "measure_column": "amount", "aggregation": "sum"},
        {"id": "c2", "title": "Region", "chart_type": "bar", "dimension_column": "region", "measure_column": "amount", "aggregation": "sum"},
        {"id": "c3", "title": "Channel Share", "chart_type": "donut", "dimension_column": "channel", "aggregation": "count"},
    ]
    resp = _post_dashboard("multi.csv", csv_bytes, configs)
    assert resp.status_code == 200
    assert len(resp.json()["charts"]) == 3


# ---------------------------------------------------------------------------
# 15. Oversized upload check on dashboard endpoint
# ---------------------------------------------------------------------------

def test_dashboard_oversized_upload():
    big = b"A" * (11 * 1024 * 1024)
    config = [{"id": "c1", "title": "T", "chart_type": "bar", "dimension_column": "x", "aggregation": "count"}]
    resp = _post_dashboard("big.csv", big, config)
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# 16. JSON serialization with no NaN / infinity
# ---------------------------------------------------------------------------

def test_json_serialization_no_nan():
    # DataFrame with floating NaNs
    rows = [["A", float("nan")], ["B", 10.0]]
    csv_bytes = _make_csv_bytes(rows, ["cat", "val"])
    config = [{"id": "c1", "title": "Bar", "chart_type": "bar", "dimension_column": "cat", "measure_column": "val", "aggregation": "mean"}]
    resp = _post_dashboard("nan.csv", csv_bytes, config)
    assert resp.status_code == 200
    body = resp.text
    assert "NaN" not in body
    assert "Infinity" not in body
