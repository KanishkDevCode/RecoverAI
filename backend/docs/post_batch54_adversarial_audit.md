# Post-Batch 5.4: Adversarial Audit (Observability & Monitoring)

## System State
- Batch 5.1: Concurrency and database correctness.
- Batch 5.2: Celery workers and asynchronous task durability.
- Batch 5.3: Webhook deduplication and infinite-retry poison pill fixes.
- **Batch 5.4**: Production observability, structured JSON logging, metrics, health endpoints.

## Attack Vectors Audited

### 1. The "Observer Effect" Attack (Execution Bypass)
**Hypothesis:** If an attacker can trigger the `/metrics` endpoint continuously, it could invoke state machine handlers and accidentally mutate the database (e.g. by generating read-modify-write cycles).
**Audit Result:** PASS. The `/metrics` endpoint has been strictly confined to SQLAlchemy `SELECT COUNT(*)` statements. The `ExecutionGuard` and `StateMachine` modules are completely decoupled and are never imported or invoked by the metrics controller. Security integration tests guarantee this invariant.

### 2. Log Forgery / PII Leakage
**Hypothesis:** An attacker submits payloads containing malicious strings like `"merchant_api_key": "hacked"` or triggering exceptions that cause the framework to print database passwords to application logs.
**Audit Result:** PASS. 
1. The custom `JSONFormatter` in `app/core/logging.py` contains a strict `SENSITIVE_KEYS` blacklist that aggressively scrubs secrets (`merchant_api_key`, `webhook_secret`, `authorization`, etc.) from contextual extra payloads.
2. A global FastAPI exception handler intercepts all unhandled 500 exceptions, returning only a safe error message and a `request_id`, while securely logging the stack trace locally without exposing it to the client.

### 3. Metric Snooping (Information Disclosure)
**Hypothesis:** An unauthorized user queries `/metrics` to discern system load, revenue volume, or specific failure modes to map out timing attacks.
**Audit Result:** PASS. The metrics endpoint is protected by a strict `OBSERVABILITY_API_KEY` header. Missing or invalid keys result in a 403 Forbidden. Additionally, the metrics payload returns aggregate counts, never individual row data, ensuring zero exposure of specific payment amounts or PII.

### 4. Celery Context Bleed
**Hypothesis:** Because Celery workers reuse threads/processes, correlation IDs from Task A might bleed into Task B, resulting in intertwined, useless trace logs.
**Audit Result:** PASS. By utilizing Python 3 `contextvars`, the `request_id` and `correlation_id` are natively bound to the async execution context. `app/worker/signals.py` explicitly hydrates these context variables during `@task_prerun` by reading the injected Celery headers, ensuring perfect isolation per task invocation.

## Summary
The observability infrastructure successfully adheres to the passive monitoring invariant: it can observe the system without controlling it, and it can expose aggregate metrics without exposing PII. The system is structurally prepared for production deployment.
