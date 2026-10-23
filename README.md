# Automated Business Reporting Dashboard

An automated, verifiable reporting platform for business owners. Ingest raw spreadsheets (Excel and CSV), validate data integrity, inspect column classifications, calculate deterministic business metrics, and persist private datasets and saved reporting dashboards with Supabase authentication and Row Level Security (RLS).

---

## Architecture Overview

- **Frontend**: Next.js 16 (App Router), React 19, TypeScript (Strict Mode), Tailwind CSS, Lucide React, `@supabase/supabase-js`, `@supabase/ssr`.
- **Backend**: Python FastAPI, Pydantic, Pandas, OpenPyXL, dynamic CORS, Bearer token verification via Supabase Auth.
- **Database & Persistence**: Supabase PostgreSQL with strict Row Level Security (RLS) on all tables.
- **Private Storage**: Supabase Storage private bucket (`business-datasets`) with workspace-scoped RLS policies.
- **Visualizations**: Recharts interactive charting engine with server-calculated aggregations and date/category filters.

---

## Directory Structure

```
business-reporting-dashboard/
├── frontend/
│   ├── app/
│   │   ├── globals.css              # Base styles & accessible focus rings
│   │   ├── layout.tsx               # App shell, AuthProvider & DashboardProvider
│   │   ├── page.tsx                 # Overview dashboard
│   │   ├── login/page.tsx           # Email/password authentication sign in
│   │   ├── signup/page.tsx          # Account registration with workspace provisioning
│   │   ├── forgot-password/page.tsx # Password recovery request flow
│   │   ├── reset-password/page.tsx  # Secure password update flow
│   │   ├── auth/callback/route.ts   # PKCE auth code exchange route
│   │   ├── upload/page.tsx          # Spreadsheet upload, validation & profiling
│   │   ├── dashboard/page.tsx       # Interactive dashboard with filters & Save Report
│   │   ├── reports/page.tsx         # Saved reports directory (open, inspect, delete)
│   │   └── settings/page.tsx        # Workspace preferences & security info
│   ├── components/
│   │   ├── Sidebar.tsx              # Desktop sidebar with user account status
│   │   ├── Header.tsx               # Accessible page header
│   │   ├── RecommendedCharts.tsx    # Recommendation review & chart customization
│   │   ├── DashboardChartRenderer.tsx # Recharts interactive renderers
│   │   └── SummaryCard.tsx          # Metric cards
│   ├── context/
│   │   ├── AuthContext.tsx          # Supabase auth session & workspace state
│   │   └── DashboardContext.tsx     # Dataset, chart state & persistence methods
│   ├── lib/
│   │   └── supabase/                # Browser and server Supabase SSR clients
│   ├── proxy.ts                     # Next.js 16 proxy for session refresh
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app with protected dataset routes
│   │   ├── auth.py                  # Bearer token verification dependency
│   │   ├── profiler.py              # Excel/CSV parser, type inferrer & validator
│   │   ├── recommender.py           # Rules-based chart recommendation engine
│   │   └── dashboard.py             # Server-side aggregations & filter engine
│   ├── tests/                       # 54 comprehensive unit & auth tests
│   └── requirements.txt
├── supabase/
│   └── migrations/
│       ├── 00001_initial_schema.sql # Profiles, workspaces, members, datasets, reports
│       ├── 00002_rls_policies.sql   # Anti-recursion RLS functions & table policies
│       └── 00003_storage_setup.sql  # Private business-datasets bucket & storage RLS
├── sample_data/                     # Test spreadsheets (Sales, HR, Financials)
└── README.md
```

---

## Supabase Setup Guide

### 1. Create a Supabase Project

