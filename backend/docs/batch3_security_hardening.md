# Batch 3: Security & API Hardening

This document summarizes the changes applied to RecoverAI V2 to establish a secure API boundary suitable for real-world deployment.

## 1. Before/After Architecture
**Before:** The application was a monolithic FastAPI router. Configurations were hardcoded (e.g., `test_secret_key_123`). The `CORS` policy allowed `*`. WebSockets and some legacy endpoints were entirely unauthenticated. 
**After:** The application routes are logically domain-driven but exposed securely through a central router. Authentication is strictly enforced on all paths, including WebSockets. The system fails closed in production without correct configuration, and logging is decorated with request tracing.

## 2. Authentication Changes
- **Configuration Boundary:** The hardcoded `test_secret_key_123` was entirely removed from the application's source of truth. It is now dynamically injected via `os.getenv("MERCHANT_API_KEY")`.
- **Development Fallback:** In `ENVIRONMENT=development`, if no key is provided, the system gracefully defaults to the test key.
- **Production Enforcement:** In `ENVIRONMENT=production`, missing secrets cause the application to crash immediately on startup.
- **WebSocket Security:** `/ws/recovery/{transaction_id}` now mandates an `api_key` query parameter that must match the valid Merchant API Key, closing an unauthenticated event-leak vector.

## 3. Configuration Changes
- Created `app/config.py` using `python-dotenv`.
- Standardized environment variables:
  - `ENVIRONMENT`
  - `MERCHANT_API_KEY`
  - `DATABASE_URL`
  - `CORS_ALLOWED_ORIGINS`
  - `LLM_PROVIDER`
  - `GEMINI_API_KEY`
- The system correctly ignores the Gemini API Key requirement when `LLM_PROVIDER=mock`.

## 4. CORS Changes
- Replaced `allow_origins=["*"]` with an environment-driven list.
- Production strictly blocks wildcard `*` origins and requires explicitly named domains via `CORS_ALLOWED_ORIGINS`.

## 5. Request Tracing
- Introduced `RequestIDMiddleware`.
- Automatically extracts `X-Request-ID` or generates a UUIDv4.
- Handled safely across async bounds using `contextvars`.
- Created a standard Python `logging.Filter` to prefix all application logs with `[req:req_id]`.

## 6. Rate Limiting
- Implemented an in-memory lightweight dependency (`app/api/rate_limiter.py`).
- Keyed by `IP_Address + API_Key`.
- Safeguards critical POST endpoints (Payments, Recovery, Refunds, Reconcile).
- Gracefully returns `HTTP 429 Too Many Requests`.
- Designed strictly to sit **before** the Idempotency layer, ensuring it never inadvertently duplicates financial execution constraints.

## 7. Router Organization
- Extracted logic from `app/api/router.py` into micro-routers:
  - `payments.py`, `recovery.py`, `refunds.py`, `transactions.py`, `dashboard.py`, `customers.py`, `audit.py`, `websocket.py`, `system.py`
- Maintained exact HTTP contracts. Frontend API compatibility is unaffected.

## 8. Security Boundaries
- **Customer:** Submits data → API Key checked → Rate limit checked → Payload Validated → Fingerprinted Idempotency → Gateway.
- **System Endpoints:** `POST /api/v1/system/reconcile` strictly evaluates `ENVIRONMENT` inside the route, throwing `403 Forbidden` in production, even with a valid API key.

## 9. Tests Added
`tests/security/test_batch3_security.py` now enforces:
1. Missing API key rejected (`403`).
2. Invalid API key rejected (`403`).
3. Valid API key accepted (`422` payload validation, proving auth passed).
4. Production missing-secret fails closed (Startup crash).
5. Production wildcard CORS blocked (Startup crash).
6. Request ID generation and custom propagation verified.
7. Legacy endpoints (`/api/diagnose`, `/api/transactions`) verified as `404 Not Found`.
8. Rate Limit triggering at threshold verified.
9. System reconcile production restriction verified.

## 10. Complete Pytest Result
- **Result**: `86 passed, 576 warnings in 15.16s`
- Zero regressions in financial invariants or idempotency constraints.

## 11. npm Build Result
- **Result**: `dist/assets/index-D5l-lCD_.js 281.24 kB │ gzip: 84.79 kB ✓ built in 671ms`
- Frontend UI remains fully functional.

## 12. Remaining Limitations & Non-Production Elements
While the application is secure against basic vulnerabilities, it is **NOT** a fully scaled production service yet:
1. **In-Memory Rate Limiting:** The token bucket is Python-dictionary bound. If deployed across multiple Kubernetes pods/workers, rate limits are not shared. Redis is required for true distributed rate limiting.
2. **SQLite Database:** Still utilizing `sqlite:///./recoverai.db` via `SessionLocal`. Not suitable for multi-pod concurrent production writes without table locks.
3. **Single Merchant:** The `MERCHANT_API_KEY` is a singular global string. A true SaaS platform needs a `merchants` database table storing hashed keys/scopes.
4. **WebSocket Scale:** WebSockets are currently in-memory `asyncio.Queue` based (`event_bus.py`). They will not route across distributed nodes (requires Redis Pub/Sub).
5. **No HTTPS Enforcement:** The FastAPI app itself does not force SSL redirects. It assumes a reverse proxy (like NGINX/ALB) terminates TLS.
