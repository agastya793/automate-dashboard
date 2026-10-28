# Architectural & Technical Decisions (ADR) — Excel-to-Dashboard Platform

**Repository:** Business Reporting Dashboard  
**Date:** October 2026  
**Status:** Approved & Implemented for Milestone 1; Active for Milestone 2

---

## ADR 001: Architecture Alignment with Client Blueprint

### Context
An earlier iteration explored Supabase + Recharts + in-memory processing. The authoritative blueprint specification (*Excel-to-Dashboard Platform Blueprint & Client Handover, Oct 2026*) establishes:
- Backend: FastAPI + PostgreSQL + Parquet/DuckDB + Redis/Celery + S3-compatible storage (MinIO locally).
- Frontend: Next.js (App Router) + TypeScript + Tailwind/shadcn + Apache ECharts.
- Processing: Strict resource limits, streaming/chunked parsing, deterministic calculations.

### Decision
1. Retain the existing FastAPI backend and Next.js frontend structure.
2. Deliver the platform in 7 disciplined, testable milestones without breaking existing features.
3. Keep Recharts operational until Apache ECharts components in Milestone 4 are fully tested and proven feature-equivalent.
4. Implement data structures and API contracts that cleanly migrate from in-memory processing to Celery/PostgreSQL/MinIO in Milestone 3.

---

## ADR 002: Ingestion Engine & Pure-Python Block Detection (Milestone 1)

### Context
Excel files provided by manufacturing clients contain irregular layouts:
- Multiple disjoint data blocks on a single sheet.
- Form headers, metadata banners, and blank separator rows/columns.
- Bloated used-range flags (e.g., cell formats applied across 1,048,576 rows).
- Missing cached formula results (`data_only=True` returning `None`).
- Custom date formats ("Aug-26", "Jan qty", "Jan. PPM") and malformed date strings ("015-01-2026").
- Heavy dependencies like `scipy.ndimage` for connected-component labeling increase image size and cold-start latency.

### Decision
1. **Pure-Python BFS**: Implement `_find_blocks()` using a standard Breadth-First Search on non-empty cells with 8-connectivity / Manhattan expansion. Eliminates binary dependencies like `scipy`.
2. **Bounds & Clamping**: Explicitly clamp used-ranges with `MAX_SCAN_ROWS` (default 5,000) and `MAX_SCAN_COLS` (default 100), configurable via environment variables.
3. **Date & Header Parsing**:
   - Parse month-year headers ("Aug-26", "Jan 2026", "2026-08") with explicit regex and date parsing.
   - Reject suspicious year strings (e.g., year < 1990 or > 2100; malformed day strings like "015-01-2026").
   - Emit warnings when a month is found without a grounded year hint, rather than guessing.
4. **Formula-Cache Validation**: Read workbooks with `data_only=False` and `data_only=True` to detect missing cached values; surface warnings to prompt the user to re-save in Excel.
5. **No File System Paths**: `scan_workbook(raw: bytes, filename: str)` operates strictly on memory buffers to prevent path-traversal attacks.

---

## ADR 003: Recommender & Safe Aggregation Queries

### Context
Unvalidated user input or column names used in dynamic SQL queries risk SQL injection and application crashes (e.g. division by zero in cumulative Pareto calculations).

### Decision
1. **Conservative Identifier Detection**: Never classify columns containing "ppm", "defect", "qty", or "count" as identifiers, even if integer values appear sequential.
2. **Strict Col Name Validation**: Reject column names with SQL keywords (`SELECT`, `UNION`, `DROP`), double hyphens (`--`), or semicolons. Quote all identifiers in DuckDB statements (`"col_name"`).
3. **Zero-Denominator Safeguard**: In Pareto cumulative calculations, check if the total sum is 0 before dividing; return 0.0 cumulative percentages rather than throwing `ZeroDivisionError` or returning `NaN`.
4. **Source-of-Truth Conflict Flag**: If total production quantities disagree between sheets (e.g. 37,111 in monthly breakdown vs 46,816 in total overview), emit an explicit warning requiring user confirmation before generating PPM metrics.

---

## ADR 004: Milestone 2 Mapping & Normalisation UI Design

### Context
Raw Excel spreadsheets require human confirmation to resolve ambiguities before ingestion into normalized tables:
- Ambiguous summary rows vs record rows.
- Unpivoting monthly columns into long-form `[date, measure_type, value]`.
- Mapping cell fill colors (RGB) to semantic action statuses (Complete, Overdue, In Progress).
- Typo suggestions for categories (edit distance <= 2).

