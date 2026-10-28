"""
Business Reporting Dashboard - Backend API Service

Phase 1:  Health check + CORS
Phase 2:  POST /api/datasets/preview — multipart upload, dataset profiling
Phase 4:  POST /api/datasets/dashboard — aggregated chart data
Milestone 1: POST /api/workbooks/scan — block detection + classification

How to run locally:
    1. Navigate to the backend directory:
       cd backend
    2. Create & activate a virtual environment:
       python -m venv .venv
       .venv\\Scripts\\activate        # Windows
       source .venv/bin/activate      # macOS/Linux
    3. Install dependencies:
       pip install -r requirements.txt
    4. Start the development server:
       uvicorn app.main:app --reload --port 8000
"""

import datetime as dt
import hashlib
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import (
    AuthenticatedUser,
    get_current_user,
    has_required_role,
    verify_csrf_and_origin,
    verify_dashboard_access,
    verify_template_access,
    verify_upload_access,
)
from app.api.auth_routes import router as auth_router, workspace_router
from app.db.session import get_db
from app.db.repositories import (
    UploadRepository,
    DatasetRepository,
    TemplateRepository,
    DashboardRepository,
    ExportRepository,
)
from app.storage import get_storage_backend
from app.dashboard_engine.duckdb_engine import QueryPlan, execute_query_plan
from app.dashboard_engine.manufacturing_templates import (
    ManufacturingDashboardSpec,
    ManufacturingWidgetSpec,
    GlobalFilterInput as ManufacturingGlobalFilter,
    build_manufacturing_dashboard_spec,
    execute_manufacturing_widget,
    compute_ppm_reconciliation,
)

logger = logging.getLogger("main_api")

