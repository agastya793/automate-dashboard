# Roadmap — Excel-to-Dashboard Platform

**Repository:** Business Reporting Dashboard  
**Architecture Reference:** Excel-to-Dashboard Platform Blueprint & Client Handover (PDF, Oct 2026)  
**Document Updated:** 2026-10-25

---

## Milestone 1 — COMPLETED

**Integrate and harden the ingestion/recommendation engine**

### Deliverables (all done)

| Item | Status |
|---|---|
| `backend/app/ingestion/` package: `scanner.py`, `limits.py`, `__init__.py` | Done |
| `backend/app/dashboard_engine/` package: `recommender.py`, `__init__.py` | Done |
| `POST /api/workbooks/scan` endpoint | Done |
| All existing 54 backend tests remain passing | Done |
| 67 new Milestone 1 tests added, all passing (121 total) | Done |
| `docs/ROADMAP.md` and `docs/DECISIONS.md` | Done |

### What was implemented

**`backend/app/ingestion/scanner.py`** — Production-grade workbook scanner:
- `scan_workbook(raw, filename)` returns ScanResult (never accepts filesystem paths)
- Pure-Python BFS connected-component block detection (no scipy dependency)
- `parse_header()` handles real dates and text headers (Aug-26, Jan qty, Jan. PPM);
  rejects suspicious day strings (015-01-2026); warns when year cannot be grounded
- Bloated used-range guard via MAX_SCAN_ROWS / MAX_SCAN_COLS (configurable via env vars)
- `_unpivot()` fixed crash when id_cols is empty; ambiguous-row flagging;
  distinct measures (qty, PPM, %) never merged
- `suggest_label_merges()` edit-distance suggestions only, never silent rewrites; handles known=[]
- Cell fill colour reading (separate openpyxl pass, targeted, bounded)
- Formula-cache miss detection (compare formula vs data-only reads)
- Archive validation (zip-bomb guard, macro rejection, .xls rejection)

**`backend/app/dashboard_engine/recommender.py`** — Validated dashboard spec generator:
- Conservative `_is_id_column()` — PPM/defect counts correctly treated as measures
- `_validate_col_name()` rejects SQL keywords, dangerous patterns, oversized names
- `_validate_widget_spec()` strict server-side allowlists for types/aggregations/keys
- `run_widget()` DuckDB queries with quoted, pre-validated identifiers; zero-denominator safety
- Source-of-truth conflict (37,111 vs 46,816) surfaced as explicit warning requiring confirmation
- No client-workbook hardcoded values or print() calls in production code

**New API endpoint:**
- `POST /api/workbooks/scan` returns JSON with blocks, sheet names, column roles,
  confidence scores, warnings, formula-cache flags, ambiguous rows

### Known limitations (to address in later milestones)

- No database, Redis queue, or object storage. Processing is in-memory, 10 MiB limit enforced.
- Dashboard recommendations are not persisted; run_widget() requires DataFrames in-memory.
- Source-of-truth conflict flag surfaces as a JSON warning; confirmation UI is Milestone 2.
- Color-based action status extraction surfaces raw RGB only; status mapping is Milestone 2.
- No PPM widgets generated until production-quantity source-of-truth is confirmed by user.

---

## Milestone 2 — COMPLETED

**Mapping and normalisation UI & template engine**

### Deliverables (all done)

| Item | Status |
|---|---|
| `backend/app/ingestion/mapping.py`: Mapping models, template persistence, and normalisation logic | Done |
| `POST /api/workbooks/mapping` (save and version template) | Done |
| `GET /api/workbooks/mapping/{id}` (retrieve template by ID) | Done |
| `GET /api/workbooks/mappings` (list templates) | Done |
| `DELETE /api/workbooks/mapping/{id}` (delete template) | Done |
| `POST /api/workbooks/normalize` (apply mapping and return normalized tables) | Done |
| 26 new Milestone 2 tests in `backend/tests/test_mapping.py`, all passing (147 total) | Done |
| `frontend/lib/mappingTypes.ts`: Strict TypeScript interfaces for scan & mapping contracts | Done |
| `frontend/components/WorkbookMappingWorkspace.tsx`: Interactive mapping & normalisation workspace | Done |
| `frontend/app/upload/page.tsx`: Mode switcher integrating mapping workspace with upload flow | Done |
| Frontend `typecheck` and `lint` passing with 0 errors | Done |