### Decision
1. **Template Schema**: Structure mapping templates as versioned JSON objects containing:
   - `id`: Unique identifier (UUIDv4).
   - `version`: Integer version tracking modifications.
   - `sheet_mappings`: Per-sheet block coordinates, column role assignments, unpivot configurations, and color mappings.
   - `resolved_conflicts`: Explicit confirmations for source-of-truth discrepancies.
2. **Storage**:
   - Milestone 2: Store mapping templates in memory and local filesystem (`backend/data/mappings/`).
   - Milestone 3: Migrate seamlessly to PostgreSQL `templates` table with JSONB column.
3. **Client Flow**:
   - User uploads workbook -> `POST /api/workbooks/scan` returns detected blocks and preview.
   - UI displays Interactive Mapping Workspace: Sheet selector -> Block selection -> Column role editor -> Ambiguous row triage -> Color mapper.
   - User reviews and confirms mapping -> `POST /api/workbooks/mapping` persists template.

---

## ADR 005: Zero AWS / No Cloud Decision & Local Pipeline (Milestone 3)

### Context
Client-side requirement mandates that development and local reporting workflows must not depend on an AWS account, AWS S3, AWS credentials, paid cloud databases, paid Redis, Cloudflare R2, or requiring MinIO setup for local processing.

### Decision
1. **Storage Abstraction & Local Filesystem Default**:
   - Implemented `StorageBackend` abstraction (`put_object`, `get_object`, `delete_object`, `object_exists`, `generate_key`).
   - Default backend is `LocalStorageBackend` (`STORAGE_BACKEND=local`), saving files under `backend/data/storage/`.
   - Generates opaque keys (e.g. `uploads/<id>/original.xlsx`, `datasets/<id>/normalized.parquet`) and strictly prevents path traversal attacks (`..`, escaping root).
   - Atomic writes via temporary `.tmp` file and atomic rename guarantee zero partial file states.
   - Private local files are never exposed via static web servers or public HTTP endpoints.

2. **Metadata Layer (PostgreSQL 16 & SQLAlchemy 2.x)**:
   - PostgreSQL is the authoritative metadata database for `users`, `uploads`, `datasets`, `templates`, `dashboards`, and `exports`.
   - Raw cell contents belong in Parquet datasets; PostgreSQL stores structural metadata and JSONB configuration.
   - Dual-dialect compatibility (`JSON().with_variant(JSONB, "postgresql")` and `Uuid(as_uuid=True)`) enables zero-dependency SQLite in-memory execution for fast unit tests.
   - Template repository supports dual PostgreSQL persistence and file-based JSON compatibility with an idempotent migration utility (`migrate_templates_to_pg.py`).

3. **Background Ingestion (Redis 7 & Celery)**:
   - Asynchronous scanning and normalisation decouple file processing from synchronous HTTP request loops.
   - Tasks receive only stringified UUIDs and storage keys; workbook bytes and large DataFrames are never passed over Celery/Redis.
   - Eager fallback mode (`CELERY_TASK_ALWAYS_EAGER=true`) ensures tests and local single-node development execute reliably even if Redis is temporarily offline.

4. **DuckDB Query Engine over Parquet**:
   - Replaced unsafe string interpolation from starter scripts with typed, parameterized `QueryPlan`.
   - Identifiers are validated against strict regex allowlists, standard double-quoted, and filter values are passed as SQL parameters (`?`).
   - Executes aggregate queries directly on Parquet files, returning bounded JSON-safe rows.

---

## ADR 006: Manufacturing Quality Dashboards, Apache ECharts & Reconciliation Engine (Milestone 4)

### Context
Manufacturing quality reporting requires deterministic, explainable dashboards rather than AI-guessed charts.
Client specifications establish:
- Five mandatory templates:
  1. Monthly Rejection PPM vs Target (Line with variance & exceeded badges).
  2. Defect Pareto Chart (Dual-axis with 0-100% cumulative line & 80% cutoff).
  3. Paynter Defect Heatmap (Months x Defect/Model matrix with null handling for future periods).
  4. Corrective-Action Tracker (Status KPIs, champion breakdown, validated due dates, cell-fill colour mapping).
  5. Model-Level Rejection Comparison (Quantities compared directly; PPM cross-model summing prohibited).
- Authoritative reference PPM reconciliation (Jan-Aug 2026: 4229, 2718, 2514, 1307, 1618, 2318, 3565, 7458).
- Source-of-truth conflict guard: January production quantity (37,111 in monthly breakdown vs 46,816 in overview ledger).
- Next.js 16 + React 19 SSR compatibility with Apache ECharts.

