"""
Tests for Phase 4 User-Controlled Custom Chart Creation & Validation.

Covers:
 1. Category + Numeric -> Bar
 2. Category + Numeric -> Pie
 3. Category + Numeric -> Donut
 4. Date + Numeric -> Line
 5. Category + Numeric -> Horizontal Bar
 6. Two categories + Numeric -> Stacked Bar
 7. Numeric -> Histogram
 8. Identifier cannot be SUMmed
 9. Text cannot be Histogram
10. Missing required dimension rejected
11. Missing measure rejected
12. Top 10 occurs after aggregation
13. Custom title preserved
14. Recommended chart customization still works
15. Existing Manufacturing Dashboard unaffected
"""

from __future__ import annotations

import json
from typing import Any
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dashboard import (
    ChartConfigInput,
    validate_chart_config,
    generate_dashboard_data,
)

client = TestClient(app)


def _make_csv_bytes(rows: list[list[Any]], header: list[str]) -> bytes:
    df = pd.DataFrame(rows, columns=header)
    return df.to_csv(index=False).encode("utf-8")


def _post_dashboard(
    filename: str,
    content: bytes,
    chart_configs: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
) -> Any:
    files = {"file": (filename, content, "application/octet-stream")}
    data: dict[str, Any] = {"chart_configs": json.dumps(chart_configs)}
    if filters is not None:
        data["filters"] = json.dumps(filters)
    return client.post("/api/datasets/dashboard", files=files, data=data)


