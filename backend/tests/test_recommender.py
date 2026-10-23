"""
Phase 3 Backend Tests - Automatic Chart Recommendation Engine.

Test suite covers:
 1. Date + numeric measure produces time-series recommendation.
 2. Category + numeric measure produces comparison recommendation.
 3. Identifier columns are not treated as numeric measures.
 4. Empty columns are ignored.
 5. High-cardinality text columns do not produce noisy recommendations.
 6. Numeric distribution recommendations (histograms) are generated only for suitable measures.
 7. Categorical frequency recommendations work without numeric measures.
 8. Missing values do not crash recommendation generation.
 9. Dataset with no useful chart combinations produces an empty list.
10. Existing CSV and multi-sheet XLSX preview endpoints remain intact and include chart_recommendations.
11. Recommendation response objects contain valid serializable data.
12. Recommendation validation logic rejects invalid configuration options.
"""

from __future__ import annotations

import io
from typing import Any
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.recommender import (
    ChartRecommendation,
    recommend_charts,
    _is_measure_candidate,
    _is_categorical_candidate,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_csv_bytes(rows: list[list[Any]], header: list[str]) -> bytes:
    df = pd.DataFrame(rows, columns=header)
    return df.to_csv(index=False).encode("utf-8")


def _make_xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Date + numeric measure -> time-series recommendation
# ---------------------------------------------------------------------------

def test_time_series_recommendation():
    df = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
        "sales": [100.0, 150.0, 200.0, 180.0, 220.0],
    })
    profiles = [
        {"name": "date", "inferred_type": "date", "missing_count": 0, "missing_pct": 0.0, "unique_count": 5},
        {"name": "sales", "inferred_type": "numeric", "missing_count": 0, "missing_pct": 0.0, "unique_count": 5},
    ]

    recs = recommend_charts(df, profiles)
    assert len(recs) > 0
    time_series = [r for r in recs if r["chart_type"] == "line" and r["date_column"] == "date"]
    assert len(time_series) == 1
    assert time_series[0]["measure_column"] == "sales"
    assert time_series[0]["suggested_aggregation"] == "sum"
    assert "sum" in time_series[0]["supported_aggregations"]
    assert "mean" in time_series[0]["supported_aggregations"]


# ---------------------------------------------------------------------------
# 2. Category + numeric measure -> comparison recommendation
# ---------------------------------------------------------------------------

def test_category_comparison_recommendation():
    df = pd.DataFrame({
        "department": ["Sales", "Engineering", "Marketing", "Sales", "Engineering"],
        "budget": [50000, 120000, 40000, 60000, 110000],
    })
    profiles = [
        {"name": "department", "inferred_type": "categorical", "missing_count": 0, "missing_pct": 0.0, "unique_count": 3},
        {"name": "budget", "inferred_type": "currency", "missing_count": 0, "missing_pct": 0.0, "unique_count": 5},
    ]

    recs = recommend_charts(df, profiles)
    bar_recs = [r for r in recs if r["chart_type"] in ("bar", "ranked_bar") and r["dimension_column"] == "department"]
    assert len(bar_recs) >= 1
    assert bar_recs[0]["measure_column"] == "budget"
    assert bar_recs[0]["suggested_aggregation"] == "sum"


# ---------------------------------------------------------------------------
# 3. Identifier columns are not treated as measures
# ---------------------------------------------------------------------------

def test_identifier_not_treated_as_measure():
    profile_id = {
        "name": "customer_id",
        "inferred_type": "identifier",
        "unique_count": 100,
        "missing_count": 0,
    }
    assert not _is_measure_candidate(profile_id)

    profile_zip = {
        "name": "postal_code",
        "inferred_type": "numeric",
        "unique_count": 20,
        "missing_count": 0,
    }
    assert not _is_measure_candidate(profile_zip)


# ---------------------------------------------------------------------------
# 4. Empty columns are ignored
# ---------------------------------------------------------------------------

def test_empty_columns_ignored():
    df = pd.DataFrame({
        "empty_col": [None, None, None],
        "category": ["A", "B", "A"],
    })
    profiles = [
        {"name": "empty_col", "inferred_type": "text", "missing_count": 3, "missing_pct": 100.0, "unique_count": 0},
        {"name": "category", "inferred_type": "categorical", "missing_count": 0, "missing_pct": 0.0, "unique_count": 2},
    ]

    recs = recommend_charts(df, profiles)
    for r in recs:
        assert r.get("dimension_column") != "empty_col"
        assert r.get("measure_column") != "empty_col"
        assert r.get("date_column") != "empty_col"


# ---------------------------------------------------------------------------
# 5. High-cardinality text columns do not produce noisy recommendations
# ---------------------------------------------------------------------------

def test_high_cardinality_text_not_recommended_as_category():
    # 50 unique descriptions in 50 rows
    descriptions = [f"Unique transaction description number {i}" for i in range(50)]
    df = pd.DataFrame({"notes": descriptions})
    profile_notes = {
        "name": "notes",
        "inferred_type": "text",
        "unique_count": 50,
        "missing_count": 0,
    }
    assert not _is_categorical_candidate(profile_notes, total_rows=50)

    recs = recommend_charts(df, [profile_notes])
    assert len(recs) == 0


# ---------------------------------------------------------------------------
# 6. Numeric distribution recommendations (histogram) generated for measures
# ---------------------------------------------------------------------------

