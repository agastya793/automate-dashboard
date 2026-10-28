# Project Status — Business Reporting Dashboard

**Current Phase:** Milestone 5 (Secure Authentication, Workspaces, Roles and Data Access Control) — Completed
**Status Date:** October 2026  
**Lead Architecture:** Senior Application Security Engineer, Backend Architect & Full-Stack Engineer

### Current verification note (27 October 2026)

The upload UI now uses the persisted asynchronous ingestion pipeline as its
single structural scan path. The browser reads the bounded scan result back
from `/api/uploads/{upload_id}/scan`; it no longer starts a second independent
scan for the same workbook. Approved mapping JSON is forwarded to the
background normalization job. Frontend typecheck and lint, and backend Python
compilation, pass. Full backend pytest execution remains unverified in the
current sandbox because the suite hangs after initial ingestion tests; live
PostgreSQL, Redis/Celery, and browser integrations were not available for
verification.

### Stabilization verification (27 October 2026)

- Pytest collection succeeds: 234 tests collected.
- With a writable workspace temp directory, storage (12), database (7),
  worker tasks (4), ingestion non-HTTP coverage (53), DuckDB (9), recommender
  non-HTTP coverage (10), and manufacturing calculation coverage (13) pass.
- HTTP `TestClient` tests remain blocked by the Windows sandbox: AnyIO cannot
  create its socketpair even for a minimal FastAPI app. This is an execution
  environment limitation, not an application assertion failure.
- The production Next.js build succeeds in `C:\dev\AutomateDashboard`, an
  isolated copy outside OneDrive. The original OneDrive build fails creating
  generated `.next` directories with `EPERM`.
- Docker-backed PostgreSQL, Redis, and Celery were not available because the
  Docker Desktop engine is not running.

### Live local verification (27 October 2026)

The browser's 404 was caused by `localhost:8000` being occupied by an
unrelated Digital Wallet Ledger Engine container. The dashboard now defaults
to dedicated local ports (`18001` API, `15433` PostgreSQL, `16380` Redis), and
the PostgreSQL `psycopg` 3 dependency required by SQLAlchemy 2.1 is installed.
Using the dedicated Compose stack, authenticated synthetic verification
completed successfully: upload returned 202, the worker reached `ready`, all
three worksheets and persisted scan ranges were returned, normalization wrote
Parquet, DuckDB returned model totals, and manufacturing dashboard generation
returned five rendered widgets. The real client workbook remains unverified.

---

## 1. System Architecture Overview

The **Automated Business Reporting Dashboard** is a template-driven, explainable manufacturing BI platform designed to transform structured and semi-structured Excel workbooks into accurate, deterministic quality dashboards.

```
+-------------------------------------------------------------------------+
|                  Frontend (Next.js 16 + React 19 + Tailwind)            |
|  - App Router (/dashboard, /upload, /reports, /settings, /login, /signup)|
|  - Centralized apiFetch with automatic CSRF & cookie credentials        |
|  - Workspace Switcher & User Profile Navigation in Sidebar              |
|  - Apache ECharts v5 (Lifecycle-safe client wrapper + ResizeObserver)   |
|  - 5 Manufacturing Templates (PPM Trend, Pareto, Heatmap, Action, Model)|
|  - Global Parameterized Filters (Period, Model, Defect, Owner, Status)  |
|  - Lineage & Provenance Modal + Reference Reconciliation Banner         |
+-------------------------------------------------------------------------+
                                    |
                                    | HTTP REST with HttpOnly Session Cookie & CSRF Token
                                    v
+-------------------------------------------------------------------------+
|                         Backend (FastAPI + Python 3.13)                 |
|  - Authentication & Session Layer (Argon2id + SHA-256 Session Token Hash)|
|  - Double-Submit CSRF & Origin Validation Middleware                    |
|  - Multi-Tenant RBAC Workspace Authorization (Admin, Editor, Viewer)    |
|  - Production Startup Security Guard (Fails fast on Dev Mode Bypass)    |
|  - Pure-Python Scanner (BFS Table Block & Multi-month Unpivot Detector) |
|  - DuckDB In-Memory Analytical Query Engine over Parquet Files          |
|  - Blueprint Reconciliation Engine (Jan-Aug 2026 Reference PPM Guard)   |
|  - PostgreSQL Metadata Layer (SQLAlchemy 2.x Declarative Repositories)   |
|  - Background Queue (Celery + Redis with eager local fallback)          |
|  - Local Private Filesystem Storage (backend/data/storage/)             |
+-------------------------------------------------------------------------+
```