### What was implemented

**Backend (`backend/app/ingestion/mapping.py` & `backend/app/main.py`):**
- **MappingTemplate & Schema**: Pydantic models supporting block inclusion/exclusion, range trimming, column role overrides (`date`, `category`, `measure`, `id`, `text`, `derived`), wide table unpivoting, ambiguous row routing, cell-color status mapping, and typo value merges.
- **Auto-versioning TemplateStorage**: File-based JSON template persistence in `backend/data/mappings/` with automatic version incrementing on update, in-memory caching, and path-traversal protection.
- **Normalization Engine (`normalize_workbook`)**:
  - Deterministic execution of range trimming and block exclusions.
  - Column role assignment override.
  - Wide monthly column unpivoting to long-form series with date and measure dimensions.
  - Ambiguous row classification (routes summary rows to separate summary tables, discards unwanted noise, preserves clean data records).
  - Cell fill color mapping deriving semantic `Action_Status` column from detected RGB codes.
  - Category typo merges replacing near-duplicate values based on user acceptance.
  - Production count conflict resolution unlocking PPM calculations when confirmed.

**Frontend (`frontend/components/WorkbookMappingWorkspace.tsx` & `frontend/app/upload/page.tsx`):**
- **Interactive Mapping Workspace**:
  - Sheet selector tabs with block count badges.
  - Block list with coordinate range preview, kind badges, and confidence metrics.
  - Range trim input allowing custom boundary adjustments (e.g. `A1:M20`).
  - Column role dropdown editor with visual type badges.
  - Wide table monthly unpivot configuration panel.
  - Ambiguous summary row triage panel (3-way toggle: Record vs Summary vs Discard).
  - Cell fill color status mapping panel with live hex swatches.
  - Production quantity conflict prompt (37,111 vs 46,816) with clear trade-off explanations.
  - Template save and load controls.
- **Seamless Integration in `/upload`**:
  - Switchable view modes: "Interactive Mapping & Normalisation" (Milestone 2) and "Standard Profiling View" (Phase 2).
  - Automatic workbook scan on file drop with real-time scanning indicator.
  - One-click "Apply & Normalise" action passing clean normalized tables directly into reporting preview.

---

## Milestone 3 — COMPLETED

**Background Ingestion, Local Storage, PostgreSQL, Parquet, DuckDB and Redis/Celery**

### Deliverables (all done)

| Item | Status |
|---|---|
| `backend/app/storage/`: Abstract `StorageBackend`, `LocalStorageBackend`, `save_dataframe_as_parquet` | Done |
| Mandatory architectural decision: Zero AWS / paid cloud dependencies (`STORAGE_BACKEND=local`, `backend/data/storage/`) | Done |
| `backend/app/db/`: SQLAlchemy 2.x models (`users`, `uploads`, `datasets`, `templates`, `dashboards`, `exports`) | Done |
| Alembic migrations: `alembic.ini`, `001_initial_schema.py` | Done |
| `backend/scripts/migrate_templates_to_pg.py`: Idempotent JSON-to-PostgreSQL template migration | Done |
| `backend/app/worker/`: Celery application (`celery_app.py`) & task modules (`tasks.py`) with eager fallback | Done |
| `backend/app/dashboard_engine/duckdb_engine.py`: Safe identifier quoting, parameterized `QueryPlan`, DuckDB execution | Done |
| Async Ingestion APIs: `POST /api/uploads`, `GET /api/uploads`, `GET /api/uploads/{id}`, `GET /api/uploads/{id}/datasets`, `POST /api/uploads/{id}/normalize`, `POST /api/uploads/{id}/retry`, `POST /api/query` | Done |
| `frontend/app/upload/page.tsx`: Async upload pipeline card, progress & stage monitoring, failed retry control, dataset catalog | Done |
| `infra/docker-compose.yml`: PostgreSQL 16, Redis 7, FastAPI API, Celery worker (all loopback bound) | Done |
| 40 new Milestone 3 tests (storage, database, duckdb, worker tasks, async API) — 187 total tests passing | Done |
| Frontend `typecheck`, `lint`, and Next.js production `build` passing with 0 errors | Done |

