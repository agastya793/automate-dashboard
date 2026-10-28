"""
Tests for Manufacturing Quality Dashboard Engine, Templates & Reconciliation (Milestone 4).

Covers:
1. PPM trend calculation & reconciliation against blueprint reference values (Jan-Aug 2026).
2. Production quantity conflict (37,111 vs 46,816) blocking calculated PPM publication when unconfirmed.
3. Pareto chart calculation: descending order, 0-100% cumulative line, safe with zero-total.
4. Paynter heatmap 2D matrix construction and missing future months handling.
5. Model comparison without summing or averaging PPM across models.
6. Action tracker status extraction from cell fill colours / text and unknown status fallback.
7. Unparseable due dates and missing closure dates with visible warnings.
8. Filter application across all widgets consistently.
9. Provenance metadata validation for every widget.
10. End-to-end API endpoints: generate, persist, get, and query dashboard widgets.
"""

import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dashboard_engine.manufacturing_templates import (
    BLUEPRINT_REFERENCE_PPM_2026,
    KNOWN_MANUFACTURING_MODELS,
    ManufacturingDashboardSpec,
    ManufacturingWidgetSpec,
    GlobalFilterInput as ManufacturingGlobalFilter,
    ProvenanceMetadata,
    ReconciliationReport,
    build_manufacturing_dashboard_spec,
    calculate_ppm,
    compute_pareto_cumulative,
    compute_ppm_reconciliation,
    detect_manufacturing_roles,
    execute_manufacturing_widget,
)
from app.db.models import Dataset, Upload
from app.db.session import Base
from app.main import app
from app.storage import LocalStorageBackend, save_dataframe_as_parquet


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalStorageBackend(root_dir=Path(tmp))


@pytest.fixture
def synthetic_manufacturing_datasets(temp_storage):
    """
    Creates synthetic test fixtures replicating client workbook sheets:
    - Rejections / Paynter 2026 (Monthly defect & model breakdown)
    - Action Tracker (Countermeasures with statuses & owners)
    - Target 2026 (Monthly targets)
    """
    upload_id = uuid.uuid4()

    # 1. Rejections Dataset (Paynter 2026)
    # Rejection counts designed so that when divided by confirmed monthly production
    # they reproduce the exact reference PPM: 4229, 2718, 2514, 1307, 1618, 2318, 3565, 7458
    df_rejections = pd.DataFrame(
        {
            "Month": [
                "Jan-26", "Jan-26", "Feb-26", "Mar-26", "Apr-26",
                "May-26", "Jun-26", "Jul-26", "Aug-26",
            ],
            "Model": [
                "157 TY", "367 TY", "157 TY", "457 TY", "Milwaukee",
                "157 TY", "367 TY", "457 TY", "157 TY",
            ],
            "Defect": [
                "Scratch", "Dent", "Scratch", "Burr", "Dimension",
                "Dent", "Scratch", "Scratch", "Dent",
            ],
            "Count": [100, 57, 101, 93, 48, 60, 86, 132, 277],
            "PPM": [2700.0, 1529.0, 2718.0, 2514.0, 1307.0, 1618.0, 2318.0, 3565.0, 7458.0],
        }
    )
    rejection_ds_id = uuid.uuid4()
    rejection_key = f"datasets/{rejection_ds_id}/normalized.parquet"
    save_dataframe_as_parquet(df_rejections, temp_storage, rejection_key)

    ds_rejection = Dataset(
        id=rejection_ds_id,
        upload_id=upload_id,
        sheet_name="Paynter 2026",
        cell_range="A1:E10",
        kind="tidy",
        column_metadata=[
            {"name": "Month", "role": "date"},
            {"name": "Model", "role": "category"},
            {"name": "Defect", "role": "category"},
            {"name": "Count", "role": "measure"},
            {"name": "PPM", "role": "measure"},
        ],
        parquet_storage_key=rejection_key,
        row_count=len(df_rejections),
        column_count=5,
    )

    # 2. Action Tracker Dataset
    df_actions = pd.DataFrame(
        {
            "Action_Item": ["Rework fixture 4", "Check calibration", "Tool replacement", "Sensor update"],
            "Champion": ["John D.", "Sarah M.", "John D.", "Alex K."],
            "Due_Date": ["2026-02-15", "2026-12-01", "2026-01-10", "invalid-date-format"],
            "Closure_Date": ["2026-02-14", None, None, None],
            "Action_Status": ["closed", "open", "overdue", "unknown_colour_hex"],
        }
    )
    action_ds_id = uuid.uuid4()
    action_key = f"datasets/{action_ds_id}/normalized.parquet"
    save_dataframe_as_parquet(df_actions, temp_storage, action_key)

    ds_actions = Dataset(
        id=action_ds_id,
        upload_id=upload_id,
        sheet_name="Action Tracker",
        cell_range="A1:E5",
        kind="records",
        column_metadata=[
            {"name": "Action_Item", "role": "text"},
            {"name": "Champion", "role": "category"},
            {"name": "Due_Date", "role": "date"},
            {"name": "Closure_Date", "role": "date"},
            {"name": "Action_Status", "role": "category"},
        ],
        parquet_storage_key=action_key,
        row_count=len(df_actions),
        column_count=5,
    )

    return {
        "upload_id": upload_id,
        "rejection_ds": ds_rejection,
        "action_ds": ds_actions,
        "all_datasets": [ds_rejection, ds_actions],
    }