1. Sign in to your [Supabase Dashboard](https://supabase.com/dashboard) and click **New Project**.
2. Choose a project name, database password, and preferred region.
3. Once the database is provisioned, navigate to **Project Settings -> API** to find:
   - **Project URL** (`https://<project-ref>.supabase.co`)
   - **anon / public key** (`ey...`)

### 2. Run Database Migrations

Open the **SQL Editor** in your Supabase dashboard and run the migrations in numerical order:

1. **`supabase/migrations/00001_initial_schema.sql`**:
   - Creates `profiles`, `workspaces`, `workspace_members`, `datasets`, and `reports` tables.
   - Sets up the `handle_new_user()` database trigger: when a user registers via Supabase Auth, it automatically provisions their profile and creates a private default workspace with the user as `owner`.
   - Adds indexes for common workspace, dataset, and report queries.

2. **`supabase/migrations/00002_rls_policies.sql`**:
   - Defines security definer helper functions (`public.is_workspace_member`, `public.has_workspace_role`) with search_path locked to `public` to prevent policy recursion.
   - Enables RLS on all application tables.
   - Restricts datasets and reports creation, update, and deletion to `owner` and `editor` roles, while allowing `viewer` members read-only access.
   - Enforces strict cross-workspace isolation.

3. **`supabase/migrations/00003_storage_setup.sql`**:
   - Creates the private `business-datasets` storage bucket (10 MiB limit, restricted MIME types).
   - Establishes storage RLS policies ensuring only workspace members can download source files, and only authorized roles (`owner`, `editor`) can upload/delete.

### 3. Configure Authentication Settings

In **Authentication -> URL Configuration**:
- **Site URL**: `http://localhost:3000`
- **Redirect URLs**: Add:
  - `http://localhost:3000/auth/callback`
  - `http://localhost:3000/reset-password`

---

## Local Environment Configuration

### Frontend Configuration (`frontend/.env.local`)

Copy `frontend/.env.example` to `frontend/.env.local`:

```bash
cp frontend/.env.example frontend/.env.local
```

Populate with your project values:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_MAX_UPLOAD_BYTES=10485760

NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

### Backend Configuration (`backend/.env`)

Copy `backend/.env.example` to `backend/.env`:

```bash
cp backend/.env.example backend/.env
```

Populate with matching values:

```env
ENVIRONMENT=development
HOST=127.0.0.1
PORT=8000
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

> **Security Note**: Never commit `.env` or `.env.local` files to Git. The project `.gitignore` excludes all `.env*` files while retaining example templates.

---

## Running the Application Locally

### 1. Start the FastAPI Backend

```bash
cd backend

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Install dependencies if not installed
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

FastAPI will be available at `http://127.0.0.1:8000`.
- Health check: `http://127.0.0.1:8000/health` (public)
- Protected endpoints: `/api/datasets/preview`, `/api/datasets/dashboard` (require Bearer access token)

### 2. Start the Next.js Frontend

In a separate terminal:

```bash
cd frontend

# Run development server
npm run dev
```

The Next.js application will be available at `http://localhost:3000`.

---

## Testing & Verification

### Backend Tests

Run the complete backend test suite (including auth, schema validation, chart recommendations, and dashboard aggregation tests):

```bash
cd backend
pytest tests -v
```

All 54 tests will execute with isolated dependency overrides and mock credentials.

### Frontend Quality Checks

```bash
cd frontend

# TypeScript strict type checking
npm run typecheck

# ESLint validation
npm run lint

# Production build validation
npm run build
```

---

## How to Verify Persistence & Workspace Isolation

1. **Sign Up & Workspace Creation**:
   - Navigate to `http://localhost:3000/signup`.
   - Register a new user (e.g. `alice@example.com`).
   - Notice the user is assigned a private workspace (`Alice's Workspace`) with the `owner` role.
2. **Upload & Private Storage**:
   - Upload an Excel or CSV spreadsheet (e.g. `sample_data/sample_sales_data.csv`).
   - The file is profiled and saved to private Supabase Storage at `<workspace_id>/<user_id>/<dataset_id>/<filename>`.
   - The green `[Saved to Private Storage]` badge confirms persistence.
3. **Save Report**:
   - Confirm chart recommendations and click **Generate Dashboard**.
   - Apply a date or category filter.
   - Click **Save Report** in the top bar and name it (e.g. `Q3 Sales Summary`).
4. **Reopen Across Browser Refreshes**:
   - Refresh the browser, or close the browser and open `http://localhost:3000/reports`.
   - Click **Open Dashboard** on the saved report card.
   - The source file is downloaded through authenticated private Storage access, and the dashboard calculations are recomputed server-side with saved filters and confirmed charts restored.
5. **Multi-User Isolation**:
   - Sign out and register a second user (e.g. `bob@example.com`).
   - Navigate to `/reports`: Bob cannot see Alice's reports or access Alice's datasets in Supabase Storage due to Row Level Security enforcement.
