# Batch 5.3.1 — Webhook Retry Safety Remediation

## Overview
This document outlines the changes implemented during Batch 5.3.1 to resolve the P1 vulnerability discovered in the Post-Batch 5.3 adversarial audit.

The vulnerability existed because `reconcile_pending_webhooks()` swept both `PENDING` and `FAILED` WebhookEvents using the immutable `received_at` timestamp. A permanently failing webhook could thus satisfy the reconciliation condition forever, leading to an infinite Celery retry loop that could starve the worker queue.

## Goal
Make webhook retry behavior durable but **BOUNDED**. The system must continue recovering legitimate transient failures while preventing poison-pill events from being retried forever.

## Implementation Details

### Schema Changes
The following fields were added to the `WebhookEvent` model in PostgreSQL via Alembic migration (`faecf6256136`):
- `retry_count` (Integer, default=0): Tracks the number of retry attempts for the webhook event.
- `last_attempt_at` (DateTime, nullable): Records the timestamp of the last attempt to process the webhook.

### Bounded Retry Logic
The `process_webhook` Celery task in `app/worker/tasks.py` was updated to implement bounded retries:
1. Atomically locks the event using `with_for_update()`.
2. Updates `last_attempt_at` before processing.
3. If processing fails, it increments `retry_count`.
4. If `retry_count >= MAX_WEBHOOK_RETRIES` (default 3), the status is transitioned to `FAILED_PERMANENTLY`.
5. Otherwise, the status is set to `FAILED`.

### Atomic Budget Enforcement
The reconciliation logic in `app/services/reconciliation.py` was updated to use PostgreSQL-safe optimistic concurrency and atomic UPDATE semantics:
1. Sweeps `PENDING` events older than `WEBHOOK_RECONCILIATION_TIMEOUT`.
2. Sweeps `FAILED` events that have not exceeded the retry budget (`retry_count < MAX_WEBHOOK_RETRIES`) and where `last_attempt_at` is older than the timeout.
3. Uses `with_for_update(skip_locked=True)` to prevent race conditions among concurrent workers.
4. Terminal state `FAILED_PERMANENTLY` is ignored by the reconciliation loop and can never be automatically re-enqueued.

## Financial Safety Invariants Maintained
- **No Financial Execution:** Webhook processing remains strictly for state reconciliation. It does not call `execute_recovery_action` or `process_refund`.
- **Database Source of Truth:** PostgreSQL remains the sole source of truth for webhook state and retry budgets.
- **Concurrency Protections:** `with_for_update` continues to protect against concurrent processing and race conditions.

## Verification
A comprehensive test suite was added in `tests/security/test_batch531_webhook_retry.py` to verify:
- Pending and failed webhooks are correctly reconciled and re-enqueued.
- Failed webhooks increment `retry_count` and transition to `FAILED_PERMANENTLY` after reaching the maximum retries.
- Poison-pill webhooks are successfully terminated and do not cause infinite loops.
- Concurrent reconciliation avoids duplicate processing.
- `FAILED_PERMANENTLY` events are strictly ignored by the reconciliation loop.
- The webhook processing path never executes financial operations directly.
