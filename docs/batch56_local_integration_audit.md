# RecoverAI V2 — Batch 5.6: Local Full-System Integration Audit

## 1. Executive Summary
The system architecture is remarkably well-suited for local execution without Docker. The configuration supports dynamic local overrides and gracefully falls back to dev-mode defaults. However, there is a **P0 Blocker** related to missing dependencies in `requirements.txt` that prevents a clean local install. Once fixed, the system will run flawlessly across terminal sessions natively.

## 2. Local Architecture Diagram
```mermaid
graph TD
    UI[Frontend (React/Vite)] -->|HTTP POST| API[FastAPI (Uvicorn)]
    UI <-->|WebSocket| API
    
    API --> DB[(PostgreSQL)]
    API --> Broker[Redis]
    
    Broker --> CeleryWorker[Celery Worker]
    CeleryWorker --> StateMachine[Recovery Orchestrator]
    
    StateMachine --> Broker
    StateMachine --> DB
    
    CeleryBeat[Celery Beat] --> Broker
```

## 3. Required Software
### Required
- **Python 3.9+**
- **Node.js 18+**
- **PostgreSQL**: Mandatory. SQLite fallback exists in `config.py`, but it will silently fail execution layer invariants and skip locks (`FOR UPDATE SKIP LOCKED`), thus breaking concurrency testing.
- **Redis**: Mandatory. Powers both Celery Broker and WebSocket Pub/Sub event bus.

### NOT Required
- Docker (completely unnecessary)
- Kubernetes
- RabbitMQ (Redis handles brokering)
- Cloud Services (AWS/GCP)

## 4. Environment Variables

| Variable | Required? | Used By | Example Local Value | Purpose |
|----------|-----------|---------|---------------------|---------|
| `ENVIRONMENT` | No | Config | `development` | Toggles strict prod safety checks |
| `DATABASE_URL` | Yes | API / Alembic | `postgresql://usr:pass@localhost:5432/recoverai` | Primary persistence layer |
| `CELERY_BROKER_URL` | No | API / Celery | `redis://localhost:6379/0` | Message broker and event bus |
| `MERCHANT_API_KEY` | No (Dev) | API Auth | `test_secret_key_123` | Secures core endpoints |
| `WEBHOOK_SECRET` | No (Dev) | Webhooks | `test_webhook_secret_456` | Secures webhook ingestion |
| `OBSERVABILITY_API_KEY` | No (Dev) | Metrics | `test_obs_key_123` | Protects observability endpoints |
| `LLM_PROVIDER` | No | AI Engine | `mock` (or `gemini`) | Determines which LLM to invoke |
| `GEMINI_API_KEY` | If gemini | AI Engine | `AIzaSy...` | Real LLM inference |
| `VITE_API_BASE_URL` | No | Frontend | `http://127.0.0.1:8000/api/v1` | HTTP Target |
| `VITE_WS_BASE_URL` | No | Frontend | `ws://127.0.0.1:8000/api/v1` | WS Target |

## 5. PostgreSQL Setup Requirements
- **Version**: Any modern PG (13+) supporting `FOR UPDATE SKIP LOCKED`.
- **Database Name**: Configurable via URL, e.g. `recoverai`.
- **Startup Command**: Native OS service start or run the provided `run_pg.ps1`.
- **Migrations**: MUST be run (`alembic upgrade head`). 
- **Migration Status**: All recent migrations (including `add_webhook_retry_fields`) are present and intact in the repository.

## 6. Redis Setup Requirements
- The exact same Redis instance safely handles both Celery task brokering and Pub/Sub recovery events over separate channels/keys.
- Redis must be running locally (`localhost:6379`).

## 7. Backend Startup Command
```bash
cd backend
uvicorn app.main:app --reload
```

## 8. Celery Worker Startup Command
```bash
cd backend
celery -A app.worker.celery_app worker --loglevel=info -Q high_priority,reconciliation,celery
```
*(Worker correctly routes `process_orchestrator` and `process_webhook` to `high_priority` via `celery_app.py` config).*

## 9. Celery Beat Startup Command
```bash
cd backend
celery -A app.worker.celery_app beat --loglevel=info
```

## 10. Frontend Startup Command
```bash
cd frontend
npm install
npm run dev
```