---

## 2. Completed Milestones

### Milestone 1 — Ingestion Engine & Pure-Python Block Detection
- Pure-Python BFS connected-component table detection (`scanner.py`).
- Automatic wide multi-month header detection, unpivot configuration, and category typo suggestions.
- Formula-cache detection (`data_only=False` vs `True`).
- 67 tests passing.

### Milestone 2 — Interactive Mapping Workspace & Normalization
- Visual table mapping workspace (`WorkbookMappingWorkspace.tsx`).
- Column role assignment (Date, Category, Measure, ID, Derived, Text).
- Ambiguous row triage (Summary vs Record vs Discard).
- Cell fill colour to semantic status mapping.
- Source-of-truth production quantity conflict prompt (37,111 vs 46,816).
- 26 tests passing.

### Milestone 3 — Local Storage, PostgreSQL, Parquet, DuckDB & Celery
- Private filesystem storage abstraction (`LocalStorageBackend`).
- PostgreSQL models & repositories (`users`, `uploads`, `datasets`, `templates`, `dashboards`, `exports`).
- Redis & Celery asynchronous background pipeline with eager fallback.
- DuckDB analytical query engine executing parameterized `QueryPlan` over Parquet files.
- 40 tests passing.

### Milestone 4 — Manufacturing Quality Dashboards, Apache ECharts & Reconciliation
- **Apache ECharts Client Integration**: `EChartsWrapper.tsx` providing SSR-safe chart initialization, automatic resize observer, high-DPI canvas, and clean unmount disposal.
- **5 Specialized Manufacturing Chart Components**: Monthly PPM Trend vs Target, Dual-axis Defect Pareto, Paynter Defect Heatmap, Corrective-Action Tracker, Model-Level Comparison.
- **Reconciliation & Accuracy Engine**:
  - Compares recalculations against approved blueprint reference PPM values for Jan–Aug 2026 (`4229, 2718, 2514, 1307, 1618, 2318, 3565, 7458`).
  - Source-of-truth denominator conflict guard: January production quantity (37,111 in monthly breakdown vs 46,816 in overview ledger). Calculated PPM is blocked from publication with `conflict_blocked` status until confirmed.
  - Full data lineage and KPI provenance displayed on all widgets via `ProvenanceModal.tsx`.
- 15 tests passing.

### Milestone 5 — Secure Authentication, Workspaces, Roles and Data Access Control
- **Argon2id Email/Password Authentication**: Secure password verification via `argon2-cffi`, minimum 8 characters with complexity checks, duplicate account handling.
- **Server-Side PostgreSQL Sessions**: 256-bit entropy opaque random session tokens. Only the SHA-256 hash is persisted in the database; raw session tokens are never stored in PostgreSQL, `localStorage`, or `sessionStorage`.
- **Session & Cookie Security**: Configurable session lifetime, revocation, server-side logout, HTTP-only cookie (`session_token`), `SameSite=Lax`, `Secure` in production.
- **CSRF & CORS Defense**: Double-submit CSRF cookie + mandatory `X-CSRF-Token` header on state-changing requests (`POST`, `PUT`, `DELETE`, `PATCH`). Exact origin allowlist check; zero wildcard origins with credentials.
- **Multi-Tenant Workspaces & RBAC**:
  - `User`, `Session`, `Workspace`, `WorkspaceMember` models with Alembic migration `002_auth_workspaces.py`.
  - Roles: `admin` (manages membership and settings), `editor` (uploads, normalizes, manages templates/dashboards), `viewer` (read-only queries and inspection).
  - Every new user receives a private default workspace with ownership.
  - Centralized authorization helpers (`verify_upload_access`, `verify_dashboard_access`, `verify_template_access`, `require_role`).
  - Legacy records with unassigned workspaces are isolated from standard users (return 404).
