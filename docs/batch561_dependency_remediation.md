# RecoverAI V2 — Batch 5.6.1: Local Environment Dependency Remediation

## 1. Problem Discovered
During the Batch 5.6 Integration Audit, a **P0 Blocker** was identified: `backend/requirements.txt` was completely missing the critical infrastructure dependencies introduced in architecture Batches 5.1–5.3 (Celery, Redis, Alembic, PostgreSQL drivers). Consequently, executing `pip install -r requirements.txt` resulted in an environment incapable of importing or running the application natively.

## 2. Root Cause
The `requirements.txt` file remained untouched since the initial mock-based architecture (Batch 1-4). When durable execution and background processing were implemented, the associated dependencies were installed directly into the development environment but were not frozen into `requirements.txt`.

## 3. Dependency Audit Table

| Package | Why Required | Imported By / Usage | Existing Requirement? |
| --- | --- | --- | --- |
| `fastapi` | Core web framework | `app.main`, routers | Yes |
| `sqlalchemy` | ORM | `app.database`, models | Yes |
| `celery` | Background tasks & durability | `app.worker.*` | **No (Missing)** |
| `redis` | Message broker & Event Bus | Celery config, `app.api.websocket` | **No (Missing)** |
| `alembic` | Database schema migrations | CLI | **No (Missing)** |
| `psycopg2-binary`| PostgreSQL adapter | DB Engine (`DATABASE_URL`) | **No (Missing)** |
| `websockets` | FastAPI WS support | `fastapi.websockets` | **No (Missing)** |
| `google-genai` | AI Provider (Gemini) | `app.services.llm` | Yes |
| `scikit-learn` | Machine Learning | `app.services.ml` | Yes |
| `pandas` | Data manipulation (ML) | `app.services.ml` | Yes |

## 4. Changes Made
1. Appended missing core packages (`celery`, `redis`, `alembic`, `psycopg2-binary`, `websockets`) to `backend/requirements.txt`.
2. Updated `.env.example` to accurately document the required `CELERY_BROKER_URL`.
3. Updated the `.env.example` `DATABASE_URL` placeholder to default to a `postgresql://` string, reinforcing that SQLite is fundamentally unsupported for execution invariants (`FOR UPDATE SKIP LOCKED`).
4. Fixed a trivial string syntax error (`"""`) in a test docstring (`test_postgres_concurrency.py:289`) that was preventing test suite collection.

## 5. requirements.txt Final Status
The file now accurately reflects all dependencies necessary to instantiate the RecoverAI API and Workers. Minimal, sensible compatible versions (e.g. `>=`) are used for reproducible installation without brittle over-pinning.

## 6. Fresh Environment Verification Results
**PASS**. Inside a clean `.venv` execution context:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
*Result:* Executed cleanly with Exit Code `0`.

## 7. Backend Import Verification
**PASS**. A non-destructive startup smoke test was executed against the freshly installed environment:
```powershell
python -c "import fastapi, sqlalchemy, celery, redis, alembic, app.main, app.worker.celery_app"
```
*Result:* Executed flawlessly (Exit Code `0`). No `ModuleNotFoundError` triggered. All core application components and Celery workers are fully discoverable.

## 8. Test Results
- **Frontend Build (`npm run build`):** **PASS** (100% built cleanly)
- **Backend Tests (`pytest tests/ -v`):** 
  - Passed: **131**
  - Skipped: **11**
  - Infrastructure-Blocked (Failed): **16**
  
*Note: The 16 failures are entirely expected `EXPECTED MISSING INFRASTRUCTURE ERROR` instances. They occur strictly in integration tests (`test_celery_worker.py`, `test_observability.py`, etc.) asserting against live connections to a running PostgreSQL or Redis instance, which were not spun up for this isolated dependency verification step.*

## 9. Remaining Infrastructure Requirements
The application dependencies are now fully satisfied. To actually process payments locally, the USER MUST install and run the backing services on Windows:
1. **PostgreSQL** (Port `5432`)
2. **Redis** (Port `6379`)

## 10. Exact Next Steps for Local Full-System Testing
1. Install and start native **PostgreSQL** and **Redis** servers on your Windows machine.
2. Ensure you have the `backend/.env` file populated with your `DATABASE_URL` and `CELERY_BROKER_URL`.
3. Run migrations: `alembic upgrade head`.
4. Boot the 4 runtime services:
   - FastAPI (`uvicorn app.main:app`)
   - Celery Worker (`celery -A app.worker.celery_app worker`)
   - Celery Beat (`celery -A app.worker.celery_app beat`)
   - Frontend (`npm run dev`)

---

# FINAL VERDICT

> Can a developer now clone the repository and run `pip install -r requirements.txt` without missing Python package errors?

**PASS**

The environment is now pristine, correctly documented, and completely decoupled from Docker. You are ready to start up the infrastructure and execute the full timeline demo.
