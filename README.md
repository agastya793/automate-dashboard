# Automated Business Reporting Dashboard

An automated, verifiable manufacturing quality reporting platform. Ingest complex Excel workbooks and CSV files, detect multi-table blocks, unpivot wide monthly rejection ledgers, normalize data into Parquet datasets, execute deterministic DuckDB analytical queries, and generate interactive Apache ECharts manufacturing dashboards with strict provenance and reconciliation safeguards.

Enterprise security is enforced natively using FastAPI, Argon2id password hashing, server-side PostgreSQL sessions, double-submit CSRF protection, and multi-tenant workspace role-based access control (RBAC).

---

## Architecture Overview

- **Frontend**: Next.js 16 (App Router), React 19, TypeScript (Strict Mode), Tailwind CSS, Lucide React, Apache ECharts v5.
- **Backend API**: Python FastAPI, Pydantic v2, Pandas, OpenPyXL, Argon2id (`argon2-cffi`), secrets module.
- **Metadata Database**: PostgreSQL 16 + SQLAlchemy 2.x + Alembic migrations (`users`, `sessions`, `workspaces`, `workspace_members`, `uploads`, `datasets`, `templates`, `dashboards`, `exports`).
- **Private Storage**: Private local filesystem storage (`STORAGE_BACKEND=local`, `backend/data/storage/`) with atomic writes and path-traversal prevention. Zero public URLs.
- **Analytical Engine**: DuckDB executing parameterized `QueryPlan` calculations directly over normalized Parquet datasets.
- **Background Pipeline**: Redis 7 + Celery asynchronous workers with thread-safe eager local fallback.
- **Security & Authorization**:
  - Argon2id password hashing with timing-safe verification.
  - 256-bit entropy opaque session tokens stored strictly as SHA-256 hashes in PostgreSQL.
  - HTTP-only session cookies (`SameSite=Lax`, `Secure` in production).
  - Double-submit CSRF tokens (`csrf_token` cookie + `X-CSRF-Token` header) and exact `Origin`/`Referer` allowlisting.
  - Multi-tenant workspace isolation with role enforcement (`admin`, `editor`, `viewer`).
  - Production startup guard that aborts startup if development bypass mode is enabled in production.

---

## Directory Structure

```
business-reporting-dashboard/
├── frontend/
│   ├── app/
│   │   ├── globals.css              # Base styling & design tokens
│   │   ├── layout.tsx               # App shell, AuthProvider & DashboardProvider
│   │   ├── page.tsx                 # Overview dashboard
│   │   ├── login/page.tsx           # Email/password authentication sign in
│   │   ├── signup/page.tsx          # Account registration with workspace provisioning
│   │   ├── forgot-password/page.tsx # Password recovery instructions & admin guide
│   │   ├── reset-password/page.tsx  # Password reset notification
│   │   ├── upload/page.tsx          # Spreadsheet ingestion, scan & normalization
│   │   ├── dashboard/page.tsx       # Manufacturing dashboards with Apache ECharts
│   │   ├── reports/page.tsx         # Saved reports catalog
│   │   └── settings/page.tsx        # Workspace preferences & security info
│   ├── components/
│   │   ├── Sidebar.tsx              # Sidebar with workspace switcher & role badge
│   │   ├── Header.tsx               # Top header
│   │   ├── EChartsWrapper.tsx       # Lifecycle-safe Apache ECharts client component
│   │   ├── TrendTargetChart.tsx     # Monthly Rejection PPM vs Target
│   │   ├── ParetoChart.tsx          # Dual-axis Defect Pareto (0-100% cumulative)
│   │   ├── PaynterHeatmap.tsx       # Defect/Model Paynter Heatmap
│   │   ├── ActionTracker.tsx        # Corrective Action Tracker with status KPIs
│   │   ├── ModelComparisonChart.tsx # Grouped/Stacked model quantities
│   │   ├── ProvenanceModal.tsx      # KPI formula, source cell & lineage modal
│   │   ├── ReconciliationBanner.tsx # Blueprint reference PPM verification banner
│   │   └── WorkbookMappingWorkspace.tsx # Interactive table mapping workspace
│   ├── context/
│   │   ├── AuthContext.tsx          # FastAPI session auth, workspaces & active role
│   │   └── DashboardContext.tsx     # Dataset, dashboard state & DuckDB query runner
│   ├── lib/
│   │   ├── api.ts                   # Centralized apiFetch with credentials & CSRF
│   │   └── mappingTypes.ts          # TypeScript interfaces for scanner & templates
│   └── package.json
├── backend/
│   ├── alembic/                     # Database migrations
│   │   └── versions/
│   │       ├── 001_initial_schema.py
│   │       └── 002_auth_workspaces.py
│   ├── app/
│   │   ├── main.py                  # FastAPI application & protected endpoints
│   │   ├── auth.py                  # Argon2id, session tokens, CSRF & RBAC policies
│   │   ├── rate_limiter.py          # Sliding-window rate limiter (Redis / in-memory)
│   │   ├── db/                      # SQLAlchemy models, sessions & repositories
│   │   ├── ingestion/               # Scanner, mapping models & normalization engine
│   │   ├── dashboard_engine/        # Manufacturing templates, DuckDB & reconciliation
│   │   ├── storage/                 # Private filesystem storage abstraction
│   │   └── worker/                  # Celery worker & background ingestion tasks
│   ├── tests/                       # 217 comprehensive tests
│   └── requirements.txt
├── infra/
│   └── docker-compose.yml           # Local PostgreSQL 16 & Redis 7
├── sample_data/                     # Synthetic test spreadsheets
└── README.md
```