from app.profiler import (
    DatasetError,
    FileTooLargeError,
    InvalidSheetError,
    MalformedFileError,
    TooManyColumnsError,
    TooManyRowsError,
    UnsupportedFormatError,
    load_and_validate_dataset,
    profile_dataset,
)
from app.recommender import ChartRecommendation
from app.dashboard import (
    ChartConfigInput,
    GlobalFilterInput,
    DashboardResponse,
    generate_dashboard_data,
)
from app.ingestion.scanner import scan_workbook, ScanResult
from app.ingestion.mapping import (
    MappingTemplate,
    MappingTemplateSummary,
    NormalizationResult,
    template_storage,
    normalize_workbook,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Resource limits — override via environment variables
# ---------------------------------------------------------------------------

def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


MAX_UPLOAD_BYTES: int = _int_env("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
MAX_DATA_ROWS: int = _int_env("MAX_DATA_ROWS", 50_000)
MAX_COLUMNS: int = _int_env("MAX_COLUMNS", 100)
MAX_PREVIEW_ROWS: int = _int_env("MAX_PREVIEW_ROWS", 20)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Business Reporting Dashboard API",
    description="Backend API for automated Excel/CSV dataset inspection and reporting.",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


def get_allowed_origins() -> List[str]:
    """
    Parse allowed CORS origins from the environment.
    Defaults to localhost:3000 for safe local frontend development.
    Avoids unrestricted wildcard ('*') origins.
    """
    raw_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    return origins or ["http://localhost:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(workspace_router)


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """
    Middleware verifying CSRF tokens and Origin/Referer for state-changing requests.
    Exempts safe methods (GET, HEAD, OPTIONS).
    """
    try:
        verify_csrf_and_origin(
            request=request,
            csrf_cookie=request.cookies.get("csrf_token"),
            csrf_header=request.headers.get("X-CSRF-Token"),
        )
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.on_event("startup")
async def startup_security_check():
    """
    Startup guard:
    Ensures local-only single-user dev mode cannot accidentally be run in production.
    """
    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env == "production":
        dev_mode = os.getenv("SINGLE_USER_DEV_MODE", "false").lower() == "true"
        if dev_mode:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "Local single-user development mode is active (SINGLE_USER_DEV_MODE=true) "
                "which is prohibited when APP_ENV=production. Ensure proper authentication is configured."
            )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class UploadAcceptedResponse(BaseModel):
    upload_id: str
    status: str
    original_filename: str
    file_size_bytes: int
    created_at: str
    status_url: str


class UploadSummary(BaseModel):
    upload_id: str
    original_filename: str
    sanitized_filename: str
    file_size_bytes: int
    file_type: str
    status: str
    stage: Optional[str] = None
    progress: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    dataset_count: int = 0
    created_at: str
    updated_at: str


class UploadListResponse(BaseModel):
    items: List[UploadSummary]
    total: int
    page: int
    page_size: int


class DatasetSummaryResponse(BaseModel):
    dataset_id: str
    upload_id: str
    sheet_name: str
    cell_range: str
    kind: str
    column_metadata: List[Dict[str, Any]]
    normalization_status: str
    parquet_storage_key: Optional[str] = None
    row_count: int
    column_count: int
    summary_metadata: Dict[str, Any]


class QueryPlanInput(BaseModel):
    dataset_id: str
    dimensions: List[str] = []
    measures: List[str] = []
    aggregations: Dict[str, str] = {}
    filters: List[Dict[str, Any]] = []
    sort_by: Optional[str] = None
    sort_desc: bool = False
    top_n: Optional[int] = None
    limit: int = 500


class RootResponse(BaseModel):
    message: str
    docs_url: str
    health_url: str


class ColumnProfile(BaseModel):
    name: str
    inferred_type: str
    missing_count: int
    missing_pct: float
    missing_percentage: Optional[float] = None
    unique_count: int
    sample_values: Optional[List[Any]] = None


class DatasetPreviewResponse(BaseModel):
    filename: str
    file_name: Optional[str] = None
    file_type: str
    file_size_bytes: Optional[int] = None
    sheet_names: List[str]
    available_worksheets: Optional[List[str]] = None
    selected_sheet: Optional[str] = None
    selected_worksheet: Optional[str] = None
    row_count: int
    total_rows: Optional[int] = None
    column_count: int
    total_columns: Optional[int] = None
    column_names: List[str]
    columns: List[ColumnProfile]
    duplicate_row_count: int
    total_missing_cells: int
    preview_rows: List[List[Any]]
    warnings: List[str]
    chart_recommendations: List[ChartRecommendation] = []


# ---------------------------------------------------------------------------
# Existing Phase 1 endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_model=RootResponse, summary="Root service info")
def read_root() -> RootResponse:
    """Returns basic information and service links."""
    return RootResponse(
        message="Business Reporting Dashboard API is active.",
        docs_url="/docs",
        health_url="/health",
    )


@app.get("/health", response_model=HealthResponse, summary="System health check")
def health_check() -> HealthResponse:
    """
    Returns system status and basic operational information.
    Used by load balancers, orchestrators, and frontend connectivity checks.
    """
    env = os.getenv("ENVIRONMENT", "development")
    return HealthResponse(
        status="healthy",
        service="business-reporting-dashboard-api",
        version="0.2.0",
        environment=env,
    )


# ---------------------------------------------------------------------------
# Phase 2 — Dataset preview endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/api/datasets/preview",
    response_model=DatasetPreviewResponse,
    summary="Upload and profile a dataset",
    status_code=status.HTTP_200_OK,
)
async def preview_dataset(
    file: UploadFile = File(..., description="Excel (.xlsx) or CSV file"),
    sheet_name: Optional[str] = Form(
        default=None,
        description="Worksheet name (XLSX only; omit to use the first sheet)",
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DatasetPreviewResponse:
    """
    Accept a multipart upload of an Excel or CSV dataset.

    - Validates file type, size, row count, and column count against
      server-side limits.
    - Returns column names, inferred types, missing-value statistics,
      duplicate-row count, and a preview of the first N rows.
    - Processes files in memory — nothing is saved to disk.
    - Never executes macros or formulas.
    """
    raw: bytes = await file.read()
    filename: str = file.filename or "upload"

    # Server-side size check (before profiling, fast-fail)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size ({len(raw) / 1024 / 1024:.1f} MB) exceeds the "
                f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB upload limit."
            ),
        )

    try:
        result: dict = profile_dataset(
            filename=filename,
            raw=raw,
            sheet_name=sheet_name if sheet_name else None,
            max_upload_bytes=MAX_UPLOAD_BYTES,
            max_data_rows=MAX_DATA_ROWS,
            max_columns=MAX_COLUMNS,
            max_preview_rows=MAX_PREVIEW_ROWS,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except UnsupportedFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except InvalidSheetError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except (TooManyRowsError, TooManyColumnsError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except MalformedFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except DatasetError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception:
        # Do not expose internal stack traces to callers
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "An unexpected error occurred while processing the file.  "
                "Please try again or contact support if the problem persists."
            ),
        )

    return DatasetPreviewResponse(**result)


# ---------------------------------------------------------------------------
# Phase 4 — Dashboard data generation endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/api/datasets/dashboard",
    response_model=DashboardResponse,
    summary="Generate aggregated dashboard data and filter options",
    status_code=status.HTTP_200_OK,
)
async def generate_dashboard(
    file: UploadFile = File(..., description="Excel (.xlsx) or CSV file"),
    sheet_name: Optional[str] = Form(
        default=None,
        description="Worksheet name (XLSX only; omit to use the first sheet)",
    ),
    chart_configs: str = Form(
        ...,
        description="JSON array of confirmed ChartConfigInput objects",
    ),
    filters: Optional[str] = Form(
        default=None,
        description="Optional JSON object containing GlobalFilterInput",
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DashboardResponse:
    """
    Accepts full dataset bytes, confirmed chart configurations, and global filters.
    Applies filters, computes chart aggregations and summary statistics,
    and returns sanitized JSON payload ready for interactive chart rendering.
    """
    # 1. Parse JSON payloads
    try:
        raw_configs = json.loads(chart_configs)
        if not isinstance(raw_configs, list) or len(raw_configs) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one chart configuration is required to generate the dashboard.",
            )
        parsed_configs = [ChartConfigInput(**cfg) for cfg in raw_configs]
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Malformed chart_configs JSON payload: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid chart configuration payload: {exc}",
        ) from exc

    parsed_filters: Optional[GlobalFilterInput] = None
    if filters and filters.strip() and filters.strip() != "null":
        try:
            raw_filters = json.loads(filters)
            if isinstance(raw_filters, dict):
                parsed_filters = GlobalFilterInput(**raw_filters)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid filters payload: {exc}",
            ) from exc

    # 2. File size limit
    raw: bytes = await file.read()
    filename: str = file.filename or "upload"

    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size ({len(raw) / 1024 / 1024:.1f} MB) exceeds the "
                f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB upload limit."
            ),
        )

    # 3. Load & validate dataset
    try:
        df, column_profiles, selected_sheet, sheet_names, file_type = load_and_validate_dataset(
            filename=filename,
            raw=raw,
            sheet_name=sheet_name if sheet_name else None,
            max_upload_bytes=MAX_UPLOAD_BYTES,
            max_data_rows=MAX_DATA_ROWS,
            max_columns=MAX_COLUMNS,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except UnsupportedFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except InvalidSheetError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except (TooManyRowsError, TooManyColumnsError, MalformedFileError, DatasetError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while parsing the dataset for the dashboard.",
        )

    # 4. Generate dashboard calculations
    try:
        response = generate_dashboard_data(
            df=df,
            filename=filename,
            selected_sheet=selected_sheet,
            column_profiles=column_profiles,
            chart_configs=parsed_configs,
            filters=parsed_filters,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dashboard calculation error: {exc}",
        ) from exc

    return response


# ---------------------------------------------------------------------------
# Milestone 1 — Workbook scan endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/api/workbooks/scan",
    summary="Scan a workbook and return detected cell blocks with metadata",
    status_code=status.HTTP_200_OK,
)
async def scan_workbook_endpoint(
    file: UploadFile = File(..., description="Excel (.xlsx) or CSV file"),
    read_colours: Optional[str] = Form(
        default="false",
        description="Set to 'true' to read cell fill colours (slower; for action tracker sheets)",
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Any:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot scan or upload workbooks.",
        )
    """
    Accept a multipart upload and return worksheet names and detected cell blocks.

    Each block includes:
    - Sheet name and A1:C12-style source range
    - Block kind (tidy / wide / records / form)
    - Dimensions, bounded sample preview, and column names
    - Column role suggestions (date / measure / category / id / derived / text)
    - Notes, warnings, confidence score
    - Formula-cache warnings (if cached values are missing)
    - Ambiguous summary-row flags requiring user review
    - Cell fill colours (when read_colours=true)

    No data is persisted.  Temporary bytes are processed in memory only.
    The 10 MiB upload cap remains enforced until background workers are ready.
    """
    raw: bytes = await file.read()
    filename: str = file.filename or "upload"

    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size ({len(raw) / 1024 / 1024:.1f} MB) exceeds the "
                f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB upload limit."
            ),
        )

    want_colours = (read_colours or "").strip().lower() == "true"

    try:
        result: ScanResult = scan_workbook(
            raw=raw,
            filename=filename,
            read_colours=want_colours,
            max_upload_bytes=MAX_UPLOAD_BYTES,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        if "size" in msg and "limit" in msg:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=str(exc),
            ) from exc
        if "macro" in msg or ".xlsm" in msg:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(exc),
            ) from exc
        if "unsupported" in msg or ".xls" in msg or "format" in msg:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(exc),
            ) from exc
        if "password" in msg or "encrypted" in msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "An unexpected error occurred while scanning the workbook. "
                "Please try again or contact support."
            ),
        )

    return result.to_dict()


