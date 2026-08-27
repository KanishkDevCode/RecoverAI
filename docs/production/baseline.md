# RecoverAI - Production Readiness Baseline

**Date:** 2026-08-27
**Scope:** Complete backend architecture gap analysis

This document establishes the factual baseline of the RecoverAI backend architecture before proceeding with hardening and production readiness changes.

---

## 1. Complete Backend Directory Tree

**Status:** PARTIAL

```
backend/
├── app/
│   ├── agents/
│   │   └── diagnosis_agent.py
│   ├── api/
│   │   └── router.py
│   ├── models/
│   │   └── db_models.py
│   ├── policy/
│   │   └── rules.py
│   ├── schemas/
│   │   ├── agent_schema.py
│   │   ├── events.py
│   │   └── transaction.py
│   ├── services/
│   │   ├── audit_logger.py
│   │   ├── event_bus.py
│   │   ├── feature_store.py
│   │   ├── ml_service.py
│   │   ├── orchestrator.py
│   │   ├── razorpay_mock.py
│   │   └── state_machine.py
│   ├── database.py
│   └── main.py
├── scripts/
├── tests/
│   ├── api/
│   ├── e2e/
│   ├── integration/
│   ├── security/
│   ├── unit/
│   └── conftest.py
├── .env
├── .env.example
├── requirements.txt
└── (Sqlite DB files)
```

**Notes:** The directory tree is established but components like the API layer are heavily monolithic (`router.py`), and critical components like `execution_guard` and `webhook_handler` are missing entirely.

## 2. Every API Endpoint

**Status:** PARTIAL

- `GET /health` (main.py): Health check.
- `GET /api/transactions` (main.py) [SECURITY RISK]: Unauthenticated mock endpoint.
- `POST /api/diagnose` (main.py) [SECURITY RISK]: Unauthenticated, exposes ML+LLM pipeline directly.
- `POST /api/v1/payments` (router.py): Simulates initial payment gateway attempt and kicks off recovery if failed.
- `POST /api/v1/recovery/process` (router.py): Triggers recovery orchestrator for an arbitrary transaction.
- `WS /api/v1/ws/recovery/{transaction_id}` (router.py): WebSocket stream for recovery events.
- `GET /api/v1/payments/{transaction_id}` (router.py): Fetches payment and recovery state.
- `GET /api/v1/audit/{transaction_id}` (router.py): Fetches audit logs for a transaction.
- `GET /api/v1/dashboard/metrics` (router.py): Dashboard metrics aggregated dynamically.
- `GET /api/v1/customers` (router.py): Dashboard customer view derived from transactions.
- `GET /api/v1/transactions` (router.py): Fetches recent transactions.
- `POST /api/v1/payments/{transaction_id}/refund` (router.py): Initiates refund for a successful payment.

## 3. Every Database Model/Table

**Status:** PARTIAL

- `Transaction` (transactions): Tracks payment metadata, `status` (failed/success/recovered), and refund state. **SECURITY RISK**: `status` gets overwritten during recovery, erasing original context. `amount` is a Float, not a Decimal/Integer.
- `RecoveryAttempt` (recovery_attempts): Tracks the ML probability, AI diagnosis, Policy decision, and execution status.
- `AuditLog` (audit_logs): Immutable event log. **MISSING**: Request ID correlation and tracking of refund events.
- `IdempotencyRecord` (idempotency_records): Tracks idempotent key usage. **SECURITY RISK**: Lack of concurrency control during check/insert.

## 4. Every State Machine State and Transition

**Status:** IMPLEMENTED

Defined in `state_machine.py`.
- **States:** PENDING, AUTHORIZED, EXECUTING, SUCCEEDED, FAILED, UNKNOWN, VERIFYING, STOPPED, ESCALATED, WAITING, AWAITING_CUSTOMER
- **Allowed Transitions:** Enforced strictly via `VALID_TRANSITIONS` map.
- **SECURITY RISK**: No concurrency protection (e.g. optimistic locking / row versioning) on state transitions.