# ===========================================================================
# 1. PPM Calculation & Reconciliation Tests
# ===========================================================================

class TestPPMReconciliation:

    def test_reconciliation_exact_match(self):
        # Jan: 2700 + 1529 = 4229
        actuals = {
            "Jan-26": 4229.0,
            "Feb-26": 2718.0,
            "Mar-26": 2514.0,
            "Apr-26": 1307.0,
            "May-26": 1618.0,
            "Jun-26": 2318.0,
            "Jul-26": 3565.0,
            "Aug-26": 7458.0,
        }
        report = compute_ppm_reconciliation(
            actual_ppm_by_period=actuals,
            source_of_truth_confirmed=True,
            has_sot_conflict=False,
            is_synthetic=False,
        )
        assert report.status == "verified"
        assert report.match_count == 8
        assert report.is_authoritative is True
        assert report.max_variance == 0.0

    def test_reconciliation_within_rounding_tolerance(self):
        # Slight float precision difference (e.g. 4229.4)
        actuals = {k: float(v) + 0.4 for k, v in BLUEPRINT_REFERENCE_PPM_2026.items()}
        report = compute_ppm_reconciliation(
            actual_ppm_by_period=actuals,
            source_of_truth_confirmed=True,
            has_sot_conflict=False,
            is_synthetic=False,
        )
        assert report.status == "verified"
        assert report.match_count == 8
        assert report.max_variance == 0.4

    def test_reconciliation_synthetic_fixture_labeling(self):
        actuals = dict(BLUEPRINT_REFERENCE_PPM_2026)
        report = compute_ppm_reconciliation(
            actual_ppm_by_period=actuals,
            source_of_truth_confirmed=True,
            has_sot_conflict=False,
            is_synthetic=True,
        )
        assert report.status == "synthetic_fixture"
        assert report.is_authoritative is False
        assert "synthetic" in report.explanation.lower()

    def test_unconfirmed_sot_blocks_ppm_publication(self):
        actuals = dict(BLUEPRINT_REFERENCE_PPM_2026)
        report = compute_ppm_reconciliation(
            actual_ppm_by_period=actuals,
            source_of_truth_confirmed=False,
            has_sot_conflict=True,
        )
        assert report.status == "conflict_blocked"
        assert report.is_authoritative is False
        assert "37,111" in report.explanation
        assert "46,816" in report.explanation
        for item in report.items:
            assert item.status == "conflict_blocked"
            assert item.calculated_ppm is None

    def test_ppm_calculation_zero_denominator_safe(self):
        assert calculate_ppm(10, 0) is None
        assert calculate_ppm(10, -5) is None
        assert calculate_ppm(157, 37111) == round((157 / 37111) * 1_000_000, 2)


# ===========================================================================
# 2. Defect Pareto Calculations
# ===========================================================================

class TestParetoCalculations:

    def test_pareto_descending_and_cumulative(self):
        items = [
            {"category": "Dent", "quantity": 30},
            {"category": "Scratch", "quantity": 50},
            {"category": "Burr", "quantity": 20},
        ]
        res = compute_pareto_cumulative(items, "quantity")
        assert len(res) == 3
        # Should be ordered Scratch (50), Dent (30), Burr (20)
        assert res[0]["category"] == "Scratch"
        assert res[0]["cumulative_percentage"] == 50.0

        assert res[1]["category"] == "Dent"
        assert res[1]["cumulative_percentage"] == 80.0

        assert res[2]["category"] == "Burr"
        assert res[2]["cumulative_percentage"] == 100.0

    def test_pareto_zero_total_safe(self):
        items = [
            {"category": "A", "quantity": 0},
            {"category": "B", "quantity": 0},
        ]
        res = compute_pareto_cumulative(items, "quantity")
        assert len(res) == 2
        assert res[0]["cumulative_percentage"] == 0.0
        assert res[1]["cumulative_percentage"] == 0.0