# ---------------------------------------------------------------------------
# Milestone 2 — Mapping templates and normalisation endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/workbooks/mapping",
    summary="Save and version a workbook mapping template",
    status_code=status.HTTP_200_OK,
    response_model=MappingTemplate,
)
async def save_mapping_template(
    template: MappingTemplate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MappingTemplate:
    """
    Save or update a workbook mapping template.
    If a template with the same ID already exists, its version number is incremented.
    Stored in JSON and synchronized to PostgreSQL with workspace ownership.
    """
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create or modify mapping templates.",
        )
    try:
        saved = template_storage.save_template(template)
        # Synchronize to PostgreSQL with workspace and owner association
        TemplateRepository(db).save(
            template_id=saved.id,
            name=saved.name,
            blocks_data=[b.model_dump() for b in saved.blocks],
            description=saved.description,
            source_of_truth=saved.source_of_truth.model_dump() if saved.source_of_truth else None,
            user_id=current_user.id,
            workspace_id=current_user.workspace_id,
        )
        return saved
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to save mapping template: {exc}",
        ) from exc


@app.get(
    "/api/workbooks/mappings",
    summary="List all saved workbook mapping templates",
    status_code=status.HTTP_200_OK,
    response_model=List[MappingTemplateSummary],
)
async def list_mapping_templates(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[MappingTemplateSummary]:
    """Return summary metadata for templates accessible in the current workspace."""
    t_repo = TemplateRepository(db)
    db_templates = t_repo.list_all(workspace_id=current_user.workspace_id)
    if db_templates:
        return [
            MappingTemplateSummary(
                id=t.id,
                name=t.name,
                version=t.version,
                created_at=t.created_at.isoformat() if t.created_at else "",
                updated_at=t.updated_at.isoformat() if t.updated_at else "",
                block_count=len(t.column_mapping.get("blocks", [])) if t.column_mapping else 0,
                description=t.description,
                source_of_truth_confirmed=bool(t.normalization_decisions.get("confirmed", False)) if t.normalization_decisions else False,
            )
            for t in db_templates
        ]
    return template_storage.list_templates()


@app.get(
    "/api/workbooks/mapping/{template_id}",
    summary="Retrieve a saved mapping template by ID",
    status_code=status.HTTP_200_OK,
    response_model=MappingTemplate,
)
async def get_mapping_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MappingTemplate:
    """Retrieve a mapping template by ID, verifying workspace authorization."""
    t_repo = TemplateRepository(db)
    t_db = t_repo.get(template_id)
    if t_db:
        verify_template_access(db, t_db, current_user, min_role="viewer")
        return MappingTemplate(
            id=t_db.id,
            name=t_db.name,
            version=t_db.version,
            description=t_db.description,
            blocks=t_db.column_mapping.get("blocks", []),
            source_of_truth=t_db.normalization_decisions if t_db.normalization_decisions else None,
        )

    template = template_storage.get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mapping template '{template_id}' not found.",
        )
    return template


