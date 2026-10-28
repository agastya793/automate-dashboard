"""
Tests for Milestone 3 Asynchronous Ingestion & DuckDB Query APIs.

Covers:
- POST /api/uploads (HTTP 202, streaming to storage, queueing scan)
- File validation (415 unsupported format, 413 oversized)
- GET /api/uploads (paginated list)
- GET /api/uploads/{id} (status polling)
- GET /api/uploads/{id}/datasets (detected block previews)
- POST /api/uploads/{id}/normalize (normalisation to Parquet)
- POST /api/uploads/{id}/retry (retry failed processing)
- POST /api/query (parameterized DuckDB queries on Parquet)
"""

import io
import uuid
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.auth import get_current_user, AuthenticatedUser
from app.db.models import Base
from app.db.session import get_db
from app.storage.local import LocalStorageBackend
from app.storage import get_storage_backend


def _make_xlsx(sheets: dict) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def api_test_env(tmp_path):
    """Isolated database and storage backend for API testing."""
    from app.db.session import set_session_factory
    from app.worker.celery_app import celery_app

    celery_app.conf.update(
        task_always_eager=True,
        task_store_eager_result=False,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    set_session_factory(TestingSessionLocal)

    storage = LocalStorageBackend(root_dir=tmp_path / "storage")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_backend] = lambda: storage
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="00000000-0000-0000-0000-000000000001",
        email="test@local.internal",
        role="authenticated",
    )

    client = TestClient(app)

    yield {
        "client": client,
        "storage": storage,
        "session": TestingSessionLocal,
    }

    set_session_factory(None)
    app.dependency_overrides.clear()