### What was implemented

**1. Private Local Filesystem Storage (`backend/app/storage/`):**
- Storage abstraction interface: `put_object`, `get_object`, `delete_object`, `object_exists`, `generate_key`.
- `LocalStorageBackend`: Enforces storage root boundaries, strictly rejects path traversal attempts (`..`, absolute paths outside root), implements atomic writes via temporary `.tmp` files and atomic rename, bounding file operations.
- `save_dataframe_as_parquet` / `read_parquet_as_dataframe`: High-performance Parquet serialization using PyArrow.
- Configurable private root `backend/data/storage/` (excluded from Git).

**2. PostgreSQL Metadata Layer (`backend/app/db/`):**
- SQLAlchemy 2.x declarative models with cross-dialect support (native PostgreSQL JSONB and UUID, SQLite in-memory fallback for zero-dependency unit tests).
- Clean encapsulated repositories: `UploadRepository`, `DatasetRepository`, `TemplateRepository`, `DashboardRepository`.
- Idempotent template migration script safely importing existing JSON templates into PostgreSQL without data loss.

**3. Background Queue & Tasks (`backend/app/worker/`):**
- Celery worker configured with Redis broker on `127.0.0.1:6379`.
- Eager execution fallback (`CELERY_TASK_ALWAYS_EAGER=true`) enabling full native testing without requiring live Redis daemon.
- `scan_workbook_task`: Accepts only upload UUID and storage key (never passes raw bytes or DataFrames over message bus), detects tables via production scanner, persists datasets in PostgreSQL, handles retry idempotence.
- `normalize_workbook_task`: Converts user-mapped tables to Apache Parquet files, publishes them through storage abstraction, updates dataset metadata.

**4. DuckDB Analytical Query Engine (`backend/app/dashboard_engine/duckdb_engine.py`):**
- Parameterized `QueryPlan` executing aggregate queries directly on Parquet files using in-memory DuckDB.
- Strict security controls: Regex identifier validation rejecting SQL keywords and injection patterns, standard double-quoting (`replace('"', '""')`), and parameterized filter placeholders.
- Returns JSON-safe results with aggregated measure mappings.

**5. Async Ingestion Endpoints (`backend/app/main.py`):**
- `POST /api/uploads`: Accepts workbook, validates size & format, streams to private storage, creates `queued` DB record, enqueues background worker task, returns HTTP 202 Accepted.
- `GET /api/uploads`: Returns paginated upload summaries for current context.
- `GET /api/uploads/{upload_id}`: Returns processing status (`queued`, `scanning`, `needs_mapping`, `ready`, `failed`), stage, progress, and safe error details.
- `GET /api/uploads/{upload_id}/datasets`: Lists discovered data blocks and Parquet keys.
- `POST /api/uploads/{upload_id}/normalize`: Triggers background Parquet normalisation.
- `POST /api/uploads/{upload_id}/retry`: Safely resets and retries failed uploads.
- `POST /api/query`: Validates query plan against authorized dataset schema and executes DuckDB query.
- Startup security guard preventing single-user dev mode from running when `APP_ENV=production`.

**6. Frontend Pipeline UI (`frontend/app/upload/page.tsx`):**
- Milestone 3 Asynchronous Pipeline Card displaying real-time status pills, progress bar, stage descriptions, and upload ID metadata.
- Polling hook with bounded interval, exponential backoff, and automatic unmount cleanup.
- Error banner with one-click "Retry Processing" button for failed jobs.
- Discovered Data Blocks & Parquet Tables catalog showing cell ranges, block kinds, dimensions, and Parquet persistence status.

---

## Milestone 4 — Manufacturing Quality Dashboards, Apache ECharts & Reconciliation (Completed)

**Status:** Completed (2026-10-25)  
**Dependencies:** Milestone 3 complete  
**Test Coverage:** 202 passed tests (187 baseline + 15 Milestone 4 tests); frontend `typecheck`, `lint`, and `build` passing with 0 errors.

### Deliverables Checklist