@app.delete(
    "/api/workbooks/mapping/{template_id}",
    summary="Delete a saved mapping template by ID",
    status_code=status.HTTP_200_OK,
)
async def delete_mapping_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a mapping template by ID with editor permission check."""
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot delete mapping templates.",
        )
    t_repo = TemplateRepository(db)
    t_db = t_repo.get(template_id)
    if t_db:
        verify_template_access(db, t_db, current_user, min_role="editor")
        t_repo.delete(template_id)

    deleted = template_storage.delete_template(template_id)
    if not deleted and not t_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mapping template '{template_id}' not found.",
        )
    return {"status": "deleted", "id": template_id}


@app.post(
    "/api/workbooks/normalize",
    summary="Apply mapping template to workbook and return normalized tables",
    status_code=status.HTTP_200_OK,
    response_model=NormalizationResult,
)
async def normalize_workbook_endpoint(
    file: UploadFile = File(..., description="Excel (.xlsx) or CSV file"),
    template_json: Optional[str] = Form(
        default=None,
        description="JSON string of MappingTemplate",
    ),
    template_id: Optional[str] = Form(
        default=None,
        description="ID of a previously saved MappingTemplate",
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> NormalizationResult:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot execute workbook normalization.",
        )
    """
    Accepts a workbook and a mapping template (inline JSON or template_id),
    executes range trimming, unpivoting, ambiguous row routing, cell colour mapping,
    and value merges, and returns clean, normalized tabular datasets.
    """
    raw: bytes = await file.read()
    filename: str = file.filename or "upload"

    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size ({len(raw) / 1024 / 1024:.1f} MB) exceeds the "
                f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB upload limit."
            ),
        )

    # Resolve template
    template: Optional[MappingTemplate] = None
    if template_id:
        template = template_storage.get_template(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mapping template '{template_id}' not found.",
            )
    elif template_json:
        try:
            parsed = json.loads(template_json)
            template = MappingTemplate.model_validate(parsed)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid template JSON: {exc}",
            ) from exc
    else:
        # Default empty template (automatic defaults from scanner)
        template = MappingTemplate(
            name=f"Auto-generated for {filename}",
            description="Default mapping generated from workbook scanner",
        )

    try:
        result: NormalizationResult = normalize_workbook(
            raw=raw,
            filename=filename,
            template=template,
            max_upload_bytes=MAX_UPLOAD_BYTES,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Normalization error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Milestone 3: Asynchronous Ingestion, Datasets, and DuckDB Queries
# ---------------------------------------------------------------------------

@app.post(
    "/api/uploads",
    summary="Accept workbook upload asynchronously, stream to private storage, and enqueue background scan",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAcceptedResponse,
)
async def create_upload(
    file: UploadFile = File(..., description="Excel (.xlsx, .xls) or CSV file"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UploadAcceptedResponse:
    """
    Asynchronous upload ingestion:
    1. Enforces workspace editor role (viewers cannot upload).
    2. Validates file format and size limit.
    3. Streams workbook to private local filesystem storage (under opaque key).
    4. Persists metadata record with status 'queued' and workspace_id in PostgreSQL.
    5. Enqueues background Celery task (passing only upload UUID and storage key).
    6. Returns HTTP 202 immediately.
    """
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot upload workbooks.",
        )

    filename = file.filename or "upload"
    lower_name = filename.lower()
    valid_exts = (".xlsx", ".xls", ".csv")
    if not any(lower_name.endswith(ext) for ext in valid_exts):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format '{filename}'. Supported formats: .xlsx, .xls, .csv",
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size ({len(raw) / 1024 / 1024:.1f} MB) exceeds the "
                f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB upload limit."
            ),
        )

    ext = ".xlsx" if lower_name.endswith(".xlsx") else (".csv" if lower_name.endswith(".csv") else ".xls")
    sha256 = hashlib.sha256(raw).hexdigest()
    upload_id = uuid.uuid4()

    storage = get_storage_backend()
    storage_key = storage.generate_key("uploads", str(upload_id), ext)
    storage.put_object(storage_key, raw)

    upload_repo = UploadRepository(db)
    user_uuid = None
    if current_user and current_user.id:
        try:
            user_uuid = uuid.UUID(current_user.id)
        except (ValueError, TypeError):
            user_uuid = None

    sanitized = "".join(c for c in filename if c.isalnum() or c in "._- ")
    upload = upload_repo.create(
        upload_id=upload_id,
        user_id=user_uuid,
        workspace_id=current_user.workspace_id,
        original_filename=filename,
        sanitized_filename=sanitized,
        storage_key=storage_key,
        file_size_bytes=len(raw),
        file_type=ext.lstrip("."),
        sha256_hash=sha256,
    )

    # Enqueue background scan task (pass only upload ID and storage key, never raw bytes)
    try:
        from app.worker.tasks import scan_workbook_task
        scan_workbook_task.delay(str(upload_id), storage_key)
    except Exception as exc:
        logger.warning(f"Celery task dispatch fallback: {exc}. Running scan eagerly.")
        scan_workbook_task(str(upload_id), storage_key)

    return UploadAcceptedResponse(
        upload_id=str(upload_id),
        status="queued",
        original_filename=filename,
        file_size_bytes=len(raw),
        created_at=upload.created_at.isoformat() if upload.created_at else "",
        status_url=f"/api/uploads/{upload_id}",
    )


@app.get(
    "/api/uploads",
    summary="List paginated uploads for current workspace context",
    status_code=status.HTTP_200_OK,
    response_model=UploadListResponse,
)
async def list_uploads(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UploadListResponse:
    upload_repo = UploadRepository(db)
    dataset_repo = DatasetRepository(db)
    total = upload_repo.count(
        workspace_id=current_user.workspace_id,
        user_id=current_user.id if not current_user.workspace_id else None,
    )
    offset = max(0, (page - 1) * page_size)
    uploads = upload_repo.list_recent(
        limit=page_size,
        offset=offset,
        workspace_id=current_user.workspace_id,
        user_id=current_user.id if not current_user.workspace_id else None,
    )

    items = []
    for u in uploads:
        ds_count = dataset_repo.count_by_upload(u.id)
        items.append(
            UploadSummary(
                upload_id=str(u.id),
                original_filename=u.original_filename,
                sanitized_filename=u.sanitized_filename,
                file_size_bytes=u.file_size_bytes,
                file_type=u.file_type,
                status=u.status,
                stage=u.stage,
                progress=u.progress,
                error_code=u.error_code,
                error_message=u.error_message,
                dataset_count=ds_count,
                created_at=u.created_at.isoformat() if u.created_at else "",
                updated_at=u.updated_at.isoformat() if u.updated_at else "",
            )
        )
    return UploadListResponse(items=items, total=total, page=page, page_size=page_size)


@app.get(
    "/api/uploads/{upload_id}",
    summary="Get upload status, processing stage, and progress metadata",
    status_code=status.HTTP_200_OK,
    response_model=UploadSummary,
)
async def get_upload_status(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UploadSummary:
    upload_repo = UploadRepository(db)
    u = upload_repo.get(upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{upload_id}' not found.",
        )
    verify_upload_access(db, u, current_user, min_role="viewer")

    dataset_repo = DatasetRepository(db)
    ds_count = dataset_repo.count_by_upload(u.id)
    return UploadSummary(
        upload_id=str(u.id),
        original_filename=u.original_filename,
        sanitized_filename=u.sanitized_filename,
        file_size_bytes=u.file_size_bytes,
        file_type=u.file_type,
        status=u.status,
        stage=u.stage,
        progress=u.progress,
        error_code=u.error_code,
        error_message=u.error_message,
        dataset_count=ds_count,
        created_at=u.created_at.isoformat() if u.created_at else "",
        updated_at=u.updated_at.isoformat() if u.updated_at else "",
    )


@app.get(
    "/api/uploads/{upload_id}/datasets",
    summary="List detected and normalized datasets for an upload",
    status_code=status.HTTP_200_OK,
    response_model=List[DatasetSummaryResponse],
)
async def list_upload_datasets(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[DatasetSummaryResponse]:
    upload_repo = UploadRepository(db)
    u = upload_repo.get(upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{upload_id}' not found.",
        )
    verify_upload_access(db, u, current_user, min_role="viewer")

    dataset_repo = DatasetRepository(db)
    datasets = dataset_repo.list_by_upload(u.id)

    results = []
    for d in datasets:
        results.append(
            DatasetSummaryResponse(
                dataset_id=str(d.id),
                upload_id=str(d.upload_id),
                sheet_name=d.sheet_name,
                cell_range=d.cell_range,
                kind=d.kind,
                column_metadata=d.column_metadata or [],
                normalization_status=d.normalization_status,
                parquet_storage_key=d.parquet_storage_key,
                row_count=d.row_count,
                column_count=d.column_count,
                summary_metadata=d.summary_metadata or {},
            )
        )
    return results


@app.get(
    "/api/uploads/{upload_id}/scan",
    summary="Return the persisted bounded scan result for an upload",
    status_code=status.HTTP_200_OK,
)
async def get_persisted_scan(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Expose the worker's scan metadata without rescanning the workbook.

    The upload pipeline owns scanning.  Keeping this read endpoint backed by
    persisted dataset metadata prevents the browser from issuing a second,
    independent scan request for the same file.
    """
    upload_repo = UploadRepository(db)
    upload = upload_repo.get(upload_id)
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Upload '{upload_id}' not found.")
    verify_upload_access(db, upload, current_user, min_role="viewer")

    datasets = DatasetRepository(db).list_by_upload(upload.id)
    blocks: list[dict[str, Any]] = []
    global_warnings: list[str] = []
    for dataset in datasets:
        meta = dataset.summary_metadata or {}
        column_metadata = dataset.column_metadata or []
        warnings = list(meta.get("warnings") or [])
        global_warnings.extend(warnings)
        blocks.append({
            "sheet": dataset.sheet_name,
            "range": dataset.cell_range,
            "kind": dataset.kind,
            "confidence": float(meta.get("confidence") or 0),
            "dimensions": {"rows": dataset.row_count, "cols": dataset.column_count},
            "column_names": [c.get("name", "") for c in column_metadata],
            "column_roles": {c.get("name", ""): c.get("role", "text") for c in column_metadata},
            "sample_preview": meta.get("sample_preview") or [],
            "notes": meta.get("notes") or [],
            "warnings": warnings,
            "formula_cache_warning": bool(meta.get("formula_cache_warning")),
            "cap_reached": bool(meta.get("cap_reached")),
            "ambiguous_row_count": len(meta.get("ambiguous_rows") or []),
            "ambiguous_rows": meta.get("ambiguous_rows") or [],
            "cell_colours": meta.get("cell_colours") or [],
            "has_summary": bool(meta.get("has_summary")),
        })
    return {
        "filename": upload.original_filename,
        "sheet_names": list(dict.fromkeys(d.sheet_name for d in datasets)),
        "block_count": len(blocks),
        "cap_reached": any(b["cap_reached"] for b in blocks),
        "global_warnings": list(dict.fromkeys(global_warnings)),
        "blocks": blocks,
    }