### Decision
1. **Lifecycle-Safe Apache ECharts Client Wrapper**:
   - Built `EChartsWrapper.tsx` utilizing direct `echarts.init()` inside `useEffect()`, observing container dimensions via `ResizeObserver` and guaranteeing cleanup via `chart.dispose()`.
   - Eliminated third-party React wrappers (`echarts-for-react`) that suffer from React 19 peer-dependency conflicts.
   - Guaranteed zero SSR hydration failures by keeping chart initialization strictly on the client.

2. **Template-Driven Backend Specification & Parameterized Execution**:
   - Created `ManufacturingDashboardSpec` and `ManufacturingWidgetSpec` typed models.
   - Built `build_manufacturing_dashboard_spec()` and `execute_manufacturing_widget()` running parameterized DuckDB queries directly over normalized Parquet datasets.
   - Complete metric provenance retained on every widget: `upload_id`, `sheet_name`, `cell_range`, `source_column`, `aggregation`, `calculation_applied`, `confirmation_status`, and `caveats`.

3. **Reconciliation & Accuracy Guard**:
   - Implemented `compute_ppm_reconciliation()` comparing recalculated PPM against the 8 approved reference figures.
   - When the January production count conflict is unconfirmed, calculated PPM is blocked with a `conflict_blocked` status and an explicit user confirmation prompt.
   - When confirmed source PPM columns exist, they are displayed as source measures with provenance.
   - Disallow summing or averaging PPM across product models; model comparisons display verified quantities.

4. **Global Manufacturing Filters**:
   - Consistent parameterized filtering across all 5 widgets for `Period`, `Model`, `Defect`, `Champion/Owner`, and `Action Status`.

---

## ADR 007: Secure Authentication, Server-Side Sessions, Double-Submit CSRF, and Workspace Authorization (Milestone 5)

### Context
Handling private manufacturing and quality-reporting information mandates enterprise-grade security without relying on paid cloud services (AWS, Supabase, Auth0, MinIO).
Key architectural constraints:
- Local email/password authentication using FastAPI and PostgreSQL.
- Opaque, cryptographically secure server-managed sessions (no raw tokens in DB or browser storage).
- Complete session expiration, revocation, and logout handling.
- Defense-in-depth CSRF and strict CORS protection for cookie-based authentication.
- Multi-tenant workspace isolation with role-based access control (Admin, Editor, Viewer).
- Object-level authorization for all storage objects, Parquet datasets, and DuckDB analytical queries.
- Safe local development mode protected by a production startup guard.

### Decision
1. **Argon2id Password Hashing & Timing-Safe Verification**:
   - Implemented password hashing via `argon2-cffi` with standard parameters (`time_cost=3`, `memory_cost=65536`, `parallelism=4`).
   - Timing-safe verification prevents side-channel attacks.
   - Passwords must be at least 8 characters and contain both letters and digits/special characters.

2. **256-Bit Entropy Session Tokens & SHA-256 Database Hashes**:
   - Generated using `secrets.token_urlsafe(32)` (256 bits of cryptographic entropy).
   - Only the SHA-256 hash of the token (`token_hash`) is stored in PostgreSQL. Raw session tokens are never persisted in the database.
   - Compromised database backups cannot be leveraged to hijack active user sessions.
   - HTTP-only cookie (`session_token`) with `SameSite=Lax`, `Secure` in production, and configurable lifetime (`SESSION_LIFETIME_SECONDS`, default 86400s).

3. **Double-Submit CSRF Token & Origin Validation**:
   - Issues a separate, unpredictable client-readable `csrf_token` cookie along with the HTTP-only session cookie.
   - Enforces `X-CSRF-Token` header check on all state-changing HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`).
   - Cross-Origin validation checks `Origin` / `Referer` against explicit `ALLOWED_ORIGINS` (defaulting to `http://localhost:3000`). Wildcard origins are strictly forbidden when credentials are enabled.

4. **Multi-Tenant Workspaces & Role-Based Access Control (RBAC)**:
   - Each registered user automatically receives a private default workspace with `admin` ownership.
   - Roles:
     - `admin`: Manages workspace members, role assignments, and workspace-level resources.
     - `editor`: Can upload workbooks, edit mapping templates, normalize datasets, and save dashboards.
     - `viewer`: Can read dashboards, inspect provenance, and view datasets; strictly prohibited from uploading, modifying templates, saving dashboards, or deleting resources.
   - Centralized authorization helpers (`verify_upload_access`, `verify_dashboard_access`, `verify_template_access`, `require_role`).
   - Unassigned legacy records (`workspace_id IS NULL`) are isolated from standard users and return 404.