## 5. Every place that can potentially execute a financial action

**Status:** SECURITY RISK

- `RecoveryOrchestrator.process_transaction` (`orchestrator.py`): Contains inline logic that directly calls `razorpay_service.execute_recovery_action()`. There is no dedicated Execution Guard.
- `initiate_refund` (`router.py`): Directly calls `razorpay_service.process_refund()` from the HTTP handler.

## 6. Every place that calls the gateway

**Status:** SECURITY RISK

- `RecoveryOrchestrator.process_transaction` (`orchestrator.py` L125) calls `razorpay_service.execute_recovery_action`.
- `initiate_refund` (`router.py` L353) calls `razorpay_service.process_refund`.

## 7. Every idempotency mechanism

**Status:** PARTIAL

- Recovery Gateway execution (`razorpay_mock.py`): Creates an `IdempotencyRecord` keying on `idem_{txn_id}_{final_action}_{retry_count}`. **SECURITY RISK**: Prone to TOCTOU race conditions under heavy concurrency.
- Refund Execution (`razorpay_mock.py` / `router.py`): Creates an `IdempotencyRecord` keying on `refund_{transaction_id}`.
- **MISSING**: Idempotency for `POST /api/v1/payments` (initial payment creation).

## 8. Every background task

**Status:** IMPLEMENTED

- `run_orchestrator_bg` (`router.py`): Runs the `RecoveryOrchestrator` synchronously in a background thread via FastAPI `BackgroundTasks`. **RELIABILITY RISK**: Errors are blindly caught, leaving the `RecoveryAttempt` stuck in PENDING indefinitely.
- `simulate_refund_webhook_bg` (`router.py`): Uses `time.sleep` in a FastAPI BackgroundTask to mock an asynchronous webhook completing a refund.

## 9. Every WebSocket/event mechanism

**Status:** PARTIAL

- `EventBus` (`event_bus.py`): In-memory pub/sub using `asyncio.Queue`.
- **RELIABILITY RISK**: Thread safety issues. Modifying `subscribers` dictionary across threads without a lock. Memory leaks possible if websockets disconnect ungracefully. Loss of all events upon server restart.

## 10. Every ML model loading path

**Status:** SECURITY RISK

- `MLService.load_model` (`ml_service.py`): Loads `recovery_model_v2.pkl` using `joblib.load()`.
- **SECURITY RISK**: No hash verification before loading the pickle file. A compromised `.pkl` file could execute arbitrary code on the server.

## 11. Every LLM invocation path

**Status:** PARTIAL

- `DiagnosisAgent.diagnose_transaction` (`diagnosis_agent.py`): Routes to `_mock_diagnose`, `_llm_diagnose` (OpenAI), or `_ollama_diagnose` (Local).
- **SECURITY RISK**: Prompt injection defense relies on instructing the LLM to ignore untrusted data, but the parsed JSON is unpacked directly without sanitization of string length/content (e.g. `diagnosis` and `reason`).

## 12. Every refund path

**Status:** PARTIAL

- `POST /api/v1/payments/{transaction_id}/refund` (`router.py`): Checks authorization (must be `success` or `recovered`), marks DB as `REFUND_REQUESTED`, calls gateway, gets `REFUND_PROCESSING`, and spawns a background task to simulate completion.
- **MISSING**: Webhook endpoint to actually receive refund confirmation from a real provider. No AuditLog records for refund events.

## 13. Authentication implementation

**Status:** SECURITY RISK

- `get_api_key` dependency (`router.py`): Checks for `X-API-Key` header against `MERCHANT_API_KEY` env var.
- **SECURITY RISK**: Hardcoded fallback (`test_secret_key_123`) in the source code. Two endpoints in `main.py` bypass this dependency entirely. No role-based access control.

## 14. CORS configuration

**Status:** SECURITY RISK