@app.post(
    "/api/uploads/{upload_id}/normalize",
    summary="Enqueue asynchronous normalisation to Parquet for an upload",
    status_code=status.HTTP_202_ACCEPTED,
)
async def normalize_upload_async(
    upload_id: str,
    template_json: Optional[str] = Form(default=None),
    template_id: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    upload_repo = UploadRepository(db)
    u = upload_repo.get(upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{upload_id}' not found.",
        )
    verify_upload_access(db, u, current_user, min_role="editor")

    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot normalize uploads.",
        )

    template: Optional[MappingTemplate] = None
    if template_id:
        template = template_storage.get_template(template_id)
        if not template:
            # Check DB
            t_db = TemplateRepository(db).get(template_id)
            if t_db:
                template = MappingTemplate(
                    id=t_db.id,
                    name=t_db.name,
                    version=t_db.version,
                    description=t_db.description,
                    blocks=t_db.column_mapping.get("blocks", []),
                )
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mapping template '{template_id}' not found.",
            )
    elif template_json:
        try:
            parsed = json.loads(template_json)
            template = MappingTemplate.model_validate(parsed)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid template JSON: {exc}",
            ) from exc
    else:
        template = MappingTemplate(
            name=f"Auto-generated for {u.original_filename}",
            description="Default mapping generated from workbook scanner",
        )

    try:
        from app.worker.tasks import normalize_workbook_task
        normalize_workbook_task.delay(str(u.id), u.storage_key, template.model_dump())
    except Exception as exc:
        logger.warning(f"Celery dispatch fallback: {exc}. Running normalize eagerly.")
        normalize_workbook_task(str(u.id), u.storage_key, template.model_dump())

    return {"upload_id": str(u.id), "status": "normalizing"}


@app.post(
    "/api/uploads/{upload_id}/retry",
    summary="Retry a failed workbook processing job",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_failed_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    upload_repo = UploadRepository(db)
    u = upload_repo.get(upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{upload_id}' not found.",
        )
    verify_upload_access(db, u, current_user, min_role="editor")

    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot retry uploads.",
        )

    if u.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload '{upload_id}' is in status '{u.status}'. Only 'failed' uploads can be retried.",
        )

    upload_repo.update_status(
        u.id,
        status="queued",
        stage="retry_queued",
        progress=0,
        error_code=None,
        error_message=None,
    )

    try:
        from app.worker.tasks import scan_workbook_task
        scan_workbook_task.delay(str(u.id), u.storage_key)
    except Exception as exc:
        logger.warning(f"Celery dispatch fallback: {exc}. Running scan eagerly.")
        scan_workbook_task(str(u.id), u.storage_key)

    return {"upload_id": str(u.id), "status": "queued"}


@app.post(
    "/api/query",
    summary="Execute validated, parameterized DuckDB query on normalized Parquet dataset",
    status_code=status.HTTP_200_OK,
)
async def execute_query(
    plan: QueryPlan,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    dataset_repo = DatasetRepository(db)
    ds = dataset_repo.get(plan.dataset_id)
    if not ds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{plan.dataset_id}' not found.",
        )
    upload_repo = UploadRepository(db)
    u = upload_repo.get(ds.upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated upload not found.",
        )
    verify_upload_access(db, u, current_user, min_role="viewer")

    if not ds.parquet_storage_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset '{plan.dataset_id}' has not been normalized into Parquet yet.",
        )

    storage = get_storage_backend()
    if not storage.object_exists(ds.parquet_storage_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parquet dataset '{ds.parquet_storage_key}' not found in storage.",
        )

    try:
        result = execute_query_plan(plan, storage, ds)
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution error: {exc}",
        )


# ---------------------------------------------------------------------------
# Milestone 4: Manufacturing Quality Dashboards & Specification Persistence
# ---------------------------------------------------------------------------

class ManufacturingGenerateRequest(BaseModel):
    upload_id: str
    template_name: Optional[str] = "Manufacturing Quality Dashboard"
    source_of_truth_confirmed: bool = False
    source_of_truth_choice: Optional[str] = None
    target_ppm: float = 2000.0


class PersistDashboardRequest(BaseModel):
    upload_id: str
    title: str
    spec: Dict[str, Any]
    template_id: Optional[str] = None


class DashboardFilterQueryRequest(BaseModel):
    filters: Optional[ManufacturingGlobalFilter] = None


class RenameDashboardRequest(BaseModel):
    title: str


class DuplicateDashboardRequest(BaseModel):
    title: Optional[str] = None


class CreateExportRequest(BaseModel):
    format: str
    options: Optional[Dict[str, Any]] = None