---

## Authentication & Authorization Model

### 1. Registration & Provisioning
- When a user registers (`POST /api/auth/register`), passwords are validated for strength (minimum 8 characters with letters and numbers/special characters) and hashed using Argon2id.
- An initial profile and a private default workspace (`<Name>'s Workspace`) are created automatically.
- The user is assigned the `admin` role in their own default workspace.
- A 256-bit entropy session token is generated, its SHA-256 hash is recorded in PostgreSQL, and an HTTP-only `session_token` cookie is set along with a client-readable `csrf_token` cookie.

### 2. Login & Session Management
- `POST /api/auth/login` verifies credentials against the Argon2id hash with timing-safe checks.
- On success, any existing session is rotated, and a new session with an expiration timestamp (`SESSION_LIFETIME_SECONDS`, default 24h) is persisted.
- Only the SHA-256 hash of the session token is stored in the database.
- Logout (`POST /api/auth/logout`) revokes the session record in PostgreSQL and expires the cookie. Revoked or expired sessions are rejected immediately.

### 3. Role-Based Access Control (RBAC)
Every protected endpoint derives authorization from the validated session, the user ID, their active workspace membership, and their role:
- **`admin`**: Full administrative access within the workspace. Manages members, role assignments, workspace settings, template deletion, upload deletions, and dashboard deletions.
- **`editor`**: Ingests spreadsheets, creates and edits mapping templates, runs normalizations, and saves dashboards.
- **`viewer`**: Read-only access. Can inspect dashboards, run analytical filter queries, and review data provenance; strictly prohibited from modifying templates, uploading files, or deleting records.

### 4. Cross-User and Object Isolation
- Users cannot access, preview, query, or delete another user's uploads, Parquet datasets, or saved dashboards. Attempts return HTTP 404 (non-disclosing) or HTTP 403.
- Unassigned legacy records (`workspace_id IS NULL`) are isolated from standard users and can only be accessed by platform administrators.

---

## Local Environment Configuration

### Backend Configuration (`backend/.env`)

Copy `backend/.env.example` to `backend/.env`:

```bash
cp backend/.env.example backend/.env
```

Key environment variables:

```env
APP_ENV=development
HOST=127.0.0.1
PORT=8000

# Metadata Database (PostgreSQL 16)
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/reporting_db

# Background Task Queue (Redis 7 & Celery)
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_TASK_ALWAYS_EAGER=false

# Storage Abstraction (Local private filesystem - zero cloud required)
STORAGE_BACKEND=local
STORAGE_LOCAL_ROOT=data/storage

# CORS Allowed Origins (Exact origins, no wildcards with credentials)
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Authentication & Sessions
SESSION_LIFETIME_SECONDS=86400
ALLOW_REGISTRATION=true
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
SINGLE_USER_DEV_MODE=false
```

