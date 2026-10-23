# Business Reporting Dashboard

An automated, verifiable reporting platform for business owners. Ingest raw spreadsheets (Excel and CSV), validate data integrity, inspect column classifications, and generate deterministic, executive-grade business dashboards.

---

## Architecture Overview

- **Frontend**: Next.js 14 (App Router), TypeScript (Strict Mode), Tailwind CSS, Lucide React.
- **Backend**: Python FastAPI, Pydantic, dynamic CORS configuration.
- **Database & Auth (Roadmap Phase 3)**: Supabase PostgreSQL, Supabase Auth, Row-Level Security (RLS).

---

## Directory Structure

```
business-reporting-dashboard/
├── frontend/
│   ├── app/
│   │   ├── globals.css         # Base styles & accessible focus rings
│   │   ├── layout.tsx          # App shell, responsive layout & metadata
│   │   ├── page.tsx            # Overview dashboard
│   │   ├── upload/page.tsx     # Dataset upload & validation shell
│   │   ├── reports/page.tsx    # Saved reports view with empty states
│   │   └── settings/page.tsx   # Workspace preferences & security roadmap
│   ├── components/
│   │   ├── Sidebar.tsx         # Desktop sidebar navigation
│   │   ├── MobileNav.tsx       # Responsive mobile navigation drawer
│   │   ├── Header.tsx          # Accessible page header
│   │   ├── SummaryCard.tsx     # KPI & status cards with honest metrics
│   │   └── EmptyState.tsx      # Reusable empty state component
│   ├── lib/
│   │   └── utils.ts            # Class merger (clsx + twMerge) & byte formatter
│   ├── public/                 # Static assets & favicon
│   ├── .env.example            # Frontend environment variable template
│   ├── package.json            # Frontend dependencies and scripts
│   ├── tsconfig.json           # Strict TypeScript configuration
│   └── tailwind.config.ts      # Tailwind design system tokens
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py             # FastAPI app with health check & dynamic CORS
│   ├── .env.example            # Backend environment variable template
│   └── requirements.txt        # Backend dependencies
├── docs/
│   └── PROJECT_STATUS.md       # Architecture, completed work, roadmap
├── .gitignore                  # Git ignore rules for Node, Python, and secrets
├── .env.example                # Root environment template
└── README.md                   # This document
```

---

## Getting Started

### Prerequisites

- **Node.js**: v18.17+ or v20+ (tested on Node v24)
- **Python**: 3.10+ (tested on Python 3.13)
- **Git**

---

### Running the Services Locally

To run the application, open **two separate terminal windows**:

#### Terminal 1: Backend (FastAPI)

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables (optional for default development):
   ```bash
   cp .env.example .env
   ```

5. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   The backend API will be available at `http://127.0.0.1:8000`.
   - Health check: `http://127.0.0.1:8000/health`
   - Interactive Swagger docs: `http://127.0.0.1:8000/docs`

---

#### Terminal 2: Frontend (Next.js)

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env.local
   ```

4. Start the Next.js development server:
   ```bash
   npm run dev
   ```
   The frontend application will be available at `http://localhost:3000`.

---

## Development Scripts

### Frontend

| Command | Description |
|---|---|
| `npm run dev` | Starts the Next.js development server on port 3000 |
| `npm run build` | Builds the production-ready Next.js bundle |
| `npm run start` | Starts the production server |
| `npm run lint` | Runs Next.js ESLint checks |
| `npm run typecheck` | Runs strict TypeScript compiler check (`tsc --noEmit`) |

---

## Phase Roadmap

- [x] **Phase 1: Project Foundation & Application Shell** (Completed)
- [ ] **Phase 2: Dataset Upload & Schema Validation** (FastAPI Excel/CSV parser, column type inference)
- [ ] **Phase 3: Database & Authentication** (Supabase PostgreSQL, RLS, Auth)
- [ ] **Phase 4: Dynamic Dashboard & Interactive Visualizations**
- [ ] **Phase 5: Automated PDF and Excel Export**
