# Local integration verification

Run these commands from a normal Windows terminal or Linux shell. Use a
dedicated test database and storage root; do not point them at production or a
user's existing data.

## Backend regression suite

```powershell
cd backend
python -m pytest --collect-only -q
python -m pytest -q
```

On Windows, if the default temporary directory is restricted, set a writable
temporary directory before running pytest:

```powershell
$env:TEMP = "$PWD\.test-temp"
$env:TMP = $env:TEMP
python -m pytest -q
```

The current sandbox cannot run Starlette `TestClient` because its AnyIO portal
cannot create the Windows socketpair. A normal Windows or Linux runner is
required for the HTTP integration tests.

## Local services and application

```powershell
docker compose -f infra/docker-compose.yml up -d postgres redis api worker
Copy-Item backend/.env.example backend/.env
alembic -c backend/alembic.ini upgrade head
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 18001
celery -A app.worker.celery_app.celery_app worker --workdir backend --loglevel=INFO --pool=solo
```

In another terminal, start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

The synthetic workbook for the acceptance flow is
`sample_data/Business_Reporting_Dashboard_Synthetic_Test_Workbook.xlsx`.
