# RecoverAI V2 — Batch 5.4: Production Observability & Monitoring Plan

## 1. Current Observability Gaps
- **Unstructured Logging:** Currently, logging uses plain text via `logging.StreamHandler`. It lacks reliable JSON structuring, making it difficult to parse in log aggregators.
- **Missing Correlation:** While `request_id` exists, `correlation_id` is missing and context is not automatically propagated into Celery tasks.
- **Print Statements:** Several utility scripts and fallback paths use raw `print()` statements.
- **Basic Health Checks:** The `/health` endpoint is a static response. There are no distinct liveness vs. readiness probes, and database/Redis connectivity is not verified.
- **Blind Spots in Safety States:** Operators have no visibility into how many `RecoveryAttempt`s are stuck in `UNKNOWN` or `ESCALATED`, or how many webhooks are `FAILED_PERMANENTLY`, without manual SQL queries.
- **Error Leakage:** No centralized exception handler is defined to guarantee that unexpected errors don't leak stack traces to API consumers.

## 2. Proposed Architecture

### Structured Logging (`app.core.logging`)
- Create a custom `JSONFormatter` that inherits from standard `logging.Formatter`.
- Extract `request_id`, `correlation_id`, `transaction_id`, etc., from `contextvars` and embed them into the JSON payload.
- Implement basic sanitization/redaction logic inside the formatter to scrub potential sensitive fields (e.g., secrets, tokens).

### Request Correlation (`app.api.middleware`)
- Update `RequestIDMiddleware` to extract or generate `X-Request-ID` and `X-Correlation-ID`.
- Attach these to `contextvars` for the logger to pick up.

### Health Endpoints (`app.api.health`)
- `GET /health/live`: Returns `{"status": "alive"}` instantly.
- `GET /health/ready`: Performs `SELECT 1` via SQLAlchemy and `PING` via Redis client. Fails if either is unavailable.

### Operational Metrics (`app.api.metrics`)
- `GET /metrics`: Returns JSON payload with counts for safety signals:
  - `RecoveryAttempt.status` = `UNKNOWN`, `ESCALATED`
  - `RecoveryAttempt` stuck in `EXECUTING` beyond `STUCK_EXECUTION_THRESHOLD_SECONDS`
  - `WebhookEvent.processing_status` = `FAILED`, `FAILED_PERMANENTLY`
- These endpoints will execute read-only queries directly via `db.query(...)`.

### Celery Observability (`app.worker.signals`)
- Hook into `@task_prerun`, `@task_postrun`, and `@task_failure` to log the lifecycle of tasks.
- Hook into `@before_task_publish` to inject `correlation_id` from `contextvars` into task headers so workers inherit the trace.

### Secure Error Handling (`app.main`)
- Add `@app.exception_handler(Exception)` to catch unhandled exceptions, log them securely as `ERROR` with stack traces, and return a sanitized `500 Internal Server Error` containing only the `request_id`.

## 3. Exact Files to Modify
- `backend/app/main.py`: Register new routers and exception handlers.
- `backend/app/api/middleware.py`: Add `correlation_id` context tracking.
- `backend/app/api/router.py`: Wire `/health` and `/metrics` routers.
- `backend/app/worker/celery_app.py`: Import signals.
- `backend/app/config.py`: Add `LOG_LEVEL`, `SERVICE_NAME`, `STUCK_EXECUTION_THRESHOLD_SECONDS`.
- `backend/.env.example`: Update.
- `backend/app/services/logger.py`: Delete (replaced by `app/core/logging.py`).
- Replace `print()` statements across scripts (`migrate_*.py`) and use structured logging.

## 4. New Files to Create
- `backend/app/core/logging.py`
- `backend/app/api/health.py`
- `backend/app/api/metrics.py`
- `backend/app/worker/signals.py`
- `backend/tests/integration/test_observability.py`
- `backend/tests/security/test_observability_security.py`

## 5. Security Risks & Mitigations
- **Leakage in Logs:** The `JSONFormatter` will filter out specific blacklisted keys.
- **Accidental Execution:** Metrics and health queries will exclusively use standard SQLAlchemy `SELECT` operations. They will absolutely not import `ExecutionGuard` or `state_machine.py`.
- **Data Exposure via Metrics:** Metrics will output aggregate integers (counts), never row data, ensuring no PII or amounts are exposed.

## 6. Performance Impact
- Structured logging overhead is negligible.
- Readiness probe uses `SELECT 1` which is instantaneous.
- Metrics endpoint uses `COUNT(*)` with `WHERE` clauses on indexed/low-cardinality columns (like `status`). This is extremely lightweight.
