# Development commands

Run commands from the repository root unless noted otherwise.

## Backend

```powershell
pip install -r backend/requirements.txt
$env:PYTHONPATH="backend"
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Frontend

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

## Tests and builds

```powershell
python -m pytest -q
npm --prefix frontend run build
```

The root test suite contains cross-service checks. Backend unit and integration tests live under `backend/tests/`; pytest discovers them from the repository root using `pytest.ini`.

## Supabase

Two schemas are kept. The running backend uses
`backend/src/memory/migrations/` through `scripts/database/run_migration.py`.
The local Supabase design uses `supabase/migrations/` and `supabase/seed.sql`,
applied with `npx supabase db reset`.

See `docs/database/schema.md` for which schema is which, and
`docs/database/local_and_remote.md` for the CLI, the `.env` switch, and the
catalog import.

## Docker

```powershell
docker compose build
docker compose up -d
```

Compose builds the backend from `backend/Dockerfile` and the frontend from `frontend/Dockerfile`, with the repository root as each build context so the backend can include reference data without changing its runtime paths.