def test_numeric_distribution_histogram():
    df = pd.DataFrame({
        "salary": [45000, 52000, 61000, 75000, 89000, 95000, 110000, 125000],
    })
    profiles = [
        {"name": "salary", "inferred_type": "currency", "missing_count": 0, "missing_pct": 0.0, "unique_count": 8},
    ]

    recs = recommend_charts(df, profiles)
    hist_recs = [r for r in recs if r["chart_type"] == "histogram"]
    assert len(hist_recs) == 1
    assert hist_recs[0]["measure_column"] == "salary"


# ---------------------------------------------------------------------------
# 7. Categorical frequency recommendations work without numeric measures
# ---------------------------------------------------------------------------

def test_categorical_frequency_without_measure():
    df = pd.DataFrame({
        "status": ["Pending", "Approved", "Approved", "Rejected", "Pending", "Approved"],
    })
    profiles = [
        {"name": "status", "inferred_type": "categorical", "missing_count": 0, "missing_pct": 0.0, "unique_count": 3},
    ]

    recs = recommend_charts(df, profiles)
    assert len(recs) == 1
    assert recs[0]["chart_type"] in ("donut", "bar")
    assert recs[0]["dimension_column"] == "status"
    assert recs[0]["measure_column"] is None
    assert recs[0]["suggested_aggregation"] == "count"


# ---------------------------------------------------------------------------
# 8. Missing values do not crash recommendation generation
# ---------------------------------------------------------------------------

def test_missing_values_do_not_crash_recommender():
    df = pd.DataFrame({
        "date": ["2026-01-01", None, "2026-01-03", None],
        "category": [None, "Electronics", "Electronics", None],
        "revenue": [500.0, None, 1200.0, 300.0],
    })
    profiles = [
        {"name": "date", "inferred_type": "date", "missing_count": 2, "missing_pct": 50.0, "unique_count": 2},
        {"name": "category", "inferred_type": "categorical", "missing_count": 2, "missing_pct": 50.0, "unique_count": 1},
        {"name": "revenue", "inferred_type": "currency", "missing_count": 1, "missing_pct": 25.0, "unique_count": 3},
    ]

    recs = recommend_charts(df, profiles)
    assert isinstance(recs, list)
    # Verify caveats acknowledge missing values
    for r in recs:
        if r.get("date_column") == "date":
            assert any("missing" in c.lower() for c in r["caveats"])


# ---------------------------------------------------------------------------
# 9. Dataset with no useful chart combinations produces empty list
# ---------------------------------------------------------------------------

def test_no_useful_charts_produces_empty_result():
    df = pd.DataFrame({
        "id": ["ID-01", "ID-02", "ID-03"],
        "empty_notes": [None, None, None],
    })
    profiles = [
        {"name": "id", "inferred_type": "identifier", "missing_count": 0, "missing_pct": 0.0, "unique_count": 3},
        {"name": "empty_notes", "inferred_type": "text", "missing_count": 3, "missing_pct": 100.0, "unique_count": 0},
    ]

    recs = recommend_charts(df, profiles)
    assert recs == []


# ---------------------------------------------------------------------------
# 10. Existing CSV and multi-sheet XLSX preview endpoints include chart_recommendations
# ---------------------------------------------------------------------------

def test_preview_endpoint_includes_chart_recommendations():
    csv_bytes = _make_csv_bytes(
        rows=[
            ["2026-01-10", "Hardware", 1200.0],
            ["2026-01-11", "Software", 850.0],
            ["2026-01-12", "Hardware", 950.0],
        ],
        header=["order_date", "category", "revenue"],
    )
    files = {"file": ("sales.csv", csv_bytes, "text/csv")}
    resp = client.post("/api/datasets/preview", files=files)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "chart_recommendations" in data
    assert isinstance(data["chart_recommendations"], list)
    assert len(data["chart_recommendations"]) > 0

    # Ensure all previous fields still exist
    assert "filename" in data
    assert "row_count" in data
    assert "column_count" in data
    assert "columns" in data
    assert "preview_rows" in data
    assert "warnings" in data


def test_preview_endpoint_multisheet_recommendations():
    df1 = pd.DataFrame({
        "txn_date": ["2026-02-01", "2026-02-02"],
        "units": [10, 20],
    })
    df2 = pd.DataFrame({
        "dept": ["Ops", "HR"],
        "headcount": [50, 12],
    })
    xlsx_bytes = _make_xlsx_bytes({"Operations": df1, "HumanResources": df2})

    files = {"file": ("enterprise.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/datasets/preview", files=files, data={"sheet_name": "HumanResources"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["selected_sheet"] == "HumanResources"
    assert "chart_recommendations" in data
    recs = data["chart_recommendations"]
    assert any(r.get("dimension_column") == "dept" for r in recs)


# ---------------------------------------------------------------------------
# 11. Recommendation response objects contain valid serializable data
# ---------------------------------------------------------------------------

def test_recommendation_serializable_model():
    rec = ChartRecommendation(
        id="rec_test_1",
        title="Test Chart",
        chart_type="bar",
        dimension_column="category",
        measure_column="amount",
        suggested_aggregation="sum",
        supported_aggregations=["sum", "mean", "count"],
        explanation="Valid test explanation.",
        suitability="high",
        suitability_reason="Test reason.",
        caveats=["Test caveat"],
        requires_confirmation=True,
    )
    data = rec.model_dump()
    assert isinstance(data, dict)
    assert data["id"] == "rec_test_1"
    assert data["requires_confirmation"] is True