@app.post(
    "/api/dashboards/manufacturing/generate",
    summary="Generate manufacturing quality dashboard from normalized Parquet datasets",
    status_code=status.HTTP_200_OK,
)
async def generate_manufacturing_dashboard(
    req: ManufacturingGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    upload_repo = UploadRepository(db)
    u = upload_repo.get(req.upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{req.upload_id}' not found.",
        )
    verify_upload_access(db, u, current_user, min_role="viewer")

    dataset_repo = DatasetRepository(db)
    datasets = dataset_repo.list_by_upload(u.id)
    if not datasets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No datasets detected for upload '{req.upload_id}'. Please scan and normalize first.",
        )

    # Check for Parquet files
    storage = get_storage_backend()
    valid_datasets = [d for d in datasets if d.parquet_storage_key and storage.object_exists(d.parquet_storage_key)]
    if not valid_datasets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload '{req.upload_id}' has not been normalized into Parquet datasets yet.",
        )

    # Build Manufacturing Dashboard Specification
    spec = build_manufacturing_dashboard_spec(
        upload_id=str(u.id),
        datasets=valid_datasets,
        template_name=req.template_name or f"Quality Dashboard ({u.original_filename})",
        source_of_truth_confirmed=req.source_of_truth_confirmed,
        source_of_truth_choice=req.source_of_truth_choice,
        confirmed_target_ppm=req.target_ppm,
    )

    # Render each widget
    ds_lookup = {str(d.id): d for d in valid_datasets}
    rendered_widgets = []
    distinct_periods = set()
    distinct_models = set()
    distinct_defects = set()
    distinct_owners = set()
    distinct_statuses = set()

    for widget in spec.widgets:
        target_ds = ds_lookup.get(widget.dataset_id)
        if not target_ds:
            continue
        try:
            rendered = execute_manufacturing_widget(
                widget=widget,
                storage=storage,
                dataset=target_ds,
                filters=None,
                source_of_truth_confirmed=req.source_of_truth_confirmed,
            )
            rendered_widgets.append(rendered)

            # Collect distinct filter options from rendered results
            if widget.widget_type == "ppm_trend_target":
                for pt in rendered.get("data_points", []):
                    if pt.get("period"):
                        distinct_periods.add(pt["period"])
            elif widget.widget_type == "defect_pareto":
                for it in rendered.get("items", []):
                    if it.get("category"):
                        distinct_defects.add(it["category"])
            elif widget.widget_type == "paynter_heatmap":
                for p in rendered.get("x_categories", []):
                    distinct_periods.add(p)
                for d in rendered.get("y_categories", []):
                    distinct_defects.add(d)
            elif widget.widget_type == "action_tracker":
                for o in rendered.get("owner_counts", {}).keys():
                    distinct_owners.add(o)
                for s in rendered.get("status_counts", {}).keys():
                    distinct_statuses.add(s)
            elif widget.widget_type == "model_comparison":
                for m in rendered.get("models", []):
                    distinct_models.add(m)
        except Exception as exc:
            logger.warning(f"Error rendering widget '{widget.widget_id}': {exc}")
            rendered_widgets.append(
                {
                    "widget_id": widget.widget_id,
                    "widget_type": widget.widget_type,
                    "title": widget.title,
                    "error": str(exc),
                    "provenance": widget.provenance.model_dump(),
                    "warnings": [f"Widget query failed: {exc}"],
                }
            )

    spec.available_filters = {
        "periods": sorted(list(distinct_periods)),
        "models": sorted(list(distinct_models)),
        "defects": sorted(list(distinct_defects)),
        "action_owners": sorted(list(distinct_owners)),
        "action_statuses": sorted(list(distinct_statuses)),
    }

    return {
        "spec": spec.model_dump(),
        "rendered_widgets": rendered_widgets,
        "available_filters": spec.available_filters,
        "reconciliation": spec.reconciliation.model_dump(),
        "status": "ready",
    }


@app.post(
    "/api/dashboards",
    summary="Save manufacturing dashboard specification against normalized datasets in PostgreSQL",
    status_code=status.HTTP_201_CREATED,
)
async def create_or_save_dashboard(
    req: PersistDashboardRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create or save dashboards.",
        )

    upload_repo = UploadRepository(db)
    u = upload_repo.get(req.upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{req.upload_id}' not found.",
        )
    verify_upload_access(db, u, current_user, min_role="editor")

    dash_repo = DashboardRepository(db)
    dash = dash_repo.create(
        upload_id=u.id,
        title=req.title,
        spec=req.spec,
        template_id=req.template_id,
        user_id=uuid.UUID(current_user.id) if hasattr(current_user, "id") and current_user.id else None,
        workspace_id=current_user.workspace_id,
    )

    return {
        "id": str(dash.id),
        "upload_id": str(dash.upload_id),
        "title": dash.title,
        "spec": dash.spec,
        "template_id": dash.template_id,
        "created_at": dash.created_at.isoformat() if dash.created_at else "",
    }


@app.get(
    "/api/dashboards/{dashboard_id}",
    summary="Reopen and recalculate manufacturing dashboard from stored datasets using DuckDB",
    status_code=status.HTTP_200_OK,
)
async def get_dashboard(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    dash_repo = DashboardRepository(db)
    dash = dash_repo.get(dashboard_id)
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{dashboard_id}' not found.",
        )
    verify_dashboard_access(db, dash, current_user, min_role="viewer")

    dataset_repo = DatasetRepository(db)
    datasets = dataset_repo.list_by_upload(dash.upload_id)
    storage = get_storage_backend()
    ds_lookup = {str(d.id): d for d in datasets if d.parquet_storage_key and storage.object_exists(d.parquet_storage_key)}

    spec_dict = dash.spec or {}
    rendered_widgets = []
    raw_widgets = spec_dict.get("widgets", [])
    sot_confirmed = spec_dict.get("source_of_truth_confirmed", False)

    for w_dict in raw_widgets:
        try:
            widget = ManufacturingWidgetSpec.model_validate(w_dict)
            target_ds = ds_lookup.get(widget.dataset_id)
            if target_ds:
                rendered = execute_manufacturing_widget(
                    widget=widget,
                    storage=storage,
                    dataset=target_ds,
                    filters=None,
                    source_of_truth_confirmed=sot_confirmed,
                )
                rendered_widgets.append(rendered)
        except Exception as exc:
            logger.warning(f"Error recalculating widget: {exc}")

    return {
        "id": str(dash.id),
        "upload_id": str(dash.upload_id),
        "title": dash.title,
        "spec": dash.spec,
        "rendered_widgets": rendered_widgets,
        "available_filters": spec_dict.get("available_filters", {}),
        "reconciliation": spec_dict.get("reconciliation", {}),
        "created_at": dash.created_at.isoformat() if dash.created_at else "",
        "updated_at": dash.updated_at.isoformat() if dash.updated_at else "",
    }