| Deliverable | Status |
|---|---|
| `EChartsWrapper.tsx`: Client component with ResizeObserver, high-DPI canvas, cleanup on unmount | Done |
| `TrendTargetChart.tsx`: Monthly Rejection PPM vs Target, variance indicators, target-exceeded mark points | Done |
| `ParetoChart.tsx`: Dual-axis Defect Pareto (0-100% cumulative line, 80% cutoff, Top-N toggle, zero-total safe) | Done |
| `PaynterHeatmap.tsx`: Months x Defect/Model matrix, missing future periods represented as null without false zeroes | Done |
| `ActionTracker.tsx`: Status counts (completed, open, overdue, unmapped), champion breakdown, due date validation | Done |
| `ModelComparisonChart.tsx`: Grouped/Stacked models comparison, strictly prohibiting cross-model PPM summing | Done |
| `ProvenanceModal.tsx`: Complete lineage modal (upload ID, sheet, range, column, aggregation, formula applied, caveats) | Done |
| `ReconciliationBanner.tsx`: Authoritative reference PPM reconciliation (Jan-Aug 2026 blueprint values) & conflict alerts | Done |
| `manufacturing_templates.py`: Versioned spec generator, DuckDB analytical executor, role detector, Pareto & PPM calculators | Done |
| API Endpoints: `POST /api/dashboards/manufacturing/generate`, `POST /api/dashboards`, `GET /api/dashboards/{id}`, `POST /api/dashboards/{id}/query`, `GET /api/dashboards` | Done |
| Global Filters: Consistent parameterized filtering across all 5 widgets (Period, Model, Defect, Owner, Status) | Done |
| Reconciliation regression tests against blueprint reference values and denominator conflict validation | Done |

### Reconciliation Status

- Reference PPM figures tested:
  - `Jan-26`: 4,229
  - `Feb-26`: 2,718
  - `Mar-26`: 2,514
  - `Apr-26`: 1,307
  - `May-26`: 1,618
  - `Jun-26`: 2,318
  - `Jul-26`: 3,565
  - `Aug-26`: 7,458
- **Source-of-Truth Conflict Guard**: When the January production quantity conflict (37,111 in monthly breakdown vs 46,816 in overview ledger) is unconfirmed, calculated PPM is blocked from publication with status `conflict_blocked` and an explicit confirmation prompt.
- **Client Workbook Status**: Client workbook was not available in workspace; all calculations were verified against isolated synthetic test fixtures replicating client workbook sheets and labelled as `synthetic_fixture`. Real-workbook reconciliation will run when authoritative client file is provided.

---

## Milestone 5 — COMPLETED

**Secure authentication, workspaces, roles and data access control**

### Deliverables (all done)

| Item | Status |
|---|---|
| Local email/password authentication using Argon2id (`argon2-cffi`) | Done |
| Opaque cryptographically random session tokens (256-bit entropy) | Done |
| PostgreSQL server-side sessions storing only SHA-256 token hashes | Done |
| HTTP-only session cookies (`SameSite=Lax`, `Secure` in prod, configurable lifetime) | Done |
| Double-submit CSRF cookie & `X-CSRF-Token` header check on state-changing requests | Done |
| Strict CORS allowlist derived from `ALLOWED_ORIGINS` (zero wildcard with credentials) | Done |
| Alembic migration `002_auth_workspaces.py` for Users, Sessions, Workspaces, Members | Done |
| Multi-tenant RBAC: Admin, Editor, Viewer roles enforced server-side on every endpoint | Done |
| Object-level access control on uploads, datasets, Parquet files, DuckDB queries, and dashboards | Done |
| Cross-user isolation: User A cannot read, query, update, or delete User B's resources | Done |
| Safe deletion endpoints (`DELETE /api/dashboards/{id}`, `/api/datasets/{id}`, `/api/uploads/{id}`) | Done |
| Celery background worker authentication & ownership validation | Done |
| Production startup guard rejecting `SINGLE_USER_DEV_MODE=true` in production | Done |
| Distributed sliding-window rate limiting for login and registration | Done |
| Frontend centralized `apiFetch` with automatic CSRF & credentials handling | Done |
| Frontend `AuthContext` with native FastAPI auth, profile, and workspace switcher | Done |
| 23 security & cross-user access tests in `test_auth.py` (217 total passing tests) | Done |

---

## Milestone 6 — COMPLETED