5. **Storage & Analytical Query Object Isolation**:
   - All object lookups verify workspace authorization before allowing Parquet reads or DuckDB queries.
   - Storage deletion requests verify that the user is authorized to delete the owning database record before deleting files from `backend/data/storage/`.
   - Direct filesystem paths are never accepted from clients; arbitrary path traversal is rejected.

6. **Production Startup Guard for Single-User Dev Mode**:
   - `SINGLE_USER_DEV_MODE=true` is strictly prohibited in production.
   - FastAPI startup hook (`startup_security_check`) immediately aborts startup with a `RuntimeError` if `APP_ENV=production` and `SINGLE_USER_DEV_MODE=true`.

7. **Sliding-Window Rate Limiting**:
   - Applied to `/api/auth/login` (5 requests/min) and `/api/auth/register` (3 requests/min).
   - Backed by Redis sliding window when connected, with a thread-safe in-memory fallback for local development and testing.

---

## ADR 008: Report Exports, Formula-Injection Mitigation, Export Lifecycle & Report History Hardening (Milestone 6)

### Context
To make the automated business reporting dashboard useful as a complete, client-facing product, authenticated users must be able to save and reopen dashboards, export verified reports to standard business formats (PDF, PNG, Excel, CSV), and download them securely.
Key constraints:
- Zero AWS, Supabase, MinIO, or paid cloud services.
- Local private filesystem storage (`backend/data/storage/exports/{export_id}/`).
- Exact dashboard specification reuse: on-screen ECharts, PDF, and PNG outputs must represent the exact same numbers, target indicators, and reconciliation status without independent recalculation.
- Defense-in-depth protection against spreadsheet formula injection in CSV and Excel exports.
- Multi-sheet Excel workbooks (`Summary`, `Dashboard Spec`, `Normalized Dataset`).
- Role-based export permissions: Viewers are permitted to export visual representations (PDF, PNG), but are strictly forbidden from exporting raw datasets (Excel, CSV).
- Deleting a saved dashboard must never delete underlying datasets or uploads shared by other reports.

### Decision
1. **Report History & Specification Reuse**:
   - `dashboards` table stores the confirmed `spec` JSON with widget definitions, dataset IDs, dimensions, measures, aggregations, and layout parameters.
   - When a report is opened, DuckDB queries execute dynamically against normalized Parquet files to reproduce the authoritative figures.
   - Renaming (`PATCH /api/dashboards/{id}`) and duplicating (`POST /api/dashboards/{id}/duplicate`) are restricted to `editor` and `admin` roles.
   - Deleting a dashboard (`DELETE /api/dashboards/{id}`) deletes only the dashboard record and its cascade-related `Export` records; underlying `Upload` and `Dataset` records and Parquet files in private storage remain untouched.

2. **Spreadsheet Formula-Injection Mitigation**:
   - If an untrusted string value begins with formula trigger characters (`=`, `+`, `-`, `@`), it is prepended with a single quote (`'`).
   - Pure numeric values (whether typed integers/floats or pure number strings like `"-150.5"`) are NEVER indiscriminately converted to formula-escaped strings, preserving calculations and sorting in Excel.
   - Product identifiers with leading zeros (e.g. `"00123"`, `"157 TY"`) are written explicitly as text strings.

3. **Multi-Format Export Engine**:
   - **PDF**: Printable executive report built with ReportLab (`SimpleDocTemplate`, `Table`, `NumberedCanvas`) with title, metadata, active filters, KPI cards, widget breakdown tables, and a high-visibility reconciliation warning banner when January denominator conflict is unconfirmed (37,111 vs 46,816).
   - **PNG**: High-DPI 1600x1100 dark theme dashboard card snapshot via Pillow.
   - **Excel (.xlsx)**: Generated via XlsxWriter with formatted `Summary` sheet, `Dashboard Spec` metadata sheet, and `Normalized Dataset` tables up to sheet row limits.
   - **CSV**: UTF-8 with BOM (`utf-8-sig`) for Excel character compatibility, sanitized text, and standard comma delimiters.

4. **Export Task Lifecycle & Storage Hardening**:
   - `POST /api/dashboards/{id}/exports`: Validates requested format against `['pdf', 'png', 'xlsx', 'csv', 'pptx']` and role permissions. Creates an `Export` record with status `queued` and returns HTTP 202 with opaque export ID.
   - Celery worker executes `generate_export_task(export_id)`, passing only validated IDs rather than large file buffers or DataFrames. A local synchronous fallback executes when Redis is offline or in eager test mode.
   - Atomic temporary file creation with automatic cleanup on completion or failure.
   - `GET /api/exports/{id}/download`: Enforces authenticated session, workspace isolation (rejects cross-workspace access with HTTP 403), and streams the file from private storage with proper MIME type and `Content-Disposition`.