## 11. Correct Startup Order
For full end-to-end integration:
1. **Terminal 1**: PostgreSQL Server
2. **Terminal 2**: Redis Server
3. **Terminal 3**: `alembic upgrade head` *(Run once)*
4. **Terminal 4**: FastAPI (`uvicorn`)
5. **Terminal 5**: Celery Worker
6. **Terminal 6**: Celery Beat
7. **Terminal 7**: Frontend (`npm run dev`)

## 12. Full End-to-End Flow Audit
Tracing the user journey through the code:
1. Start frontend: **PASS** (Vite handles localhost endpoints cleanly).
2. Open Checkout page: **PASS**.
3. Submit simulated failed payment: **PASS**.
4. POST /payments: **PASS** (Reaches FastAPI router).
5. Transaction saved to PostgreSQL: **PASS** (Requires PostgreSQL database).
6. Celery task enqueued: **PASS**.
7. Celery worker receives task: **PASS** (Explicit routing configured in `celery_app.py`).
8. RecoveryOrchestrator starts: **PASS**.
9. State machine executes: **PASS**.
10. ML prediction emitted: **PASS** (Published to Redis).
11. AI recommendation emitted: **PASS** (Published to Redis).
12. Policy decision emitted: **PASS** (Published to Redis).
13. ExecutionGuard evaluates action: **PASS** (Safely utilizes `with_for_update()`).
14. Mock Gateway executes: **PASS**.
15. Database state updated: **PASS**.
16. Redis terminal event published: **PASS**.
17. WebSocket forwards event: **PASS** (`app/api/websocket.py` correctly subscribes).
18. Frontend receives event: **PASS**.
19. PaymentProcessing reaches terminal state: **PASS**.
20. PaymentSuccess / PaymentFailed displayed: **PASS**.
21. PaymentDetails displays audit trail: **PASS**.

## 13. WebSocket Local Testing Audit
- **PASS**. Both the frontend (`ws://`) and backend (`/ws/recovery/{transaction_id}`) explicitly support unencrypted local WebSockets. There are no hardcoded `wss://` constraints blocking localhost testing. The robust Batch 5.5 fallback polling handles connection blips natively.

## 14. Health & Metrics Audit
- `GET /health/live`: **PASS**. Returns 200 OK immediately.
- `GET /health/ready`: **PASS**. Safely queries Postgres (`SELECT 1`) and pings Redis (`r.ping()`) without exposing secrets. Fails as expected with 503 if down.
- `GET /metrics`: **PASS**. Protected by `X-Observability-API-Key` (defaults safely to `test_obs_key_123`).

## 15. Integration Blockers

### P0 - Cannot start system (Blocker)
- **Missing Requirements**: `backend/requirements.txt` was not updated during architecture batches 5.1–5.3. It is missing critical infrastructure packages:
  - `celery`
  - `redis`
  - `alembic`
  - `psycopg2-binary` (or equivalent PostgreSQL driver)
  - `websockets`
  *Without these, `pip install -r requirements.txt` succeeds, but the application instantly crashes on boot.*

### P1 / P2 / P3
- None.

## 16. Exact Local Testing Checklist
1. Install Python 3.9+ and Node.js 18+.
2. Install & Start PostgreSQL & Redis locally.
3. Update `requirements.txt` with missing dependencies.
4. Run `pip install -r requirements.txt`.
5. Set `DATABASE_URL=postgresql://user:pass@localhost:5432/dbname`.
6. Run `alembic upgrade head`.
7. Start FastAPI, Celery Worker, and Celery Beat in separate terminals.
8. Run `npm install` && `npm run dev` in the frontend directory.
9. Open browser to `http://localhost:5173`.

## 17. Recommended Fix Plan
- Add `celery`, `redis`, `alembic`, `psycopg2-binary`, and `websockets` to `backend/requirements.txt`.
- Emphasize to the user that `DATABASE_URL` MUST be overridden to point to PostgreSQL to avoid SQLite concurrency crashes.

---

# FINAL QUESTION

> Can RecoverAI V2 currently be run completely locally without Docker?

**PASS WITH MINOR FIXES** — Small integration fixes required

*The codebase and architecture are perfectly primed for local execution without Docker, requiring 7 straightforward processes. However, a stale `requirements.txt` file missing `celery`, `redis`, `alembic`, and `psycopg2` acts as a hard P0 blocker preventing the initial Python environment setup. Fixing that single file will unlock the entire system.*