@app.post(
    "/api/dashboards/{dashboard_id}/query",
    summary="Query manufacturing dashboard with active global filters",
    status_code=status.HTTP_200_OK,
)
async def query_dashboard_widgets(
    dashboard_id: str,
    req: DashboardFilterQueryRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    dash_repo = DashboardRepository(db)
    dash = dash_repo.get(dashboard_id)
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{dashboard_id}' not found.",
        )
    verify_dashboard_access(db, dash, current_user, min_role="viewer")

    dataset_repo = DatasetRepository(db)
    datasets = dataset_repo.list_by_upload(dash.upload_id)
    storage = get_storage_backend()
    ds_lookup = {str(d.id): d for d in datasets if d.parquet_storage_key and storage.object_exists(d.parquet_storage_key)}

    spec_dict = dash.spec or {}
    raw_widgets = spec_dict.get("widgets", [])
    sot_confirmed = spec_dict.get("source_of_truth_confirmed", False)
    rendered_widgets = []

    for w_dict in raw_widgets:
        try:
            widget = ManufacturingWidgetSpec.model_validate(w_dict)
            target_ds = ds_lookup.get(widget.dataset_id)
            if target_ds:
                rendered = execute_manufacturing_widget(
                    widget=widget,
                    storage=storage,
                    dataset=target_ds,
                    filters=req.filters,
                    source_of_truth_confirmed=sot_confirmed,
                )
                rendered_widgets.append(rendered)
        except Exception as exc:
            logger.warning(f"Error filtering widget '{w_dict.get('widget_id')}': {exc}")

    return {
        "dashboard_id": str(dash.id),
        "rendered_widgets": rendered_widgets,
        "filters": req.filters.model_dump() if req.filters else None,
    }


@app.get(
    "/api/dashboards",
    summary="List saved dashboards accessible in current workspace",
    status_code=status.HTTP_200_OK,
)
async def list_dashboards(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[dict[str, Any]]:
    dash_repo = DashboardRepository(db)
    upload_repo = UploadRepository(db)
    dashboards = dash_repo.list_recent(
        limit=limit,
        workspace_id=current_user.workspace_id,
        user_id=current_user.id if not current_user.workspace_id else None,
    )
    result = []
    for d in dashboards:
        u = upload_repo.get(d.upload_id) if d.upload_id else None
        result.append({
            "id": str(d.id),
            "upload_id": str(d.upload_id) if d.upload_id else "",
            "title": d.title,
            "template_id": d.template_id,
            "source_filename": u.original_filename if u else "Manufacturing Workbook",
            "created_at": d.created_at.isoformat() if d.created_at else "",
            "updated_at": d.updated_at.isoformat() if d.updated_at else "",
        })
    return result


@app.patch(
    "/api/dashboards/{dashboard_id}",
    summary="Rename a saved manufacturing dashboard",
    status_code=status.HTTP_200_OK,
)
async def rename_dashboard(
    dashboard_id: str,
    req: RenameDashboardRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot rename dashboards.",
        )
    dash_repo = DashboardRepository(db)
    dash = dash_repo.get(dashboard_id)
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{dashboard_id}' not found.",
        )
    verify_dashboard_access(db, dash, current_user, min_role="editor")
    new_title = req.title.strip()
    if not new_title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dashboard title cannot be empty.",
        )
    dash.title = new_title
    dash.updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(dash)
    return {
        "id": str(dash.id),
        "upload_id": str(dash.upload_id) if dash.upload_id else "",
        "title": dash.title,
        "template_id": dash.template_id,
        "created_at": dash.created_at.isoformat() if dash.created_at else "",
        "updated_at": dash.updated_at.isoformat() if dash.updated_at else "",
    }


@app.post(
    "/api/dashboards/{dashboard_id}/duplicate",
    summary="Duplicate a dashboard configuration within workspace",
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_dashboard(
    dashboard_id: str,
    req: Optional[DuplicateDashboardRequest] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot duplicate dashboards.",
        )
    dash_repo = DashboardRepository(db)
    dash = dash_repo.get(dashboard_id)
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{dashboard_id}' not found.",
        )
    verify_dashboard_access(db, dash, current_user, min_role="editor")
    new_title = (req.title.strip() if req and req.title and req.title.strip() else f"Copy of {dash.title}")
    dup = dash_repo.duplicate(
        dashboard_id=dashboard_id,
        new_title=new_title,
        user_id=uuid.UUID(current_user.id) if hasattr(current_user, "id") and current_user.id else None,
        workspace_id=current_user.workspace_id,
    )
    return {
        "id": str(dup.id),
        "upload_id": str(dup.upload_id) if dup.upload_id else "",
        "title": dup.title,
        "spec": dup.spec,
        "template_id": dup.template_id,
        "created_at": dup.created_at.isoformat() if dup.created_at else "",
        "updated_at": dup.updated_at.isoformat() if dup.updated_at else "",
    }


@app.delete(
    "/api/dashboards/{dashboard_id}",
    summary="Delete a saved manufacturing dashboard",
    status_code=status.HTTP_200_OK,
)
async def delete_dashboard(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot delete dashboards.",
        )
    dash_repo = DashboardRepository(db)
    dash = dash_repo.get(dashboard_id)
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{dashboard_id}' not found.",
        )
    verify_dashboard_access(db, dash, current_user, min_role="editor")
    dash_repo.delete(dashboard_id)
    return {"message": f"Dashboard '{dashboard_id}' deleted successfully."}


@app.delete(
    "/api/datasets/{dataset_id}",
    summary="Delete a detected or normalized dataset",
    status_code=status.HTTP_200_OK,
)
async def delete_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot delete datasets.",
        )
    dataset_repo = DatasetRepository(db)
    ds = dataset_repo.get(dataset_id)
    if not ds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found.",
        )
    upload_repo = UploadRepository(db)
    u = upload_repo.get(ds.upload_id)
    if u:
        verify_upload_access(db, u, current_user, min_role="editor")

    storage = get_storage_backend()
    if ds.parquet_storage_key and storage.object_exists(ds.parquet_storage_key):
        try:
            storage.delete_object(ds.parquet_storage_key)
        except Exception as exc:
            logger.warning(f"Failed to delete parquet storage file {ds.parquet_storage_key}: {exc}")

    db.delete(ds)
    db.commit()
    return {"message": f"Dataset '{dataset_id}' deleted successfully."}


@app.delete(
    "/api/uploads/{upload_id}",
    summary="Delete an upload and its associated files and datasets",
    status_code=status.HTTP_200_OK,
)
async def delete_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot delete uploads.",
        )
    upload_repo = UploadRepository(db)
    u = upload_repo.get(upload_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload '{upload_id}' not found.",
        )
    verify_upload_access(db, u, current_user, min_role="editor")

    storage = get_storage_backend()
    if u.storage_key and storage.object_exists(u.storage_key):
        try:
            storage.delete_object(u.storage_key)
        except Exception as exc:
            logger.warning(f"Failed to delete raw storage file {u.storage_key}: {exc}")

    # Clean up parquet files for all datasets in this upload
    dataset_repo = DatasetRepository(db)
    datasets = dataset_repo.list_by_upload(u.id)
    for ds in datasets:
        if ds.parquet_storage_key and storage.object_exists(ds.parquet_storage_key):
            try:
                storage.delete_object(ds.parquet_storage_key)
            except Exception:
                pass

    db.delete(u)
    db.commit()
    return {"message": f"Upload '{upload_id}' deleted successfully."}