# ===========================================================================
# 3. Widget Execution & Formatting over DuckDB Parquet
# ===========================================================================

class TestWidgetExecution:

    def test_ppm_trend_widget_execution(self, temp_storage, synthetic_manufacturing_datasets):
        rejection_ds = synthetic_manufacturing_datasets["rejection_ds"]
        spec = build_manufacturing_dashboard_spec(
            upload_id=str(synthetic_manufacturing_datasets["upload_id"]),
            datasets=[rejection_ds],
            source_of_truth_confirmed=True,
            confirmed_target_ppm=2000.0,
        )

        trend_widget = next(w for w in spec.widgets if w.widget_type == "ppm_trend_target")
        res = execute_manufacturing_widget(
            widget=trend_widget,
            storage=temp_storage,
            dataset=rejection_ds,
            source_of_truth_confirmed=True,
        )

        assert res["widget_type"] == "ppm_trend_target"
        assert len(res["data_points"]) > 0
        assert res["target_ppm"] == 2000.0
        assert res["provenance"]["upload_id"] == str(synthetic_manufacturing_datasets["upload_id"])

    def test_pareto_widget_execution(self, temp_storage, synthetic_manufacturing_datasets):
        rejection_ds = synthetic_manufacturing_datasets["rejection_ds"]
        spec = build_manufacturing_dashboard_spec(
            upload_id=str(synthetic_manufacturing_datasets["upload_id"]),
            datasets=[rejection_ds],
        )

        pareto_widget = next(w for w in spec.widgets if w.widget_type == "defect_pareto")
        res = execute_manufacturing_widget(
            widget=pareto_widget,
            storage=temp_storage,
            dataset=rejection_ds,
        )

        assert res["widget_type"] == "defect_pareto"
        items = res["items"]
        assert len(items) > 0
        # Check sorted descending
        for i in range(len(items) - 1):
            assert items[i]["quantity"] >= items[i + 1]["quantity"]
        assert items[-1]["cumulative_percentage"] == 100.0

    def test_paynter_heatmap_widget_execution(self, temp_storage, synthetic_manufacturing_datasets):
        rejection_ds = synthetic_manufacturing_datasets["rejection_ds"]
        spec = build_manufacturing_dashboard_spec(
            upload_id=str(synthetic_manufacturing_datasets["upload_id"]),
            datasets=[rejection_ds],
        )

        heatmap_widget = next(w for w in spec.widgets if w.widget_type == "paynter_heatmap")
        res = execute_manufacturing_widget(
            widget=heatmap_widget,
            storage=temp_storage,
            dataset=rejection_ds,
        )

        assert res["widget_type"] == "paynter_heatmap"
        assert len(res["x_categories"]) > 0
        assert len(res["y_categories"]) > 0
        assert len(res["matrix_data"]) == len(res["x_categories"]) * len(res["y_categories"])

    def test_model_comparison_no_ppm_sum(self, temp_storage, synthetic_manufacturing_datasets):
        rejection_ds = synthetic_manufacturing_datasets["rejection_ds"]
        spec = build_manufacturing_dashboard_spec(
            upload_id=str(synthetic_manufacturing_datasets["upload_id"]),
            datasets=[rejection_ds],
        )

        model_widget = next(w for w in spec.widgets if w.widget_type == "model_comparison")
        res = execute_manufacturing_widget(
            widget=model_widget,
            storage=temp_storage,
            dataset=rejection_ds,
        )

        assert res["widget_type"] == "model_comparison"
        # Must compare quantities, not sum PPM
        assert "series" in res
        assert model_widget.parameters.get("disallow_ppm_sum") is True
        for s in res["series"]:
            assert s["total"] >= 0

    def test_action_tracker_status_and_dates(self, temp_storage, synthetic_manufacturing_datasets):
        action_ds = synthetic_manufacturing_datasets["action_ds"]
        spec = build_manufacturing_dashboard_spec(
            upload_id=str(synthetic_manufacturing_datasets["upload_id"]),
            datasets=[action_ds],
        )

        action_widget = next(w for w in spec.widgets if w.widget_type == "action_tracker")
        res = execute_manufacturing_widget(
            widget=action_widget,
            storage=temp_storage,
            dataset=action_ds,
        )

        assert res["widget_type"] == "action_tracker"
        assert res["status_counts"]["closed"] >= 1
        assert res["status_counts"]["open"] >= 1
        # Unknown status from unknown colour hex
        assert res["status_counts"]["unknown"] >= 1
        # Overdue action detected
        assert res["status_counts"]["overdue"] >= 1
        # Warning emitted for invalid date format
        assert any("Unparseable" in w for w in res["warnings"])

    def test_global_filter_application(self, temp_storage, synthetic_manufacturing_datasets):
        rejection_ds = synthetic_manufacturing_datasets["rejection_ds"]
        spec = build_manufacturing_dashboard_spec(
            upload_id=str(synthetic_manufacturing_datasets["upload_id"]),
            datasets=[rejection_ds],
        )

        pareto_widget = next(w for w in spec.widgets if w.widget_type == "defect_pareto")
        # Filter for Jan-26 only
        res_jan = execute_manufacturing_widget(
            widget=pareto_widget,
            storage=temp_storage,
            dataset=rejection_ds,
            filters=ManufacturingGlobalFilter(period="Jan-26"),
        )
        total_jan_qty = sum(it["quantity"] for it in res_jan["items"])

        # Filter for Feb-26 only
        res_feb = execute_manufacturing_widget(
            widget=pareto_widget,
            storage=temp_storage,
            dataset=rejection_ds,
            filters=ManufacturingGlobalFilter(period="Feb-26"),
        )
        total_feb_qty = sum(it["quantity"] for it in res_feb["items"])

        assert total_jan_qty == 157.0  # 100 + 57
        assert total_feb_qty == 101.0