**Report exports, saved report history and MVP hardening**

### Deliverables (all done)

| Item | Status |
|---|---|
| Report History workflow: save under user-provided name, list in `/reports`, reopen, recalculate from Parquet | Done |
| Dashboard rename (`PATCH /api/dashboards/{id}`) and duplicate (`POST /api/dashboards/{id}/duplicate`) | Done |
| Delete dashboard with confirmation modal without deleting shared datasets or raw uploads | Done |
| Multi-format export engine: PDF (ReportLab), PNG (Pillow), Excel (.xlsx via XlsxWriter), CSV (UTF-8 BOM) | Done |
| Spreadsheet formula-injection defense (`=`, `+`, `-`, `@` text values neutralized; numeric values preserved) | Done |
| Role-based export permissions (Viewers restricted to visual PDF/PNG; Editors/Admins allowed XLSX/CSV) | Done |
| Asynchronous export lifecycle via Celery (`generate_export_task`) with local eager fallback | Done |
| Authenticated download endpoint (`GET /api/exports/{id}/download`) with cross-workspace isolation | Done |
| Frontend `ExportModal.tsx` dialog and updated `frontend/app/reports/page.tsx` with full CRUD modals | Done |
| 16 new automated export & report history tests added in `test_exports.py` (233 total passing tests) | Done |
| Alembic migration `003_exports_hardening.py` | Done |
| Documentation updated (`README.md`, `ROADMAP.md`, `PROJECT_STATUS.md`, `DECISIONS.md` ADR 008) | Done |

---

## Milestone 7 — Deployment and handover

**Dependencies:** Milestone 6 complete
**Target:** Final release

### Scope

- Docker Compose: PostgreSQL, Redis, MinIO, FastAPI, Celery, Next.js; Caddy/Nginx HTTPS
- Health/readiness checks
- CI pipeline: lint -> tests -> build -> container build
- Secrets documentation (.env.example only; no secrets in Git)
- Backup and restore scripts, retention policy
- Logging/monitoring guidance, rollback steps
- Docs: README, user manual, admin runbook, architecture/data model/API docs
- Licence inventory, sample fixtures, handover checklist

---

## Release 2 / 3 — Deferred items (do not implement ahead of schedule)

| Item | Reason deferred |
|---|---|
| Category-merge editor and broader cleanup tools | After Milestone 2 basic mapping |
| Calculated fields / target configuration | After source-of-truth rules confirmed |
| Month-over-month comparison | After source-of-truth rules approved |
| Scheduled emails | Release 2 |
| Comments, audit UI | Release 2 |
| SSO | Release 2 |
| Google Sheets / database connectors | Release 3 |
| Public API | Release 3 |
| WhatsApp integration | Release 3 |
| AI/LLM suggestions | Explicitly excluded from MVP critical path |

---

## How to run tests

```bash
cd backend
# Activate venv or use system Python 3.13
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run all tests
python -m pytest -v

# Run only Milestone 1 tests
python -m pytest tests/test_ingestion.py -v
```

**Baseline (2026-10-25):** 233 tests, 0 failures (54 baseline + 67 M1 + 26 M2 + 40 M3 + 15 M4 + 15 M5 security & auth + 16 M6 export & history hardening in `test_exports.py`).

---

## Client workbook status

The real client workbook was **not** present in the repository workspace at time of
Milestone 1 implementation. All tests use synthetic XLSX/CSV fixtures built with openpyxl.
The PPM regression (Jan-Aug 2026, Effect confirmation 26 sheet) was not run.
This will be reported as pass/fail only when the actual workbook is available and the
production-quantity source-of-truth conflict (37,111 vs 46,816) is resolved by the client.
# Verification follow-up — October 2026

- Keep the persisted async upload/scan/normalize flow as the only primary
  workbook path.
- Add a dedicated API regression test for the persisted scan response and
  approved-template handoff once the local PostgreSQL/Redis test fixture is
  stable.
- Re-run the complete backend suite, production frontend build, and live
  PostgreSQL/Redis/Celery/browser acceptance scenario outside the constrained
  sandbox.
- Run the HTTP integration suite on a normal Windows or Linux runner where
  Starlette TestClient can create its AnyIO socketpair.

