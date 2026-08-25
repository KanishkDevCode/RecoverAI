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

### 5. Idempotent Gateway
A mock payment gateway that enforces strict idempotency using cryptographic keys, guaranteeing that duplicate execution requests (e.g., from network retries or prompt injections) are blocked.

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
GEMINI_API_KEY=your_key_here
```

### Installation & Reproducibility
We provide a PowerShell script to automatically setup the environment, install dependencies, run the test suite, and run the batch evaluation:
```powershell
.\scripts\reproduce_v2.ps1
```

### Running the Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Running the Frontend
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

## Future Work
- Implementation of WebSocket streaming for live UI observability (architecture designed, pending implementation).
- Expansion of the Policy Engine for dynamic merchant-specific rulesets.
- Enhanced telemetry for the ML model drift detection.