> **Production Security Note**: When `APP_ENV=production`, `COOKIE_SECURE` must be `true` (HTTPS), and `SINGLE_USER_DEV_MODE` must be `false`. The application will abort startup if development bypass mode is enabled in production.

### Frontend Configuration (`frontend/.env.local`)

Copy `frontend/.env.example` to `frontend/.env.local`:

```bash
cp frontend/.env.example frontend/.env.local
```

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:18001
NEXT_PUBLIC_MAX_UPLOAD_BYTES=10485760
```
---

## Milestone 3: Background Ingestion, Local Storage, PostgreSQL, Parquet & Celery

### Architectural Decision: Zero AWS / Paid Cloud Dependencies

The platform operates completely locally without requiring:
- An AWS account or credentials
- AWS S3 or Cloudflare R2
- Paid cloud databases or Redis instances
- MinIO or storage servers that must be installed for local processing

### Technology Stack

| Layer | Implementation | Details |
|---|---|---|
| Frontend | Next.js 16 + React 19 + TypeScript + Tailwind CSS | Interactive workbook mapping, dataset catalog, polling status |
| API | Python FastAPI | Asynchronous upload and query plan endpoints |
| Metadata Layer | PostgreSQL 16 + SQLAlchemy 2.x + Alembic | `users`, `uploads`, `datasets`, `templates`, `dashboards`, `exports` |
| Storage | Local Private Filesystem (`STORAGE_BACKEND=local`) | Atomic writes, path traversal prevention (`backend/data/storage/`) |
| Background Jobs | Redis 7 + Celery (`concurrency=2`) | Asynchronous workbook scanning, table extraction, Parquet conversion |
| Analytical Engine | DuckDB + Apache Parquet | Direct parameterized aggregate queries on normalized Parquet files |

---

## Local Development & Operations

### Option A: Docker Compose (Recommended for Full Stack)

Run PostgreSQL 16, Redis 7, FastAPI, and the Celery worker locally with one command:

```bash
# Start all services in the background (all ports bound to 127.0.0.1)
docker compose -f infra/docker-compose.yml up -d

# Check service logs
docker compose -f infra/docker-compose.yml logs -f

# Apply Alembic database migrations
docker compose -f infra/docker-compose.yml exec api alembic upgrade head

# Run template migration utility (imports JSON templates into PostgreSQL)
docker compose -f infra/docker-compose.yml exec api python scripts/migrate_templates_to_pg.py

# Stop all services (preserves persistent database and storage volumes)
docker compose -f infra/docker-compose.yml down
```

### Option B: Native Local Setup (Without Docker)

#### 1. Start Local PostgreSQL & Redis
Ensure PostgreSQL 16 and Redis 7 are running on `127.0.0.1:5432` and `127.0.0.1:6379`.

#### 2. Backend Setup
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Migrate existing JSON mapping templates to PostgreSQL
python scripts/migrate_templates_to_pg.py

# Start Celery worker in Terminal 1
celery -A app.worker.celery_app worker --loglevel=info --concurrency=2

# Start FastAPI server in Terminal 2
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

#### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000/upload` to upload workbooks.

---

## Backup & Restore Procedures

### 1. Metadata Database (PostgreSQL)

```bash
# Backup metadata database to compressed file
pg_dump -h 127.0.0.1 -U postgres -d reporting_db -F c -b -v -f metadata_backup.dump

# Restore metadata database
pg_restore -h 127.0.0.1 -U postgres -d reporting_db -v metadata_backup.dump
```

### 2. Private Storage & Parquet Datasets

Original files and normalized Parquet files are stored in `backend/data/storage/`.

```bash
# Backup storage directory
# Windows PowerShell:
Compress-Archive -Path backend/data/storage -DestinationPath storage_backup.zip

# Restore storage directory
Expand-Archive -Path storage_backup.zip -DestinationPath backend/data/storage -Force
```

