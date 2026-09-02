# RecoverAI — Autonomous Revenue Recovery Agent

RecoverAI is a financial safety-first autonomous system that recovers failed payments while strictly prohibiting the LLM from executing unauthorized or unsafe financial actions.

## Problem
Payment failures (e.g., bank timeouts, insufficient funds) result in millions of dollars in lost revenue for merchants. Traditional rule-based retry engines are too rigid, while modern autonomous AI agents are too dangerous to be given direct authority over financial transactions.

## Solution
RecoverAI uses a hybrid pipeline combining machine learning, an LLM reasoning engine, and a deterministic state machine. It evaluates failed payments, infers the root cause, and orchestrates recovery actions without ever granting the LLM direct API access to the payment gateway. 

## Key Features & Architecture

### Key Safety Principle
**The LLM NEVER has direct authority to move money.**
The LLM generates reasoning and a recommended action, but a deterministic Policy Engine evaluates that recommendation against financial safety invariants before any execution is permitted.

### 1. ML Component (Random Forest)
A machine learning model evaluates historical transaction features to generate a deterministic probability of successful recovery. It is optimized for Expected Value (EV) by balancing the cost of intervention against potential recovered revenue.

### 2. Gemini/LLM Component (Diagnosis Agent)
The LLM analyzes the failure context, the raw ML probability, and business constraints to reason about the failure mode. It outputs a structured diagnosis and a recommended recovery action (e.g., `RETRY_PAYMENT`, `WAIT_AND_RETRY`, `CREATE_ESCALATION`).

### 3. Deterministic Policy Engine
A strict rules engine that intercepts the LLM's recommendation. It enforces hard constraints (e.g., max retries, minimum ML probability thresholds, allowed actions per failure code) and acts as the ultimate authority over what action is taken.

### 4. Financial State Machine
A rigid state machine (`PENDING` -> `AUTHORIZED` -> `SUCCEEDED` / `FAILED` / `ESCALATED`) that ensures transactions only transition through valid states.

### 5. Configurable Payment Gateways (Factory Pattern)
The application dynamically switches between gateway abstractions using the `PAYMENT_PROVIDER` environment variable:
- **MockGateway (`PAYMENT_PROVIDER=mock`)**: A highly robust local simulator that acts like a real gateway. It enforces strict idempotency, simulates network latency, and allows for massive parallel automated testing without requiring real API keys.
- **RazorpayGateway (`PAYMENT_PROVIDER=razorpay`)**: The production-ready integration with Razorpay Test Mode. It safely maps internal semantic actions to strict real-world API endpoints (e.g., mapping `SEND_RECOVERY_MESSAGE` to generating Razorpay Payment Links, and `PROCESS_REFUND` to Razorpay's Refund API). It rigorously strips and sanitizes all API secrets from exceptions to guarantee they never leak into logs. It fully implements Razorpay webhooks (`payment.failed`, `payment.captured`, `refund.created`) using strict HMAC-SHA256 signature verification to achieve true real-time end-to-end integration.

### 6. Audit Trail
Every transition, recommendation, and policy decision is immutably logged to the database for compliance and observability.

## Evaluation Methodology & Results
The system was evaluated against 1,000 held-out synthetic transactions to compare RecoverAI against a "Safe Naive Retry" baseline.

### V2 Results
- **RecoverAI demonstrated higher simulated net value** than the safety-constrained baseline on the held-out test set.
- RecoverAI incrementally generated $106,997 in simulated net value compared to the baseline.

### Safety Results
- **Empirically verified safety invariants** across the entire test suite.
- 0 Unauthorized Executions.
- 0 Duplicate Executions.

## Project Structure
```text
recoverai/
├── backend/            # FastAPI backend, Orchestrator, Policy Engine
├── frontend/           # React live-visualization UI
├── data/v2/            # Synthetic datasets
├── models/             # Trained ML model and configuration
├── docs/               # Architecture, Security, and ML documentation
└── scripts/            # Reproducibility and evaluation scripts
```

## Running Locally

### Environment Variables
Copy `.env.example` to `.env` and fill in the required keys.
```env
# AI Providers
LLM_PROVIDER=mock # options: groq, ollama, mock, auto
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
OLLAMA_MODEL=llama3.1:8b

# Payment Providers
PAYMENT_PROVIDER=mock # options: mock, razorpay
RAZORPAY_KEY_ID=your_razorpay_key_here # Required if PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_SECRET=your_razorpay_secret_here # Required if PAYMENT_PROVIDER=razorpay
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here # Required if PAYMENT_PROVIDER=razorpay
```

### Installation & Reproducibility
We provide a PowerShell script to automatically setup the environment, install dependencies, run the test suite, and run the batch evaluation:
```powershell
.\scripts\reproduce_v2.ps1
```

### Running the Backend (Terminal 1)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Running the Celery Worker (Terminal 2)
The background worker is required for asynchronous payment recovery execution.
**Windows Users:** You must use `--pool=solo` to avoid a known multiprocessing bug in Celery, and you must explicitly listen to the custom queues.
```powershell
cd backend
.\.venv\Scripts\activate
python -m celery -A app.worker.celery_app worker --loglevel=info --pool=solo -Q celery,high_priority,reconciliation
```

### Running the Frontend (Terminal 3)
```powershell
cd frontend
npm install
npm run dev
```

### Running Tests
```powershell
cd backend
pytest tests/ -v
```

## Detailed Architecture Breakdown
RecoverAI is composed of several independent components that work together to securely process failed transactions asynchronously.

### 1. FastAPI — The Main Backend 🧠
The core API server that receives requests from the frontend or webhook sources. When a payment fails, FastAPI creates a transaction record and immediately delegates the heavy lifting to the background queue. This keeps the API lightning fast.

### 2. PostgreSQL — The Permanent Database 🗄️
Stores all critical data including `Transactions`, `RecoveryAttempts`, `AuditLogs`, and idempotency records. This acts as the permanent memory of the system, ensuring transaction state is never lost even if the application restarts.

### 3. Redis / Memurai — The Message Queue ⚡
Acts as the intermediary "waiting room" between FastAPI and the background workers. When FastAPI accepts a failed transaction, it places a job in the Redis queue. We use **Memurai** (a Windows-compatible Redis server) for local development.

### 4. Celery — The Background Worker ⚙️
Consumes tasks from the Redis queue and orchestrates the heavy recovery logic in the background without blocking the user.
The Celery worker passes the transaction through the **AI Diagnosis Agent** which utilizes a fallback chain:
1. **Groq API (Cloud):** The primary, lightning-fast LLM.
2. **Ollama (Local):** The secondary fallback if Groq is unavailable.
3. **Mock Rules (Local):** A final deterministic fallback to guarantee execution.

Once the AI generates a recommendation, it is evaluated against the deterministic **Policy Engine** before the final result is permanently saved to PostgreSQL and sent back to the frontend.

## Future Work
- Implementation of WebSocket streaming for live UI observability (architecture designed, pending implementation).
- Expansion of the Policy Engine for dynamic merchant-specific rulesets.
- Enhanced telemetry for the ML model drift detection.
