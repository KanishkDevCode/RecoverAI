# Future Production Limitations / Tech Debt

This document tracks the remaining architectural constraints that must be resolved before deploying **RecoverAI** to a live, high-traffic merchant environment.

### 1. Scaling the LLM (Asynchronous Queue)
- **Current State:** The AI Agent is called synchronously. The FastAPI endpoint waits for the LLM (Ollama or OpenAI) to generate a response before returning a 200 OK to the client.
- **Risk:** LLMs are slow. If 1,000 payment failures are ingested simultaneously, the HTTP connections will block, the server will freeze, and requests will time out.
- **Resolution:** Implement **Celery** with **RabbitMQ** or **Redis**. The FastAPI endpoint should instantly enqueue the transaction and return a `202 Accepted` status. Background Celery workers will consume the queue and handle the heavy LLM inference without blocking the main web server.

### 2. Database Concurrency (PostgreSQL)
- **Current State:** The system uses `SQLite` (`recoverai.db`).
- **Risk:** SQLite locks the entire database file on write operations. Under high concurrent load, this will result in "Database Locked" exceptions and dropped audit logs.
- **Resolution:** Spin up a **PostgreSQL** database. Because we strictly used SQLAlchemy ORM, no SQL queries need to be rewritten. Simply change the `DATABASE_URL` in the `.env` file from `sqlite:///...` to `postgresql://user:password@localhost/dbname`.

### 3. Real Payment Gateway & Webhooks
- **Current State:** The system uses `razorpay_mock.py`, which simulates network latency (`time.sleep(0.1)`) and assumes instantaneous success.
- **Risk:** It doesn't actually recover real money.
- **Resolution:** 
  1. Install the official `razorpay` Python SDK.
  2. Implement a true async webhook listener (`/api/v1/webhooks/razorpay`) to receive the actual settled state from Razorpay instead of assuming synchronous success.
  3. Validate the `X-Razorpay-Signature` HMAC hash on the webhook to ensure malicious actors aren't sending fake payment successes.