---

## Verification & Automated Tests

### Backend Tests (202 Tests)

The backend test suite runs with an isolated SQLite in-memory engine and eager Celery worker:

```bash
cd backend
pytest -v
```

Test breakdown:
- `tests/test_manufacturing_dashboard.py` (15 tests): Jan-Aug 2026 reference PPM reconciliation, source-of-truth conflict blocking (37,111 vs 46,816), defect Pareto ordering and 0-100% cumulative line, zero-total safety, Paynter heatmap 2D matrix and null future month handling, model comparison prohibiting cross-model PPM summing, action tracker cell-colour status mapping and invalid date handling, global parameterized filtering across widgets, specification persistence and DuckDB reopening.
- `tests/test_storage.py` (12 tests): Put/get, streaming, path traversal rejection, atomic writes, Parquet serialization.
- `tests/test_database.py` (7 tests): CRUD, unique constraints, foreign keys, idempotent template migration.
- `tests/test_duckdb_engine.py` (9 tests): Parquet queries, aggregations, filtering, group by, top-N, SQL injection rejection.
- `tests/test_tasks.py` (4 tests): Worker scanning, dataset generation, retry idempotence, Parquet creation.
- `tests/test_async_api.py` (8 tests): `POST /api/uploads` (202), status polling, dataset catalog, retry, DuckDB query.
- Baseline Phase 1-5 & Milestones 1-2 suites (147 tests): Ingestion scanner, mapping workspace, recommender, dashboard, auth.

### Frontend Quality Checks

```bash
cd frontend
npm run typecheck   # 0 errors
npm run lint        # 0 errors, 0 warnings
npm run build       # Next.js 16 production build: 12 static/dynamic routes
```

---

## Manufacturing Quality Dashboards (Milestone 4)

### 1. Template Catalogue
1. **Monthly Rejection PPM versus Target** (`TrendTargetChart.tsx`): Actual PPM and target series with variance indicators and target-exceeded warnings.
2. **Defect Pareto Chart** (`ParetoChart.tsx`): Categorical defect ranking sorted descending, cumulative percentage line (0% to 100%), 80% vital-few threshold, and Top-N toggle. Safe against zero-total inputs.
3. **Paynter Defect Heatmap** (`PaynterHeatmap.tsx`): 2D matrix of reporting months × defect/model categories. Future months rendered as null cells without turning into false zeros.
4. **Corrective-Action Tracker** (`ActionTracker.tsx`): Status breakdown (Completed, Open, Overdue, Unknown), champion breakdown chart, due date validation, and action details table.
5. **Model-Level Rejection Comparison** (`ModelComparisonChart.tsx`): Direct rejection quantity comparisons across models (`157 TY`, `367 TY`, `457 TY`, `Milwaukee`). Cross-model PPM summing or averaging is strictly prohibited by architectural rules.

### 2. Reconciliation Engine
- Authoritative reference figures tested against Jan–Aug 2026 blueprint values:
  `Jan: 4,229 | Feb: 2,718 | Mar: 2,514 | Apr: 1,307 | May: 1,618 | Jun: 2,318 | Jul: 3,565 | Aug: 7,458`.
- Source-of-truth conflict prompt: January production quantity conflict (37,111 in monthly breakdown vs 46,816 in overview ledger). Calculated PPM is blocked from publication until confirmed.
- Provenance modal exposes upload ID, worksheet, cell range, column, aggregation, formula applied, and audit caveats for every displayed metric.

---

## Report Exports & History Hardening (Milestone 6)

### 1. Export Formats Supported
1. **Executive PDF Report (`.pdf`)**:
   - Printable manufacturing report generated with ReportLab (`app/exports/generator.py`).
   - Running header & footer with two-pass `NumberedCanvas` ("Page X of Y").
   - Summary cards, Monthly PPM Trend table with target indicators, Defect Pareto ranking, Model-level rejection comparison, and Corrective Action Tracker board.
   - SOT reconciliation warning banner prominently rendered when January production denominator conflict is unconfirmed (37,111 vs 46,816).
   - Configurable orientation: Landscape (default, recommended for wide data tables) or Portrait.
