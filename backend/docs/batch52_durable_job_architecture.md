# Batch 5.2 — Durable Job Architecture Plan

## Current Architecture
Presently, RecoverAI executes asynchronous and scheduled tasks within the main FastAPI process using two distinct methods:
1. **Request-Scoped Background Execution:** `BackgroundTasks` via `fastapi` offloads orchestration (`run_orchestrator_bg`). If the worker crashes immediately after acknowledging a webhook/payment, the recovery orchestration is dropped.
2. **Infinite Loop Scheduling:** An `asyncio.create_task` spins a while-true loop (`reconciliation_worker`) in `app/main.py`. This design creates redundant reconciliation workers in multi-process configurations (e.g., multiple Gunicorn workers or Kubernetes pods), causing concurrent contention on the SQLite/PostgreSQL locks.

## Proposed Architecture
We propose replacing the in-process asyncio mechanism with **Celery + Redis** to provide a persistent, multi-instance-capable, and distributed job queue.
- **Broker:** Redis (Durable task delivery and scheduling).
- **Workers:** Independent Celery worker processes running outside of the FastAPI HTTP server context.
- **Scheduler:** Celery Beat (distributed, single-instance scheduler for reconciliation sweeps).
- **Source of Truth:** PostgreSQL strictly retains its role as the authoritative state and idempotency store. Redis is strictly ephemeral transit memory.

### Queue Topology
- `high_priority` queue: Payment orchestration, webhooks.
- `reconciliation` queue: Scheduled state-sweeping jobs.
- `dead_letter` queue: Poisoned or terminally failed jobs for administrative review.

## Job Types and Retry Policies

The primary invariant is that **Celery must NEVER blindly retry financial execution actions.** Execution idempotency must remain firmly under the control of PostgreSQL, `ExecutionGuard`, and `IdempotencyRecord`.

### 1. Recovery Orchestrator Execution
- **Current:** `run_orchestrator_bg`
- **Proposed:** A Celery Task triggered upon payment failure.
- **Retry Policy:** **NO AUTOMATIC RETRY.**
  If a worker crashes during execution, the database state naturally drops into `UNKNOWN` or `EXECUTING` (orphaned). The scheduled reconciliation sweep will pick this up. Celery retries risk double-execution races if the crash happened post-gateway handoff.

### 2. Scheduled Reconciliation (The "Sweeper")
- **Current:** `reconciliation_worker` loop in `main.py`
- **Proposed:** Celery Beat triggering lightweight tasks every 5 minutes on the `reconciliation` queue.
- **Retry Policy:** **SAFE TO RETRY.**
  Reconciliation is strictly a read-only verification operation. It queries the gateway for actual financial status and transitions attempts logically. If this task crashes, it can safely be retried or simply ignored until the next 5-minute sweep.

### 3. Webhook Processing
- **Current:** Webhook events are processed synchronously or via background task.
- **Proposed:** Enqueue raw webhooks as Celery tasks to immediately free the HTTP listener.
- **Retry Policy:** **SAFE TO RETRY.**
  Webhooks use PostgreSQL unique constraints (`WebhookEvent` idempotency). If a worker crashes midway, retrying the webhook is entirely safe because the database layer handles deduplication.

### 4. Non-Financial Notifications / Analytics
- **Retry Policy:** **SAFE TO RETRY** (with exponential backoff).

## Redis Requirements
- **Redis Broker:** Handles job transit. TLS required for production transit encryption (`rediss://`).
- **Result Backend:** **NOT REQUIRED / DISABLED.** We do not need Celery to store task outcomes in Redis. Task outcomes are natively logged via PostgreSQL `AuditLog` and transaction status transitions.
- **Connection configuration:** Timeouts configured to fail gracefully, avoiding zombie connections.

## PostgreSQL Relationship
PostgreSQL continues to own the financial safety layer.
- Redis acts purely as an enqueuer. 
- If Redis loses data (flushall, cache eviction, broker crash), PostgreSQL ensures financial integrity. Dropped orchestrator jobs manifest as `PENDING`/`UNKNOWN` orphans in PostgreSQL, which the next Celery Beat reconciliation sweep natively detects and repairs. No transaction can be permanently lost due to a Redis failure.

## Testing Strategy
Introducing Celery requires robust integration tests to ensure the asynchronous transit layer does not bypass existing safety boundaries. 

1. **Worker Crash Test:** Simulate a `sys.exit()` in a Celery worker immediately after the gateway executes. Prove that the transaction lands in `UNKNOWN` and the reconciliation sweep successfully parses it.
2. **Duplicate Task Delivery Test:** Manually push two identical `process_orchestrator` jobs to Celery. Prove `ExecutionGuard` blocks the second one dynamically.
3. **Multi-Worker Concurrency Test:** Ensure multiple Celery workers grabbing overlapping records correctly obey optimistic locking invariants.
4. **Redis Data-Loss Test:** Flush Redis entirely midway through orchestration. Prove that the database reconciles safely during the next Celery Beat tick.
5. **ESCALATED / UNKNOWN Protection:** Prove the queue cannot overwrite an `ESCALATED` manual-review boundary.

## Migration and Rollback Strategy
- **Migration:** 
  1. Remove `asyncio.create_task` from `main.py`.
  2. Implement `app/worker.py` (Celery initialization).
  3. Swap `background_tasks.add_task` with `.delay()` enqueue calls.
- **Rollback:** Retain the `run_orchestrator_bg` functions as fallback mechanisms. If the `CELERY_BROKER_URL` environment variable is not set, dynamically fall back to the existing `fastapi.BackgroundTasks` logic (local mode).

## Batch 5.2 Readiness Verdict

**READY FOR IMPLEMENTATION**