- **Secure File, Parquet & Object Access**: Storage deletion and DuckDB queries require validated record ownership and workspace membership. Path traversal rejected.
- **Production Startup Guard**: Aborts server startup if `APP_ENV=production` and `SINGLE_USER_DEV_MODE=true`.
- **Sliding-Window Rate Limiting**: Distributed Redis sliding-window with thread-safe in-memory fallback.
- **Frontend Integration**: Centralized `apiFetch` in `frontend/lib/api.ts`, rewritten `AuthContext.tsx`, updated `/login`, `/signup`, `/forgot-password`, and workspace switcher in `Sidebar.tsx`.
- **23 comprehensive security and auth tests in `test_auth.py` (217 total passing tests).**

### Milestone 6 — Report Exports, Saved Report History and MVP Hardening
- **Saved Report History Workflow**:
  - Full dashboard lifecycle: save under user-provided name, list in `/reports`, reopen, rename (`PATCH /api/dashboards/{id}`), duplicate (`POST /api/dashboards/{id}/duplicate`), and delete (`DELETE /api/dashboards/{id}`).
  - Deleting a dashboard deletes only the dashboard and its cascade-related `Export` records; underlying `Upload` and `Dataset` records and Parquet files in private storage remain untouched.
  - Recalculates dynamically from stored Parquet datasets using DuckDB.
- **Multi-Format Export Engine**:
  - **PDF Export**: Executive printable quality report via ReportLab with running header/footer, Page X of Y numbering, active filters, KPI cards, tables for PPM Trend, Defect Pareto, Models, Action Tracker, and high-visibility reconciliation conflict banner.
  - **PNG Export**: High-DPI 1600x1100 dark theme dashboard card snapshot via Pillow.
  - **Excel Workbook (.xlsx)**: Multi-sheet workbook via XlsxWriter (`Summary`, `Dashboard Spec`, and `Normalized Dataset`) with formula-injection protection and preserved text IDs with leading zeros.
  - **CSV Export**: UTF-8 with BOM (`utf-8-sig`) for Excel character compatibility and formula-injection protection.
- **Security & Formula-Injection Mitigation**:
  - Neutralizes untrusted strings beginning with `=`, `+`, `-`, `@` by prepending a single quote (`'`).
  - Legitimate typed numeric values (e.g. `-150`, `42.5`) remain numbers and are NOT escaped.
  - Role-based export permissions: Viewers are permitted to export visual formats (PDF, PNG), but are strictly forbidden (HTTP 403) from exporting raw datasets (Excel, CSV).
  - Cross-workspace isolation: Users cannot access or download exports belonging to other workspaces (HTTP 403).
- **Asynchronous Task Architecture & Download Endpoint**:
  - `POST /api/dashboards/{id}/exports`: Validates requested format and role permissions, returns HTTP 202 with opaque export ID.
  - Dispatches `generate_export_task` passing validated IDs only, with synchronous eager/local fallback.
  - `GET /api/exports/{id}`: Bounded status polling endpoint.
  - `GET /api/exports/{id}/download`: Authenticated file stream from local private storage with proper MIME types and `Content-Disposition`.
- **Frontend UI Integration**:
  - Redesigned `/reports` page with saved report cards, source filenames, timestamps, search filter, rename modal, duplicate action, delete confirmation modal, and export triggers.
  - Created reusable `ExportModal.tsx` with format selector, role-based locking, options, progress polling, and direct download.
  - Added "Export Report" button directly to `/dashboard` toolbar.
- **16 comprehensive export tests in `test_exports.py` (233 total passing backend tests).**

---

## 3. Explicitly Deferred Work (Future Milestones)

1. **Milestone 7**: Production deployment, containerized stack, client handover, final auditing.
2. **Explicitly Excluded from Current Scope**: Public share links, paid cloud services (AWS, MinIO, Supabase), AI/LLM hallucinations, automated alerts (WhatsApp, Email), SSO.

---

## 4. Test Verification Summary

- Backend pytest: **233 passed**, 0 failed (`py -3.13 -m pytest tests -q` in 15.91s).
- Milestone 6 pytest: **16 passed**, 0 failed (`py -3.13 -m pytest tests/test_exports.py -v` in 2.29s).
- Frontend TypeScript (`tsc --noEmit`): **0 errors**.
- Frontend ESLint (`eslint .`): **0 errors, 0 warnings**.
- Frontend Next.js build (`next build`): **12 static/dynamic routes prerendered successfully with Turbopack**.
