# RecoverAI V2 — Batch 4: Gateway Abstraction & Refund Reliability

## Architecture Overview

### Before Architecture
- The `RecoveryOrchestrator` directly imported the `RazorpayMockService`.
- Refunds were handled directly inside the `app/api/refunds.py` router.
- `ExecutionGuard` imported the mock directly.
- Webhooks were not supported; refunds used a naive background task simulator to set the `REFUNDED` status blindly after a delay.
- Reconciliation only handled payments, ignoring refunds stuck in intermediate states.

### After Architecture
- **Gateway Abstraction**: A rigorous `GatewayInterface` was defined (`app/gateways/base.py`). The application depends on this abstraction, instantiated via `get_gateway()`.
- **Execution Guard**: Hardened as a DI-injected boundary that rigorously validates all financial attempts and terminals states before pushing to the `GatewayInterface`.
- **Refund Service**: Extracted into `RefundService` (`app/services/refund_service.py`), which manages rigorous state checking, creates audit logs, and coordinates safely with the gateway.
- **Webhook Architecture**: Implemented a resilient webhook ingestion model. 
- **Reconciliation**: Extended `reconciliation_worker` to automatically detect and verify refunds stuck in `REFUND_PROCESSING` or `REFUND_UNKNOWN` without blindly creating duplicate refunds.

## Key Implementations

### Gateway Abstraction
A `GatewayInterface` Protocol was introduced. `RazorpayMockService` was refactored into `MockGateway` implementing this interface. Consumers use `get_gateway()`.

### Execution Guard
`ExecutionGuard` was updated to explicitly fail if a transaction's recovery state is already terminal (preventing blind retries), taking the `GatewayInterface` as a dependency. It continues to be the only application-level code that calls `execute_recovery_action`.

### Refund Service & Lifecycle
Refund requests undergo strict validation: only `success` or `SUCCEEDED` (recovered) transactions can be refunded.
The state transitions enforced are: `REFUND_REQUESTED` → `REFUND_PROCESSING` → `REFUNDED`.

### Webhook Architecture & Authentication
A new `WebhookEvent` model stores incoming payload hashes and status for idempotency.
The endpoint `POST /api/v1/webhooks/gateway` requires an `X-Razorpay-Signature` which is validated using `HMAC-SHA256` against a dedicated `WEBHOOK_SECRET`.
Webhooks are strictly read-only for state reconciliation; they do not blindly execute new financial operations.

### Reconciliation
`reconcile_stuck_refunds` queries transactions stuck in processing states beyond the timeout (configured via `REFUND_RECONCILIATION_TIMEOUT_SECONDS`, default 300s). It uses `verify_refund()` strictly read-only.

### Idempotency and Crash Recovery
- **Application Idempotency**: Handled using persistent DB-level keys ensuring duplicate local requests do not hit the gateway.
- **Gateway Idempotency**: Enforced by the gateway interface using passed idempotency keys.
- **Ambiguous External Outcomes**: If the server crashes during refund processing, the state remains `REFUND_PROCESSING`. The background worker catches this and queries the gateway to reach the verified final state.

## Failure Scenarios Tested
- Gateway timeout resulting in `REFUND_UNKNOWN` is reconciled to final state.
- Duplicate refunds yield an idempotent response without duplicate execution.
- Concurrent refunds handled via application-level idempotency locks.
- Duplicate webhook payloads yield a single state transition.
- Invalid webhook signature returns 401 Unauthorized.
- Failed or un-captured payments are explicitly rejected from refunds.

## Tests & Builds

### Test Count
- Total Tests: 103
- Passed: 103
- Failed: 0

### Exact pytest output
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\CODE\RevenueAi\recoverai\backend\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\CODE\RevenueAi\recoverai\backend
plugins: anyio-4.14.2
collecting ... collected 103 items

...
===================== 103 passed, 582 warnings in 12.66s ======================
```

### Exact npm build output
```text
> frontend@0.0.0 build
> vite build

vite v8.2.2 building client environment for production...
transforming...
✓ 1826 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.56 kB │ gzip:  0.35 kB
dist/assets/index-Dtz2C0QK.css   16.54 kB │ gzip:  3.45 kB
dist/assets/index-D5l-lCD_.js   281.24 kB │ gzip: 84.79 kB

✓ built in 405ms
```

## Remaining Limitations
1. **SQLite Concurrency**: Still using SQLite; highly concurrent webhook ingestion requires optimistic concurrency and row locking native to Postgres.
2. **Gateway Abstraction**: While the abstraction is rigorous, we still only have a `MockGateway`. A real Razorpay adapter is needed before true production use. 
3. **Refund Table**: Refunds are still tied 1:1 on the `Transaction` table (`refund_status`, `refund_amount`). Partial refunds or multiple distinct refunds for a single transaction will require extracting refunds into a dedicated 1-to-many model.
