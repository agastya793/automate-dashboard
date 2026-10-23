"""
Business Reporting Dashboard - Backend API Service

Phase 1: Health check + CORS
Phase 2: POST /api/datasets/preview — multipart upload, dataset profiling

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

import json
import os
from typing import Any, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth import AuthenticatedUser, get_current_user
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


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
