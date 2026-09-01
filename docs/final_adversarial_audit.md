# RecoverAI V2 — Final Adversarial Audit

## Executive Summary
This document represents a comprehensive, read-only security and financial-integrity audit of the RecoverAI codebase following the completion of Batches 1–4. The audit evaluates whether the system satisfies its core claims of financial safety, idempotency, and state integrity.

While significant hardening has been achieved (e.g., ExecutionGuard, HMAC webhook signing, state machine versioning), **the system is NOT ready for production**. The audit uncovered two P0 financial execution vulnerabilities and several P1 reliability issues that break the "at-most-once" execution guarantee.

## Architecture Reviewed
- Payment ingestion (`app/api/payments.py`)
- Core Orchestrator (`app/services/orchestrator.py`)
- State Machine (`app/services/state_machine.py`)
- Execution Guard (`app/services/execution_guard.py`)
- Refund Service (`app/services/refund_service.py`)
- Webhooks (`app/api/webhooks.py`)
- Reconciliation Worker (`app/services/reconciliation.py`)
- Mock Gateway (`app/services/razorpay_mock.py`)

## Findings

### P0 Findings (Financial Execution Vulnerabilities)
1. **Concurrent Refund Race Condition**
   - **Location**: `RefundService.initiate_refund`
   - **Vulnerability**: The check `if txn.refund_status in [...]` does not use row-level locking (`with_for_update()`) or optimistic concurrency control. Two concurrent requests with *different* Idempotency-Keys will both read `None`, bypass the check, and simultaneously issue two discrete refund calls to the gateway. The gateway's idempotency table will accept both because the keys differ.

2. **Crash-Induced Infinite Retry Loop (Gateway Success + DB Failure)**
   - **Location**: `orchestrator.py` & `execution_guard.py`
   - **Vulnerability**: If the process crashes immediately after `gateway.execute_recovery_action` completes (where `RecoveryAttempt` is marked `SUCCEEDED`), but before `orchestrator.py` commits `Transaction.recovery_status = "SUCCEEDED"`, the transaction remains `NOT_STARTED`. `ExecutionGuard` explicitly uses `txn.recovery_status` to prevent duplicate execution. Since it is still `NOT_STARTED`, a subsequent client request with a new Idempotency-Key will bypass the guard, create a new attempt, and execute a duplicate charge.

### P1 Findings (Serious Reliability/Security Issues)
1. **Swallowed IntegrityError in Payment Creation**
   - **Location**: `create_payment` in `payments.py`
   - **Issue**: If an `IntegrityError` occurs during transaction insertion (e.g., duplicate transaction ID), the exception is swallowed if an `Idempotency-Key` is present. The API will return `200 OK` (if live mode) or spawn a duplicate background recovery task without persisting the transaction state, violating data integrity and allowing silent failures.

2. **Stale AUTHORIZED State Orphan**
   - **Location**: `reconciliation.py` -> `reconcile_orphaned_attempts`
   - **Issue**: If a crash occurs after transitioning an attempt to `AUTHORIZED` but before `EXECUTING`, the attempt is orphaned forever. The reconciliation worker explicitly only rescues `PENDING`, `EXECUTING`, and `VERIFYING` states, causing the transaction to block indefinitely.

### P2 Findings (Architectural Weaknesses)
1. **Webhook Bypasses Refund State Machine**
   - **Location**: `_process_refund_completed` in `webhooks.py`
   - **Issue**: The webhook unconditionally sets `txn.refund_status = "REFUNDED"` without verifying that a refund was actually initiated (`REFUND_REQUESTED` or `REFUND_PROCESSING`). An unexpected external webhook can arbitrarily alter financial state.
2. **SQLite Concurrency Limitations**
   - **Issue**: The system relies heavily on DB-level constraints for idempotency, but lacks true `SELECT ... FOR UPDATE` capabilities necessary for safe concurrent processing of shared rows (like `Transaction`).

### P3 Findings (Documentation/Quality)
1. **Test Coverage Gaps**: No concurrent threaded tests exist for `initiate_refund`. No crash-simulation tests exist for the boundary between gateway execution and orchestrator transaction commit.

---

## Attack Matrix

