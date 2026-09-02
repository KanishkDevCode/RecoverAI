# Batch 6.1.6-D — End-to-End Razorpay Test Mode Readiness Audit

This document summarizes the read-only architecture and infrastructure readiness audit performed before conducting live Razorpay Test Mode testing.

## 1. Razorpay Configuration
- `PAYMENT_PROVIDER=razorpay` correctly initializes `RazorpayGateway` in `app/gateways/__init__.py`.
- `PAYMENT_PROVIDER=mock` elegantly falls back to `MockGateway` and bypasses Razorpay validation.
- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are securely validated inside `Settings.validate()` ONLY if `PAYMENT_PROVIDER == "razorpay"`.
- No secrets are logged. `RazorpayGateway._sanitize_error` automatically strips credentials from exception traces.
- Test Mode credentials can be safely used without modifying any source code.

## 2. Webhook Endpoint Specification
- **Exact Webhook URL Path**: `http://localhost:8000/api/v1/webhooks/gateway`
- **Required HTTP Method**: `POST`
- **Required Razorpay Headers**: `X-Razorpay-Signature`, `X-Razorpay-Event-Id`
- **Signature Verification**: Performed securely using `hmac-sha256` of the raw request body payload compared against `WEBHOOK_SECRET` via `RazorpayGateway.verify_webhook_signature()`.
- **Expected Webhook Secret ENV**: `WEBHOOK_SECRET` (⚠️ **NOTE**: The environment variable used to verify the webhook signature is `WEBHOOK_SECRET`, not `RAZORPAY_WEBHOOK_SECRET`).
- **Ngrok Compatibility**: Completely compatible. The public URL format is: `https://<ngrok-id>.ngrok-free.app/api/v1/webhooks/gateway`

## 3. Infrastructure Dependencies
To execute a genuine E2E test, the following infrastructure must be running:

1. **PostgreSQL**: REQUIRED. Stores the real transaction and webhook idempotency states.
   - *Startup*: `docker run --name recoverai-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=recoverai -p 5432:5432 -d postgres` (or Windows service equivalent)
2. **Redis / Memurai**: REQUIRED. Acts as the broker for Celery to process asynchronous recovery workflows.
   - *Startup*: Launch `memurai.exe`
3. **Celery Worker**: REQUIRED. Executes `process_webhook` and `process_orchestrator`.
   - *Startup*: `.\.venv\Scripts\celery -A app.worker.celery_app worker -l INFO -P eventlet`
4. **FastAPI Backend**: REQUIRED. Receives API requests and webhooks.
   - *Startup*: `.\.venv\Scripts\uvicorn app.main:app --reload --port 8000`
5. **Groq API**: REQUIRED. The `LLM_PROVIDER=auto` configuration requires Groq for the DiagnosisAgent to analyze the transaction failure.
6. **ngrok Tunnel**: REQUIRED. Maps the local FastAPI backend to a public URL that Razorpay can send webhook events to.
   - *Startup*: `ngrok http 8000`
7. *(Celery Beat & React Frontend are NOT strictly required for the core backend testing flow).*

## 4. Real Razorpay Payment Flow Compatibility
The flow trace verifies that end-to-end integration is structurally sound:
1. Generate Razorpay Test Payment (Frontend/Postman) → yields `pay_xxx`
2. `POST /api/v1/payments` with `gateway_payment_id="pay_xxx"` → Creates internal `Transaction`
3. Razorpay triggers webhook (`payment.failed` or `payment.captured`) → Hits Ngrok → Hits FastAPI
4. FastAPI validates signature → saves `WebhookEvent` → triggers Celery
5. Celery queries `Transaction` where `gateway_payment_id="pay_xxx"`
6. `process_webhook` invokes `RecoveryOrchestrator` → uses LLM → invokes `RazorpayGateway`

## 5. Recovery Action Compatibility
The `RazorpayGateway` supports the following actions in Test Mode:
- `WAIT_AND_RETRY`: **GENUINE**. Uses `client.payment.fetch(txn.gateway_payment_id)` to check for late auth capture.
- `SEND_RECOVERY_MESSAGE`: **GENUINE**. Creates a real Razorpay Payment Link (`client.payment_link.create`) for the customer to retry.
- `PROCESS_REFUND`: **GENUINE**. Uses `client.payment.refund` to process refunds directly.
- `VERIFY_STATE`: **GENUINE**. Polls Razorpay for current status.
- `CREATE_ESCALATION`: **SIMULATED**. Only internal status changes.
- `RETRY_PAYMENT`: **BLOCKED**. Explicitly throws an unsupported error because you cannot blindly retry a customer's failed card transaction without their consent.

## 6. Database Verification
- `gateway_payment_id` is successfully parsed from `PaymentCreateRequest` during `POST /api/v1/payments`.
- `gateway_refund_id` is effectively extracted during `refund.created` webhooks and saved via SQLAlchemy into the `Transaction` table.
- **Verification Procedure**:
  Run in powershell: `.\.venv\Scripts\python -c "from app.database import engine; from sqlalchemy import text; conn = engine.connect(); print(conn.execute(text('SELECT id, gateway_payment_id, recovery_status FROM transactions')).fetchall()); conn.close()"`

## 7. Architecture Gaps Discovered
- **Minor Config Naming mismatch**: `app/config.py` defines `RAZORPAY_WEBHOOK_SECRET` but `app/api/webhooks.py` relies solely on `settings.WEBHOOK_SECRET`. For testing, you must set `WEBHOOK_SECRET=your_razorpay_secret`.

## 8. E2E Readiness Checklist

- [ ] Razorpay Test Mode account
- [ ] Razorpay API credentials configured (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`)
- [ ] `PAYMENT_PROVIDER=razorpay` in `.env`
- [ ] PostgreSQL running
- [ ] Redis/Memurai running
- [ ] Celery Worker running (`-P eventlet`)
- [ ] FastAPI running
- [ ] ngrok tunnel running
- [ ] Webhook configured in Razorpay Dashboard (`payment.failed`, `payment.captured`, `refund.created`, `refund.processed`)
- [ ] Webhook secret configured (`WEBHOOK_SECRET` in `.env`)
- [ ] Test payment generated and simulated as failed
- [ ] Transaction created with `gateway_payment_id`
- [ ] Webhook received via ngrok
- [ ] Celery processed event
- [ ] Recovery pipeline triggered (Payment Link Generated)
- [ ] Provider telemetry persisted