2. **Dashboard Snapshot Image (`.png`)**:
   - High-DPI 1600x1100 dark-theme dashboard card rendered via Pillow.
   - Ideal for inclusion in executive review slide decks without browser capture noise.
3. **Multi-Sheet Excel Workbook (`.xlsx`)**:
   - Built with XlsxWriter with structured worksheets:
     - `Summary`: Executive KPIs, metadata, active filters, and summary tables.
     - `Dashboard Spec`: Technical widget configurations, queries, and metric provenance.
     - `Data_{Table}`: Normalized data tables from stored Parquet datasets.
   - Defense-in-depth spreadsheet formula-injection mitigation.
   - Identifier columns with leading zeros preserved explicitly as text strings.
4. **CSV Summary / Data Table (`.csv`)**:
   - UTF-8 with BOM (`utf-8-sig`) for Excel character compatibility.
   - Formula-injection mitigation for untrusted string values.
   - Configurable export mode: Normalized Parquet dataset or aggregated metrics summary.

### 2. Role-Based Export Permissions
- **Viewer**: Permitted to export visual representations (`pdf`, `png`) for dashboards they are authorized to view. Restricted (HTTP 403) from exporting raw datasets (`xlsx`, `csv`).
- **Editor & Admin**: Permitted to export all formats (`pdf`, `png`, `xlsx`, `csv`).
- **Admin**: Permitted to delete export history and clean up stored files.

### 3. Formula-Injection Mitigation Policy
- Any untrusted string value beginning with formula-triggering characters (`=`, `+`, `-`, `@`) is prepended with a single quote (`'`).
- Pure numeric values (whether typed integers/floats or numeric strings like `"-150.5"`) are NEVER altered, preserving arithmetic functionality in Excel.

### 4. Playwright Setup (Optional Browser Renderer)
The system uses native pure-Python ReportLab and Pillow for lightning-fast, zero-dependency PDF and PNG generation. Playwright is also installed for browser rendering:
```bash
# In backend virtual environment
playwright install chromium
```

### 5. Export Storage & Retention
- Generated files are written atomically to temporary files and moved to local private storage:
  `backend/data/storage/exports/{export_id}/export.{format}`.
- Deleting an export via `DELETE /api/exports/{id}` cleans up both the database record and the storage file.

---

## Verification & Automated Tests

### Backend Test Suite (233 Passing Tests)
```bash
cd backend
py -3.13 -m pytest tests -q
# Or run export tests specifically:
py -3.13 -m pytest tests/test_exports.py -v
```
**Test Results:** **233 passed**, 36 warnings in 15.91s.
- `tests/test_exports.py` (16 tests): Dashboard save, reopen, rename, duplicate, delete without deleting shared datasets, formula-injection sanitization, PDF/PNG/Excel/CSV generation, SOT warning preservation, export queue, download stream, viewer RBAC restrictions, and cross-workspace isolation.
- `tests/test_auth.py` (23 tests): Argon2id hashing, session token hashing, CSRF verification, RBAC permissions.
- `tests/test_manufacturing_dashboard.py` (15 tests): Manufacturing ECharts specs, DuckDB queries, reconciliation guard.
- `tests/test_storage.py` (12 tests): Private filesystem storage, atomic writes, path traversal prevention.
- `tests/test_database.py` (7 tests): PostgreSQL CRUD, unique constraints, foreign keys.
- `tests/test_duckdb_engine.py` (9 tests): Parquet analytical queries, aggregations, SQL injection guards.
- `tests/test_tasks.py` (4 tests): Celery worker tasks.
- `tests/test_async_api.py` (8 tests): Upload endpoints and background polling.
- Baseline suites (139 tests): Workbook scanner, mapping workspace, profiler.

### Frontend Quality Checks
```bash
cd frontend
npm run typecheck   # 0 errors
npm run lint        # 0 errors, 0 warnings
npm run build       # Next.js 16 production build: 12 static/dynamic routes prerendered
```