| Attack / Failure | Can it happen? | Why? | Existing Protection | Existing Test | Severity |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Duplicate payment** | Yes | Swallowed `IntegrityError` in API | DB Unique Constraint (bypassed) | None | P1 |
| **Duplicate recovery** | Yes | Crash between gateway and transaction commit | `ExecutionGuard` (flawed check) | None | P0 |
| **Duplicate refund** | Yes | No row-locks during initiation | `refund_status` check (racy) | None | P0 |
| **Concurrent payment** | No | IdempotencyRecord constraint | `IdempotencyRecord` table | Yes | Safe |
| **Concurrent recovery** | No | OCC on `RecoveryAttempt` | `version` field | Yes | Safe |
| **Concurrent refund** | Yes | No OCC or row-level lock on `Transaction` | None | None | P0 |
| **Prompt injection** | No | `evaluate_policy` hard bounds | Policy Engine | Yes | Safe |
| **Policy bypass** | No | `ExecutionGuard` enforces state | `ExecutionGuard` | Yes | Safe |
| **Gateway timeout** | No | Caught and reconciled | `UNKNOWN` state + Worker | Yes | Safe |
| **Gateway success + DB fail** | Yes | `ExecutionGuard` checks wrong table | None | None | P0 |
| **Crash during execution** | No | Rescued by reconciliation | `reconcile_orphaned_attempts` | Yes | Safe |
| **Crash after execution** | Yes | Leaves transaction `NOT_STARTED` | None | None | P0 |
| **Forged webhook** | No | HMAC signature validation | `verify_webhook_signature` | Yes | Safe |
| **Replay webhook** | No | `WebhookEvent` primary key | `WebhookEvent` table | Yes | Safe |
| **Stale state transition** | No | Prevented by OCC `version` | `state_machine.py` | Yes | Safe |
| **Unauthorized API call** | No | `X-API-Key` required | `get_api_key` | Yes | Safe |
| **Rate-limit abuse** | No | RateLimiter dependency | Token bucket | Yes | Safe |
| **Cross-customer data** | Yes/No | API allows arbitrary `customer_id` | N/A (Internal API assumption) | None | P2 |
| **Invalid financial amount** | No | Minor units conversion enforced | `to_minor_units` | Yes | Safe |
| **Refund amount manipulation**| No | Full refund enforced | Hardcoded `txn.amount` | Yes | Safe |

---

## Analysis Details

### State-Machine Analysis
The canonical state machine (`PENDING` → `AUTHORIZED` → `EXECUTING` → `SUCCEEDED`/`FAILED`) is well-protected by Optimistic Concurrency Control (OCC) via the `version` column. Concurrent transitions on the *same attempt* are mathematically impossible. However, the `AUTHORIZED` state was forgotten in the orphan reconciliation cron script.

### Idempotency Analysis
Idempotency using the `IdempotencyRecord` table is structurally sound. However, the API wrapper `create_payment` improperly catches `IntegrityError` for `Transaction` insertion and allows the request to proceed if an idempotency key is present, violating strict idempotency semantics.

### Gateway Execution Analysis
`ExecutionGuard` successfully prevents LLM hallucinations and policy bypasses. However, its defense against replay attacks relies on `txn.recovery_status`. Because `txn.recovery_status` is updated *after* the gateway executes, a crash leaves a window where the system forgets it successfully charged the customer, allowing infinite retries.

### Refund Analysis
Refunds are dangerously vulnerable to race conditions because `RefundService` does not use OCC or `with_for_update()`. Two concurrent requests will read `refund_status = None` simultaneously and issue two refunds. Webhooks also blindly transition refunds to `REFUNDED` without validating prior system intent.

### Webhook & Authentication Analysis
Webhooks are secured with a dedicated `WEBHOOK_SECRET` and HMAC-SHA256, mitigating forgery. The `WebhookEvent` table effectively neutralizes replay attacks. API routes correctly utilize `Depends(get_api_key)` and WebSockets utilize `get_ws_api_key`.

---

## Claim Verification

- **"at-most-once"**: **NOT SUPPORTED**. Fails due to the gateway success + DB failure crash window (P0) and concurrent refund race condition (P0).
- **"zero duplicate executions"**: **NOT SUPPORTED**. Same as above.
- **"financially safe"**: **NOT SUPPORTED**. Vulnerable to double charging and double refunding.
- **"idempotent"**: **PARTIALLY SUPPORTED**. Idempotency works for network retries, but the swallowed `IntegrityError` in `payments.py` corrupts the DB state on duplicate IDs.
- **"reconciliation safe"**: **PARTIALLY SUPPORTED**. Reconciles `UNKNOWN` correctly, but ignores orphaned `AUTHORIZED` states.

---

## Recommended Fixes (Priority Order)

1. **(P0) Fix Gateway Success Crash Window**: Update `ExecutionGuard` to query `RecoveryAttempt` directly to check for any `SUCCEEDED` attempts, rather than relying on `Transaction.recovery_status`.
2. **(P0) Fix Concurrent Refunds**: Implement row-level locking (`with_for_update()`) in `RefundService.initiate_refund` when querying the transaction, and migrate to Postgres for true locking support.
3. **(P1) Fix Swallowed IntegrityError**: In `payments.py`, if a `Transaction` insertion fails due to `IntegrityError`, it MUST fail the request (409) rather than proceeding to spawn background tasks.
4. **(P1) Rescue AUTHORIZED Orphans**: Add `"AUTHORIZED"` to the list of states targeted by `reconcile_orphaned_attempts`.
5. **(P2) Validate Webhook Intent**: Update `webhooks.py` to assert that `txn.refund_status` is `REFUND_REQUESTED` or `REFUND_PROCESSING` before blindly transitioning it to `REFUNDED`.

---

## Audit Metadata
- **Files Inspected**: `payments.py`, `orchestrator.py`, `state_machine.py`, `execution_guard.py`, `refund_service.py`, `webhooks.py`, `reconciliation.py`, `razorpay_mock.py`, `dependencies.py`
- **Total Findings**: 2x P0, 2x P1, 2x P2, 1x P3
- **Financial-Safety Issues (P0)**: YES (2)
- **Serious Reliability Issues (P1)**: YES (2)
- **Ready for Next Phase?**: **NO**. The identified P0 and P1 vulnerabilities must be remediated before proceeding to Batch 5.