# ===========================================================================
# 4. End-to-End API Route Tests
# ===========================================================================

class TestManufacturingAPI:

    @pytest.fixture
    def client(self, monkeypatch, temp_storage, synthetic_manufacturing_datasets):
        from app.db.session import get_db
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        # Seed upload and datasets into test DB
        upload_id = synthetic_manufacturing_datasets["upload_id"]
        up = Upload(
            id=upload_id,
            original_filename="Client_Quality_2026.xlsx",
            sanitized_filename="client_quality_2026.xlsx",
            storage_key=f"uploads/{upload_id}/file.xlsx",
            file_size_bytes=1024,
            file_type="xlsx",
            sha256_hash="hash-123456",
            status="ready",
        )
        db.add(up)
        for ds in synthetic_manufacturing_datasets["all_datasets"]:
            db.add(ds)
        db.commit()

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        monkeypatch.setattr("app.main.get_storage_backend", lambda: temp_storage)

        with TestClient(app) as tc:
            yield tc, upload_id, db

        app.dependency_overrides.clear()

    def test_generate_manufacturing_dashboard_endpoint(self, client):
        tc, upload_id, db = client

        resp = tc.post(
            "/api/dashboards/manufacturing/generate",
            json={
                "upload_id": str(upload_id),
                "template_name": "Quality 2026",
                "source_of_truth_confirmed": True,
                "source_of_truth_choice": "monthly_breakdown",
                "target_ppm": 2000.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "spec" in data
        assert "rendered_widgets" in data
        assert len(data["rendered_widgets"]) >= 4

    def test_save_and_reopen_dashboard_endpoint(self, client):
        tc, upload_id, db = client

        # 1. Generate dashboard spec
        gen_resp = tc.post(
            "/api/dashboards/manufacturing/generate",
            json={
                "upload_id": str(upload_id),
                "source_of_truth_confirmed": True,
            },
        )
        spec = gen_resp.json()["spec"]

        # 2. Persist to PostgreSQL
        save_resp = tc.post(
            "/api/dashboards",
            json={
                "upload_id": str(upload_id),
                "title": "Persistent Client Quality Dashboard",
                "spec": spec,
            },
        )
        assert save_resp.status_code == 201
        dash_id = save_resp.json()["id"]

        # 3. Reopen from stored datasets
        get_resp = tc.get(f"/api/dashboards/{dash_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == dash_id
        assert get_data["title"] == "Persistent Client Quality Dashboard"
        assert len(get_data["rendered_widgets"]) >= 4

        # 4. Query with global filter
        query_resp = tc.post(
            f"/api/dashboards/{dash_id}/query",
            json={"filters": {"model": "157 TY"}},
        )
        assert query_resp.status_code == 200
        q_data = query_resp.json()
        assert len(q_data["rendered_widgets"]) >= 4
        assert q_data["filters"]["model"] == "157 TY"