# ---------------------------------------------------------------------------
# Milestone 6: Report Exports & Hardened History Endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/dashboards/{dashboard_id}/exports",
    summary="Queue dashboard export (PDF, PNG, Excel, CSV)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_dashboard_export(
    dashboard_id: str,
    req: CreateExportRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    fmt = (req.format or "").lower().strip()
    if fmt not in ("pdf", "png", "xlsx", "csv", "pptx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported export format '{req.format}'. Supported: pdf, png, xlsx, csv",
        )

    # Export permission enforcement: Viewers may only export visual formats (PDF, PNG)
    if current_user.workspace_role == "viewer" and fmt in ("xlsx", "csv"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers are restricted to visual exports (PDF, PNG). Excel and CSV exports require editor or admin privileges.",
        )

    dash_repo = DashboardRepository(db)
    dash = dash_repo.get(dashboard_id)
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{dashboard_id}' not found.",
        )
    verify_dashboard_access(db, dash, current_user, min_role="viewer")

    export_repo = ExportRepository(db)
    export_id = uuid.uuid4()
    storage_key = f"exports/{export_id}/export.{fmt}"

    export = export_repo.create(
        dashboard_id=dash.id,
        format=fmt,
        user_id=uuid.UUID(current_user.id) if hasattr(current_user, "id") and current_user.id else None,
        workspace_id=current_user.workspace_id or dash.workspace_id,
        storage_key=storage_key,
        options=req.options or {},
    )

    # Queue export task in Celery worker (or execute inline if eager / test mode)
    is_eager = (
        os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() in ("true", "1")
        or os.getenv("BYPASS_CSRF_FOR_TESTS") == "true"
    )
    if is_eager:
        from app.exports.generator import generate_export
        generate_export(db, str(export.id), get_storage_backend())
    else:
        try:
            from app.worker.tasks import generate_export_task
            generate_export_task.delay(export_id=str(export.id))
        except Exception as exc:
            logger.warning(f"Celery dispatch failed or redis offline ({exc}); executing export inline.")
            from app.exports.generator import generate_export
            generate_export(db, str(export.id), get_storage_backend())

    # Refresh export to return latest status
    db.refresh(export)

    return {
        "id": str(export.id),
        "dashboard_id": str(export.dashboard_id),
        "format": export.format,
        "status": export.status,
        "storage_key": export.storage_key,
        "created_at": export.created_at.isoformat() if export.created_at else "",
    }


@app.get(
    "/api/exports/{export_id}",
    summary="Get export processing status and metadata",
    status_code=status.HTTP_200_OK,
)
async def get_export_status(
    export_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    export_repo = ExportRepository(db)
    export = export_repo.get(export_id)
    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export '{export_id}' not found.",
        )
    if export.workspace_id and current_user.workspace_id and str(export.workspace_id) != str(current_user.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to export from another workspace.",
        )

    is_ready = export.status in ("ready", "completed")
    return {
        "id": str(export.id),
        "dashboard_id": str(export.dashboard_id),
        "format": export.format,
        "status": export.status,
        "file_size_bytes": export.file_size_bytes,
        "error_code": export.error_code,
        "error_message": export.error_message,
        "created_at": export.created_at.isoformat() if export.created_at else "",
        "completed_at": export.completed_at.isoformat() if export.completed_at else "",
        "download_url": f"/api/exports/{export.id}/download" if is_ready else None,
    }


@app.get(
    "/api/exports/{export_id}/download",
    summary="Download generated export file",
    status_code=status.HTTP_200_OK,
)
async def download_export(
    export_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    export_repo = ExportRepository(db)
    export = export_repo.get(export_id)
    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export '{export_id}' not found.",
        )
    if export.workspace_id and current_user.workspace_id and str(export.workspace_id) != str(current_user.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to export from another workspace.",
        )
    if export.status not in ("ready", "completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export is not ready for download (current status: '{export.status}').",
        )

    storage = get_storage_backend()
    if not export.storage_key or not storage.object_exists(export.storage_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found in local private storage.",
        )

    local_path = storage.get_local_path(export.storage_key)
    media_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    media_type = media_types.get(export.format, "application/octet-stream")
    filename = f"report_{export.dashboard_id}_{export.format}.{export.format}"

    return FileResponse(
        path=str(local_path),
        media_type=media_type,
        filename=filename,
    )


@app.get(
    "/api/dashboards/{dashboard_id}/exports",
    summary="List authorized exports for a dashboard",
    status_code=status.HTTP_200_OK,
)
async def list_dashboard_exports(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[dict[str, Any]]:
    dash_repo = DashboardRepository(db)
    dash = dash_repo.get(dashboard_id)
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard '{dashboard_id}' not found.",
        )
    verify_dashboard_access(db, dash, current_user, min_role="viewer")

    export_repo = ExportRepository(db)
    exports = export_repo.list_by_dashboard(dash.id)
    return [
        {
            "id": str(e.id),
            "dashboard_id": str(e.dashboard_id),
            "format": e.format,
            "status": e.status,
            "file_size_bytes": e.file_size_bytes,
            "error_code": e.error_code,
            "error_message": e.error_message,
            "created_at": e.created_at.isoformat() if e.created_at else "",
            "completed_at": e.completed_at.isoformat() if e.completed_at else "",
            "download_url": f"/api/exports/{e.id}/download" if e.status in ("ready", "completed") else None,
        }
        for e in exports
    ]


@app.delete(
    "/api/exports/{export_id}",
    summary="Delete an export record and its stored file",
    status_code=status.HTTP_200_OK,
)
async def delete_export(
    export_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    if current_user.workspace_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot delete exports.",
        )
    export_repo = ExportRepository(db)
    export = export_repo.get(export_id)
    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export '{export_id}' not found.",
        )
    if export.workspace_id and current_user.workspace_id and str(export.workspace_id) != str(current_user.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to export from another workspace.",
        )

    storage = get_storage_backend()
    if export.storage_key and storage.object_exists(export.storage_key):
        try:
            storage.delete_object(export.storage_key)
        except Exception as exc:
            logger.warning(f"Failed to delete export storage file: {exc}")

    export_repo.delete(export.id)
    return {"message": f"Export '{export_id}' deleted successfully."}