# 1. Category + Numeric -> Bar
def test_category_numeric_bar():
    rows = [
        ["Lathe A", 45],
        ["Lathe B", 60],
        ["Mill C", 30],
    ]
    csv_bytes = _make_csv_bytes(rows, ["tool_type", "usage_hours"])
    config = [{
        "id": "c_bar",
        "title": "Usage Hours by Tool Type",
        "chart_type": "bar",
        "dimension_column": "tool_type",
        "measure_column": "usage_hours",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("tools.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    charts = resp.json()["charts"]
    assert len(charts) == 1
    assert charts[0]["chart_type"] == "bar"
    data_map = {p["label"]: p["value"] for p in charts[0]["data"]}
    assert data_map["Lathe A"] == 45.0
    assert data_map["Lathe B"] == 60.0
    assert data_map["Mill C"] == 30.0


# 2. Category + Numeric -> Pie
def test_category_numeric_pie():
    rows = [
        ["Operations", 5000],
        ["Logistics", 3000],
        ["Engineering", 2000],
    ]
    csv_bytes = _make_csv_bytes(rows, ["department", "budget"])
    config = [{
        "id": "c_pie",
        "title": "Budget Allocation by Department",
        "chart_type": "pie",
        "dimension_column": "department",
        "measure_column": "budget",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("dept.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    charts = resp.json()["charts"]
    assert len(charts) == 1
    assert charts[0]["chart_type"] == "pie"
    pts = charts[0]["data"]
    # Total is 10000; Operations should be 50%
    ops = next(p for p in pts if p["label"] == "Operations")
    assert ops["value"] == 5000.0
    assert ops["percentage"] == 50.0


# 3. Category + Numeric -> Donut
def test_category_numeric_donut():
    rows = [
        ["Assembly", 70],
        ["Packaging", 30],
    ]
    csv_bytes = _make_csv_bytes(rows, ["process", "scrap_count"])
    config = [{
        "id": "c_donut",
        "title": "Scrap Distribution",
        "chart_type": "donut",
        "dimension_column": "process",
        "measure_column": "scrap_count",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("scrap.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    assert chart["chart_type"] == "donut"
    pts = chart["data"]
    assy = next(p for p in pts if p["label"] == "Assembly")
    assert assy["value"] == 70.0
    assert assy["percentage"] == 70.0


# 4. Date + Numeric -> Line
def test_date_numeric_line():
    rows = [
        ["2026-01-01", 120],
        ["2026-01-15", 80],
        ["2026-02-01", 150],
    ]
    csv_bytes = _make_csv_bytes(rows, ["transaction_date", "volume"])
    config = [{
        "id": "c_line",
        "title": "Volume Over Time",
        "chart_type": "line",
        "date_column": "transaction_date",
        "measure_column": "volume",
        "aggregation": "sum",
        "date_granularity": "month",
    }]
    resp = _post_dashboard("timeline.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    assert chart["chart_type"] == "line"
    data_map = {p["label"]: p["value"] for p in chart["data"]}
    # Jan 2026 sum = 120 + 80 = 200
    assert data_map["2026-01"] == 200.0
    assert data_map["2026-02"] == 150.0


# 5. Category + Numeric -> Horizontal Bar
def test_category_numeric_horizontal_bar():
    rows = [
        ["Part X", 10],
        ["Part Y", 50],
        ["Part Z", 30],
    ]
    csv_bytes = _make_csv_bytes(rows, ["part_name", "defect_qty"])
    config = [{
        "id": "c_hbar",
        "title": "Top Defective Parts",
        "chart_type": "horizontal_bar",
        "dimension_column": "part_name",
        "measure_column": "defect_qty",
        "aggregation": "sum",
        "sort_order": "desc",
    }]
    resp = _post_dashboard("parts.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    assert chart["chart_type"] == "horizontal_bar"
    assert chart["data"][0]["label"] == "Part Y"
    assert chart["data"][0]["value"] == 50.0
    assert chart["data"][1]["label"] == "Part Z"
    assert chart["data"][2]["label"] == "Part X"


# 6. Two categories + Numeric -> Stacked Bar
def test_two_categories_numeric_stacked_bar():
    rows = [
        ["Shift 1", "Line A", 100],
        ["Shift 1", "Line B", 150],
        ["Shift 2", "Line A", 120],
        ["Shift 2", "Line B", 130],
    ]
    csv_bytes = _make_csv_bytes(rows, ["shift", "line", "output"])
    config = [{
        "id": "c_stacked",
        "title": "Output by Shift and Line",
        "chart_type": "stacked_bar",
        "dimension_column": "shift",
        "secondary_dimension_column": "line",
        "measure_column": "output",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("production.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    assert chart["chart_type"] == "stacked_bar"
    assert set(chart["series_keys"]) == {"Line A", "Line B"}
    s1 = next(p for p in chart["data"] if p["label"] == "Shift 1")
    assert s1["Line A"] == 100.0
    assert s1["Line B"] == 150.0


# 7. Numeric -> Histogram
def test_numeric_histogram():
    rows = [[v] for v in [12.5, 14.0, 15.2, 19.8, 22.1, 24.5, 29.0, 31.4, 33.2, 38.0]]
    csv_bytes = _make_csv_bytes(rows, ["tolerance_deviation"])
    config = [{
        "id": "c_hist",
        "title": "Tolerance Distribution",
        "chart_type": "histogram",
        "measure_column": "tolerance_deviation",
        "aggregation": "count",
    }]
    resp = _post_dashboard("qc.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    assert chart["chart_type"] == "histogram"
    assert len(chart["data"]) > 0
    total_pts = sum(p["value"] for p in chart["data"])
    assert total_pts == 10


# 8. Identifier cannot be SUMmed
def test_identifier_cannot_be_summed():
    col_profiles = [
        {"name": "employee_id", "inferred_type": "identifier", "unique_count": 100},
        {"name": "department", "inferred_type": "categorical", "unique_count": 5},
    ]
    cfg = ChartConfigInput(
        id="bad_id_sum",
        title="Invalid Sum of IDs",
        chart_type="bar",
        dimension_column="department",
        measure_column="employee_id",
        aggregation="sum",
    )
    errors = validate_chart_config(cfg, col_profiles)
    assert any("Identifier column 'employee_id' cannot be summed" in e for e in errors)


# 9. Text cannot be Histogram
def test_text_cannot_be_histogram():
    col_profiles = [
        {"name": "city_name", "inferred_type": "text", "unique_count": 20},
    ]
    cfg = ChartConfigInput(
        id="bad_hist",
        title="Invalid Text Histogram",
        chart_type="histogram",
        measure_column="city_name",
        aggregation="count",
    )
    errors = validate_chart_config(cfg, col_profiles)
    assert any("Histogram requires a numeric measure column" in e for e in errors)


# 10. Missing required dimension rejected
def test_missing_required_dimension_rejected():
    col_profiles = [
        {"name": "sales", "inferred_type": "numeric", "unique_count": 50},
    ]
    cfg = ChartConfigInput(
        id="missing_dim",
        title="Missing Dimension Bar",
        chart_type="bar",
        dimension_column=None,
        measure_column="sales",
        aggregation="sum",
    )
    errors = validate_chart_config(cfg, col_profiles)
    assert any("Dimension column is required" in e for e in errors)


# 11. Missing measure rejected
def test_missing_measure_rejected():
    col_profiles = [
        {"name": "category", "inferred_type": "categorical", "unique_count": 4},
    ]
    cfg = ChartConfigInput(
        id="missing_measure",
        title="Missing Measure Sum",
        chart_type="bar",
        dimension_column="category",
        measure_column=None,
        aggregation="sum",
    )
    errors = validate_chart_config(cfg, col_profiles)
    assert any("Measure column is required when aggregation is 'sum'" in e for e in errors)


# 12. Top 10 occurs after aggregation
def test_top_10_occurs_after_aggregation():
    # 15 distinct categories with 2 records each
    rows = []
    for i in range(1, 16):
        cat = f"Cat_{i:02d}"
        # Cat_15 has 150 + 150 = 300
        # Cat_01 has 10 + 10 = 20
        rows.append([cat, i * 10])
        rows.append([cat, i * 10])
    csv_bytes = _make_csv_bytes(rows, ["category", "metric"])
    config = [{
        "id": "top_10_agg",
        "title": "Top 10 Categories",
        "chart_type": "bar",
        "dimension_column": "category",
        "measure_column": "metric",
        "aggregation": "sum",
        "top_n": 10,
        "sort_order": "desc",
    }]
    resp = _post_dashboard("large_cats.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    pts = chart["data"]
    assert len(pts) == 10
    # The top category must be Cat_15 with value 300
    assert pts[0]["label"] == "Cat_15"
    assert pts[0]["value"] == 300.0
    # The 10th category must be Cat_06 with value 120
    assert pts[9]["label"] == "Cat_06"
    assert pts[9]["value"] == 120.0


# 13. Custom title preserved
def test_custom_title_preserved():
    rows = [["Tool Alpha", 15], ["Tool Beta", 25]]
    csv_bytes = _make_csv_bytes(rows, ["tool_code", "repairs"])
    custom_title = "Quarterly Tool Maintenance Frequency Overview"
    config = [{
        "id": "custom_title_chart",
        "title": custom_title,
        "chart_type": "bar",
        "dimension_column": "tool_code",
        "measure_column": "repairs",
        "aggregation": "sum",
    }]
    resp = _post_dashboard("maint.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    assert chart["title"] == custom_title


# 14. Recommended chart customization still works
def test_recommended_chart_customization_still_works():
    rows = [
        ["Product A", 100],
        ["Product B", 200],
        ["Product C", 50],
    ]
    csv_bytes = _make_csv_bytes(rows, ["product", "revenue"])
    # Customized recommendation: changed to ascending sort and mean aggregation
    config = [{
        "id": "rec_customized",
        "title": "Average Revenue by Product Ascending",
        "chart_type": "bar",
        "dimension_column": "product",
        "measure_column": "revenue",
        "aggregation": "mean",
        "sort_order": "asc",
    }]
    resp = _post_dashboard("prods.csv", csv_bytes, config)
    assert resp.status_code == 200, resp.text
    chart = resp.json()["charts"][0]
    pts = chart["data"]
    # Ascending order: Product C (50), Product A (100), Product B (200)
    assert pts[0]["label"] == "Product C"
    assert pts[0]["value"] == 50.0
    assert pts[1]["label"] == "Product A"
    assert pts[1]["value"] == 100.0
    assert pts[2]["label"] == "Product B"
    assert pts[2]["value"] == 200.0


# 15. Existing Manufacturing Dashboard unaffected
def test_existing_manufacturing_dashboard_unaffected():
    from app.dashboard_engine.manufacturing_templates import (
        BLUEPRINT_REFERENCE_PPM_2026,
        calculate_ppm,
        compute_pareto_cumulative,
        compute_ppm_reconciliation,
    )
    # Verify specialized manufacturing formulas remain intact
    ppm = calculate_ppm(rejection_qty=10, production_qty=10000)
    assert ppm == 1000.0

    pareto_pts = compute_pareto_cumulative([
        {"category": "Dent", "count": 80},
        {"category": "Scratch", "count": 20},
    ], measure_key="count")
    assert len(pareto_pts) == 2
    assert pareto_pts[0]["cumulative_percentage"] == 80.0
    assert pareto_pts[1]["cumulative_percentage"] == 100.0

    assert BLUEPRINT_REFERENCE_PPM_2026["Jan-26"] == 4229
    recon = compute_ppm_reconciliation(
        actual_ppm_by_period={"Jan-26": 4229.0},
        source_of_truth_confirmed=True,
        has_sot_conflict=False,
    )
    assert recon.match_count == 1
    assert recon.total_periods == 8