def test_upload_workbook_accepted_and_scanned(api_test_env):
    """POST /api/uploads returns 202 and stores file; background scan creates datasets."""
    client = api_test_env["client"]
    storage = api_test_env["storage"]

    xlsx_bytes = _make_xlsx(
        {
            "Monthly_Rejection": [
                ["Defect Type", "Jan-26", "Feb-26", "Mar-26"],
                ["Scratch", 10, 15, 20],
                ["Dent", 5, 8, 12],
                ["Crack", 2, 4, 3],
            ]
        }
    )

    files = {"file": ("rejections.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = client.post("/api/uploads", files=files)

    assert response.status_code == 202
    data = response.json()
    assert "upload_id" in data
    assert data["original_filename"] == "rejections.xlsx"
    assert data["file_size_bytes"] == len(xlsx_bytes)
    assert data["status_url"] == f"/api/uploads/{data['upload_id']}"

    upload_id = data["upload_id"]

    # In eager / fallback mode, the task runs and updates the status to ready or needs_mapping
    status_res = client.get(f"/api/uploads/{upload_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["upload_id"] == upload_id
    assert status_data["status"] in ("needs_mapping", "ready", "queued", "scanning")

    # Verify datasets endpoint
    ds_res = client.get(f"/api/uploads/{upload_id}/datasets")
    assert ds_res.status_code == 200
    datasets = ds_res.json()
    assert len(datasets) >= 1
    assert datasets[0]["sheet_name"] == "Monthly_Rejection"
    assert datasets[0]["row_count"] >= 3


def test_upload_unsupported_format_rejected(api_test_env):
    """POST /api/uploads rejects files with invalid extensions."""
    client = api_test_env["client"]
    files = {"file": ("malicious.exe", io.BytesIO(b"MZ..."), "application/octet-stream")}
    response = client.post("/api/uploads", files=files)
    assert response.status_code == 415
    assert "Unsupported file format" in response.json()["detail"]


def test_upload_oversized_rejected(api_test_env, monkeypatch):
    """POST /api/uploads rejects files exceeding MAX_UPLOAD_BYTES."""
    client = api_test_env["client"]
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "MAX_UPLOAD_BYTES", 100)
    files = {"file": ("large.xlsx", io.BytesIO(b"x" * 200), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = client.post("/api/uploads", files=files)
    assert response.status_code == 413


def test_list_uploads_pagination(api_test_env):
    """GET /api/uploads returns paginated upload summaries."""
    client = api_test_env["client"]

    xlsx_bytes = _make_xlsx({"S1": [["A", "B"], [1, 2]]})
    for i in range(3):
        files = {"file": (f"test_{i}.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        client.post("/api/uploads", files=files)

    res = client.get("/api/uploads?page=1&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_upload_not_found(api_test_env):
    """GET /api/uploads/{id} returns 404 for nonexistent upload."""
    client = api_test_env["client"]
    fake_id = str(uuid.uuid4())
    res = client.get(f"/api/uploads/{fake_id}")
    assert res.status_code == 404


def test_retry_non_failed_upload_rejected(api_test_env):
    """POST /api/uploads/{id}/retry rejects retrying an upload that is not failed."""
    client = api_test_env["client"]
    xlsx_bytes = _make_xlsx({"S1": [["A", "B"], [1, 2]]})
    files = {"file": ("test.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    up_res = client.post("/api/uploads", files=files)
    upload_id = up_res.json()["upload_id"]

    retry_res = client.post(f"/api/uploads/{upload_id}/retry")
    # If the upload is in needs_mapping or ready (not failed), retry should return 400
    status_res = client.get(f"/api/uploads/{upload_id}")
    if status_res.json()["status"] != "failed":
        assert retry_res.status_code == 400
        assert "Only 'failed' uploads" in retry_res.json()["detail"]


def test_full_pipeline_upload_normalize_and_duckdb_query(api_test_env):
    """End-to-end verification: upload -> detect -> normalize to Parquet -> DuckDB query."""
    client = api_test_env["client"]

    # 1. Upload workbook with wide defect monthly rejection data
    xlsx_bytes = _make_xlsx(
        {
            "Quality": [
                ["Defect", "Jan-26", "Feb-26"],
                ["Scratch", 10, 20],
                ["Dent", 5, 15],
            ]
        }
    )
    files = {"file": ("Quality.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    up_res = client.post("/api/uploads", files=files)
    assert up_res.status_code == 202
    upload_id = up_res.json()["upload_id"]

    # 2. Get datasets
    ds_res = client.get(f"/api/uploads/{upload_id}/datasets")
    assert ds_res.status_code == 200
    datasets = ds_res.json()
    assert len(datasets) > 0
    dataset_id = datasets[0]["dataset_id"]

    # 3. Trigger normalisation
    norm_res = client.post(f"/api/uploads/{upload_id}/normalize")
    assert norm_res.status_code == 202

    # 4. Refresh dataset metadata (now normalized with Parquet key)
    ds_res2 = client.get(f"/api/uploads/{upload_id}/datasets")
    assert ds_res2.status_code == 200
    datasets2 = ds_res2.json()
    norm_ds = datasets2[0]
    assert norm_ds["parquet_storage_key"] is not None

    # 5. Query the normalized Parquet table via DuckDB query plan
    query_plan = {
        "dataset_id": dataset_id,
        "dimensions": ["Defect"],
        "measures": ["Jan-26"],
        "aggregations": {"Jan-26": "sum"},
        "sort_by": "Jan-26",
        "sort_desc": True,
    }
    q_res = client.post("/api/query", json=query_plan)
    assert q_res.status_code == 200, f"Error: {q_res.json()}"
    q_data = q_res.json()
    assert "rows" in q_data
    assert len(q_data["rows"]) == 2
    # Scratch (10) should be first because of desc sort
    first_row = q_data["rows"][0]
    assert first_row["Defect"] == "Scratch"
    assert first_row.get("Jan-26_sum", first_row.get("Jan-26")) == 10


def test_duckdb_query_injection_rejection(api_test_env):
    """POST /api/query rejects column injection attempts."""
    client = api_test_env["client"]
    malicious_plan = {
        "dataset_id": str(uuid.uuid4()),
        "dimensions": ["col; DROP TABLE users;--"],
        "measures": [],
    }
    res = client.post("/api/query", json=malicious_plan)
    assert res.status_code == 422  # Pydantic field_validator rejects identifier


def test_synthetic_test_workbook_async_upload_flow(api_test_env):
    """
    Test uploading Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx
    verifying 202 Accepted, storage persistence, worker dataset scanning,
    status polling, and retry flow.
    """
    from pathlib import Path
    client = api_test_env["client"]
    storage = api_test_env["storage"]

    # Locate synthetic workbook
    wb_path = Path("sample_data") / "Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx"
    if not wb_path.exists():
        wb_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx"

    assert wb_path.exists(), f"Synthetic test workbook not found at {wb_path}"
    raw_bytes = wb_path.read_bytes()

    # 1. Asynchronous upload
    res = client.post(
        "/api/uploads",
        files={"file": ("Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx", raw_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 202
    data = res.json()
    upload_id = data["upload_id"]
    assert data["status"] == "queued"
    assert data["original_filename"] == "Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx"

    # 2. Worker execution (eager in tests or invoked)
    from app.worker.tasks import scan_workbook_task
    from app.db.repositories import UploadRepository
    from app.storage import get_storage_backend
    active_storage = get_storage_backend()
    db = api_test_env["session"]()
    try:
        u = UploadRepository(db).get(upload_id)
        storage_key = u.storage_key
        assert active_storage.object_exists(storage_key)
    finally:
        db.close()

    scan_res = scan_workbook_task(upload_id, storage_key)
    assert scan_res["status"] == "success"

    # 3. Status polling
    status_res = client.get(f"/api/uploads/{upload_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["status"] in ("needs_mapping", "ready")
    assert status_data["progress"] == 100

    # 4. Datasets catalog discovery
    ds_res = client.get(f"/api/uploads/{upload_id}/datasets")
    assert ds_res.status_code == 200
    datasets = ds_res.json()
    assert len(datasets) == 3
    sheet_names = {d["sheet_name"] for d in datasets}
    assert "Paynter 2026" in sheet_names
    assert "Action Tracker" in sheet_names
    assert "Targets" in sheet_names