- `CORSMiddleware` (`main.py`): `allow_origins=["*"]`. This is completely open and a significant security risk for a production financial application.

## 15. Configuration/environment variables

**Status:** PARTIAL

- Configured via `.env` and `os.getenv()`. Settings include `DATABASE_URL`, `OPENAI_API_KEY`, `OLLAMA_MODEL`, `MAX_RETRIES`, `MAX_AUTO_ACTION_AMOUNT`.
- **MISSING**: Centralized `config.py` using Pydantic BaseSettings for strong typing and validation.

## 16. Existing tests and what they cover

**Status:** PARTIAL

Tests exist in `tests/`:
- **api:** `test_developer_overrides.py`, `test_refund_lifecycle.py`
- **integration:** `test_orchestrator.py`
- **security:** `test_idempotency.py`, `test_policy_independence.py`, `test_prompt_injection.py`, `test_state_machine.py`, `test_transaction_schema.py`
- **unit:** `test_policy.py`, `test_state_machine.py`, `test_transaction_schema.py`

**Coverage:** Tests validate policy logic (`test_policy.py`), basic idempotency (`test_idempotency.py`), and the state machine definition.
**MISSING**: Test coverage for concurrent execution invariants, execution guard rules, and UNKNOWN/reconciliation flows.

---

## Critical Risks

### Critical Financial Risks
1. **No Execution Guard:** Orchestrator directly calls the gateway. A bug in orchestrator logic can execute unauthorized financial actions.
2. **Loss of Original Payment State:** The `Transaction.status` is overwritten from `failed` to `recovered`, obscuring the original payment state.
3. **Floating Point Currency:** Using `Float` for monetary amounts leads to precision errors.
4. **UNKNOWN State Abandonment:** If the gateway times out, the attempt lands in UNKNOWN, but no background worker ever reconciles this, potentially leaving a customer charged without the system knowing.

### Critical Security Risks
1. **Insecure Model Loading:** `joblib.load()` on an unhashed `.pkl` file allows remote code execution if the model file is tampered with.
2. **Unauthenticated Endpoints:** `/api/diagnose` and `/api/transactions` bypass all auth, exposing internal logic.
3. **Hardcoded API Secrets:** Fallback API key exists in source code.
4. **CORS wildcard:** Allowed origins set to `*`.
5. **Prompt Injection Susceptibility:** LLM output is unpacked directly into schemas without strict string validation/sanitization.

### Reliability Risks
1. **Database Concurrency Race Conditions:** Lack of locking mechanisms (e.g. optimistic versioning) on the `RecoveryAttempt` and `IdempotencyRecord` tables.
2. **Orphaned PENDING States:** If the background orchestrator crashes, the `RecoveryAttempt` is stuck in PENDING forever.
3. **Event Bus Thread Safety:** Modifying the subscriber dictionary without a lock while pushing events across threads.

### Architectural Risks
1. **Monolithic Router:** `router.py` contains 370+ lines mixing HTTP, webhooks, dashboards, and background tasks.
2. **Missing Interfaces:** `razorpay_mock.py` and `ml_service.py` lack abstract base classes/protocols, making future migrations difficult.

## Recommended Implementation Order

To safely transition to a production-ready state, follow this sequence:

1. **P0 - Financial Safety & Invariants:**
   - Implement `ExecutionGuard` layer.
   - Fix `Transaction.status` (add `recovery_status` column).
   - Implement optimistic locking for concurrency control.
2. **P1 - Security Hardening:**
   - Remove unauthenticated endpoints and hardcoded keys.
   - Enforce model hashing and restrict CORS.
3. **P2 - Refactoring & Interfaces:**
   - Split `router.py` into distinct domains (payments, refunds, recovery, dashboard).
   - Extract `RefundService`.
4. **P3 - Reliability & Reconciliation:**
   - Implement reconciliation background worker for UNKNOWN states.
   - Add thread-safe locking to the Event Bus.
