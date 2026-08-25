# RecoverAI Architecture

RecoverAI is built on a strict, pipelined architecture designed to isolate the LLM's reasoning capabilities from financial execution authority.

## The Pipeline Flow

```text
Transaction Incoming (REST / API)
   ↓
Pydantic Validation
   ↓
ML Service (Random Forest Probability)
   ↓
Gemini Diagnosis Agent (Reasoning & Recommendation)
   ↓
Deterministic Policy Engine (Authority & Rules)
   ↓
Financial State Machine (State Transitions)
   ↓
Idempotent Gateway (Execution)
   ↓
Database (Source of Truth)
   ↓
Audit Trail (Observability)
```

## Component Roles

### 1. Pydantic Validation
Incoming transactions are immediately sanitized and strongly typed. Any malformed requests are rejected before entering the orchestration pipeline.

### 2. ML Service
A local Random Forest classifier evaluates the transaction against historical data and outputs a raw recovery probability `[0.0, 1.0]`. This is purely statistical and has no decision-making power.

### 3. Gemini Diagnosis Agent
**Role: AI Reasoning**
The LLM is prompted with the transaction context, the failure code, and the ML probability. It reasons about the failure and outputs a structured JSON response containing:
- A diagnosis of the failure
- A recommended recovery action (e.g., `RETRY_PAYMENT`, `WAIT_AND_RETRY`)

### 4. Deterministic Policy Engine
**Role: Authority**
The LLM's recommendation is intercepted by the Policy Engine. This engine evaluates the recommendation against hardcoded business rules:
- Does the action violate max retries?
- Is the ML probability above the locked threshold (e.g., 0.10) required for this action?
- Is the action allowed for this specific failure code?

If the rules fail, the Policy Engine overrides the LLM and blocks the action.

### 5. Financial State Machine
**Role: State Integrity**
The transaction attempt is governed by a strict state machine (`PENDING` -> `AUTHORIZED` -> `SUCCEEDED`/`FAILED`/`ESCALATED`). Invalid transitions throw explicit errors and are blocked.

### 6. Idempotent Gateway
**Role: Execution**
The mock Razorpay gateway requires an idempotency key generated from the transaction ID, action, and retry count. It prevents duplicate executions for the same action.

### 7. Database
**Role: Source of Truth**
SQLite (or PostgreSQL in production) is the absolute source of truth. If the system crashes, recovery state is rebuilt from the database.

### 8. Live UI / WebSocket
**Role: Visualization Layer**
*(Note: Implementation pending)*
A React frontend subscribes to a WebSocket event bus to visualize the orchestrator pipeline live. The WebSocket is strictly a read-only stream; the database remains the source of truth.
