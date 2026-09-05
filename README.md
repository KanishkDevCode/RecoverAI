# RecoverAI — Autonomous Revenue Recovery Agent

<div align="center">
  <h3>🚀 <a href="https://recover-ai-xi-ten.vercel.app/" target="_blank"><strong>Live Interactive Demo</strong></a> 🚀</h3>
  <p><strong><a href="https://recover-ai-xi-ten.vercel.app/">https://recover-ai-xi-ten.vercel.app/</a></strong></p>
</div>
<p align="center">
  <img src="assets/RecoverAi_Cover.png" alt="RecoverAI Cover" width="100%">
</p>

## ✨ Key Features

- 🤖 Hybrid AI diagnosis using Groq LLM + Machine Learning
- 🛡️ Safety-first deterministic Policy Engine
- 🔒 Execution Guard preventing unsupported gateway actions
- ⚡ Asynchronous event-driven processing with Redis + Celery
- 🪝 HMAC-SHA256 verified Razorpay webhooks
- 🔁 Idempotent webhook processing
- 📊 Real-time merchant dashboard
- 📜 Immutable transaction audit trail
- 🔄 Deterministic transaction state machine
- 🧠 Root-cause analysis for payment failures
- ☁️ Fully deployed cloud architecture
- 🧪 Interactive payment failure simulation

RecoverAI is a financial safety-first autonomous system that recovers failed payments while strictly prohibiting the LLM from executing unauthorized or unsafe financial actions.

<p align="center">
  <img src="assets/RecoverAi_Architecture.png" alt="RecoverAI Architecture" width="100%">
</p>

## Problem
Payment failures (e.g., bank timeouts, insufficient funds) result in millions of dollars in lost revenue for merchants. Traditional rule-based retry engines are too rigid, while modern autonomous AI agents are too dangerous to be given direct authority over financial transactions.

## Solution
RecoverAI uses a hybrid pipeline combining machine learning, an LLM reasoning engine, and a deterministic state machine. It evaluates failed payments, infers the root cause, and orchestrates recovery actions without ever granting the LLM direct API access to the payment gateway. 

## 🌐 Live Deployment

| Service | URL |
|---|---|
| 🖥️ Frontend Demo | https://recover-ai-xi-ten.vercel.app/ |
| ⚡ Backend API | https://recoverai-api-as5f.onrender.com |
| 📚 API Documentation | https://recoverai-api-as5f.onrender.com/docs |

> The application is deployed using Vercel and Render with PostgreSQL, Redis, FastAPI, and Celery.

---

## 🔐 Security & Safety Guarantees

RecoverAI is designed around the principle that AI reasoning and financial execution must remain separated.

### Safety guarantees

- LLM has no direct payment gateway credentials or execution authority.
- Every AI recommendation passes through deterministic policy validation.
- Execution Guard validates gateway capabilities before execution.
- Razorpay webhooks are verified using HMAC-SHA256 signatures.
- Webhook events are processed idempotently.
- Transaction state transitions are explicitly controlled.
- Every recovery decision is recorded in an audit trail.
- Unsupported financial actions are blocked safely.

## ⚠️ Gateway Safety & Real-World Constraints

RecoverAI intentionally does not blindly retry failed Razorpay payments.

During testing, the AI may determine that a transaction is eligible for a `WAIT_AND_RETRY` recovery strategy. However, the Execution Guard performs a final capability check against the payment gateway.

If Razorpay does not support safely retrying the original transaction, RecoverAI blocks the execution:

```text
AI Recommendation
       ↓
Policy Approved
       ↓
Execution Guard
       ↓
Gateway Capability Check
       ↓
❌ Unsupported Action
       ↓
Recovery Blocked Safely
```

This behavior is intentional.

Rather than allowing an AI agent to perform an unsafe or unsupported financial operation, RecoverAI fails safely and records the reason in the audit trail.

A safely blocked recovery is preferable to an unauthorized financial action.

---

## 🔄 What Happens When a Payment Fails?

RecoverAI follows a safety-first autonomous recovery pipeline:

```text
1. Payment Failure Detected
        ↓
2. Transaction Event Created
        ↓
3. Event Sent to Redis Queue
        ↓
4. Celery Worker Processes Failure
        ↓
5. AI Diagnoses Root Cause
        ↓
6. ML Model Estimates Recovery Probability
        ↓
7. LLM Recommends Recovery Action
        ↓
8. Deterministic Policy Engine Validates Action
        ↓
9. Execution Guard Checks Gateway Capability
        ↓
10. Safe Action Executed OR Recovery Blocked
        ↓
11. Complete Decision Stored in Audit Trail
```

### Example

A transaction fails because of a temporary bank timeout.

1. The AI diagnoses the failure as potentially transient.
2. The ML model estimates the probability of successful recovery.
3. The AI may recommend `WAIT_AND_RETRY`.
4. The Policy Engine checks retry limits and financial constraints.
5. The Execution Guard checks whether Razorpay actually supports that retry.
6. If unsupported, RecoverAI safely blocks the action instead of blindly retrying the payment.

This is a key design principle of RecoverAI:

**Autonomy does not mean unrestricted execution.**

---

## Master System Architecture

```mermaid
flowchart TD
    %% Client Layer
    subgraph ClientLayer["Client Layer (React / Vite)"]
        A1[Checkout UI]
        A2[Merchant Dashboard]
        A3[Payment Details & Audit]
    end

    %% API Layer
    subgraph APILayer["API Layer (FastAPI)"]
        B1[Payments Router]
        B2["Webhooks Router<br>(HMAC Verification)"]
        B3[Dashboard / Stats Router]
    end

    %% Business Logic
    subgraph BusinessLogic["Business Logic & Orchestration"]
        C1[Transaction Service]
        C2[Recovery Orchestrator]
        C3[State Machine]
    end

    %% AI & Policy
    subgraph AISystem["AI & Policy Engine (Safety Boundary)"]
        D1["AI Diagnosis Agent<br>(Groq LLM / Scikit-Learn)"]
        D2["Policy Engine<br>(Limits & Rules)"]
        D3["Execution Guard<br>(Safety Constraints)"]
    end

    %% Async Layer
    subgraph AsyncLayer["Asynchronous Processing"]
        E1[(Redis Broker)]
        E2["Celery Workers<br>(app.worker.tasks)"]
    end

    %% Data Layer
    subgraph DataLayer["Data Layer (PostgreSQL)"]
        F1[(Transactions)]
        F2[(Recovery Attempts)]
        F3[(Audit Trails)]
        F4[(Webhooks)]
    end

    %% External Services
    subgraph External["External Services"]
        X1[Razorpay API]
        X2[Groq API]
    end

    %% Flow Connections
    A1 -- "Mock Checkout POST" --> B1
    A2 -- "Fetch Stats REST" --> B3
    A3 -- "Fetch Audit REST / WS" --> B3

    X1 -- "Real HTTPS Webhook" --> B2
    
    B1 -- "Sync DB Read/Write" --> C1
    B2 -- "Persist Webhook" --> F4
    
    B1 -- "Publish Event" --> E1
    B2 -- "Publish Event" --> E1
    
    E1 -- "Consume Task" --> E2
    E2 -- "Trigger Orchestrator" --> C2
    
    C2 -- "1. Request Diagnosis" --> D1
    D1 -- "Analyze Context" --> X2
    D1 -- "Recommendation" --> C2
    
    C2 -- "2. Validate Recommendation" --> D2
    D2 -- "Decision" --> C2
    
    C2 -- "3. Execute Action" --> D3
    D3 -- "4. API Call (If Safe)" --> X1
    
    C2 -- "State Transitions" --> C3
    C3 -- "Persist Status" --> F1
    C2 -- "Record Attempt" --> F2
    C2 -- "Write Audit Log" --> F3
    
    C1 --> F1
    B3 --> F1
    B3 --> F2
    B3 --> F3

    classDef client fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0f172a;
    classDef api fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#0f172a;
    classDef logic fill:#fef08a,stroke:#ca8a04,stroke-width:2px,color:#0f172a;
    classDef ai fill:#fce7f3,stroke:#db2777,stroke-width:2px,color:#0f172a;
    classDef async fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#0f172a;
    classDef db fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#0f172a;
    classDef external fill:#f3f4f6,stroke:#4b5563,stroke-width:2px,stroke-dasharray: 5 5,color:#0f172a;

    class A1,A2,A3 client;
    class B1,B2,B3 api;
    class C1,C2,C3 logic;
    class D1,D2,D3 ai;
    class E1,E2 async;
    class F1,F2,F3,F4 db;
    class X1,X2 external;
```

---

## Detailed Component Analysis

### 1. Redis (Message Broker & Queue) ⚡
Acts as the intermediary "waiting room" between the FastAPI web server and background workers. When a webhook arrives from Razorpay, FastAPI instantly pushes the payload to Redis and returns a `202 Accepted` to Razorpay. This prevents the payment gateway from timing out, even if the AI takes several seconds to generate a response. 

### 2. Celery (Distributed Task Worker) ⚙️
Consumes tasks from the Redis queue and orchestrates the heavy lifting in the background without blocking the main web server. Celery is responsible for querying the database, calling the Groq LLM API, executing the Policy Engine, and managing the Transaction State Machine.

### 3. PostgreSQL (Permanent Datastore) 🗄️
The highly relational database acting as the permanent memory of the system. It strictly enforces foreign key constraints and schemas (managed by SQLAlchemy/Alembic) to store `Transactions`, `RecoveryAttempts`, `Webhooks`, and immutable `AuditTrails`. 

### 4. FastAPI (API Web Server) 🧠
The lightning-fast core Python API that handles real-time HTTP requests, verifies cryptographically signed Razorpay Webhooks (HMAC-SHA256), and serves analytical data back to the React frontend.

### 5. Groq API (LLM Engine) 🤖
Provides ultra-fast Llama 3 inference. It acts as the semantic reasoning engine to analyze the failure context and recommend a recovery action (e.g., `WAIT_AND_RETRY`), without ever being granted direct permission to execute that action.

### 6. React & Vite (Frontend Dashboard) 🖥️
A responsive Single Page Application (SPA) providing a merchant control center. It visualizes the current state of the database, simulates checkout failures for testing, and streams live audit logs of the AI's decision-making process.

### 7. Deterministic Policy Engine & Safety Guard 🛡️
A strict Python rules engine that intercepts the LLM's recommendation. It enforces hard constraints (e.g., max retries). Finally, the **Execution Guard** ensures the requested action is actually supported by the physical payment gateway before executing it.

---

## 🛠️ Tech Stack

<div align="center">

### Frontend & UI
![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/tailwindcss-%2338B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white)

### Backend & AI
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![scikit-learn](https://img.shields.io/badge/scikit--learn-%23F7931E.svg?style=for-the-badge&logo=scikit-learn&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge&logo=groq&logoColor=white)

### Data & Infrastructure
![Postgres](https://img.shields.io/badge/postgres-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/celery-%2337814A.svg?style=for-the-badge&logo=celery&logoColor=white)
![Razorpay](https://img.shields.io/badge/Razorpay-02042B?style=for-the-badge&logo=razorpay&logoColor=3395FF)

### Deployment
![Vercel](https://img.shields.io/badge/vercel-%23000000.svg?style=for-the-badge&logo=vercel&logoColor=white)
![Render](https://img.shields.io/badge/Render-%2346E3B7.svg?style=for-the-badge&logo=render&logoColor=white)

</div>

---

## Data Flows and execution Paths

### AI Recovery Decision Pipeline
This diagram highlights the strict safety boundaries preventing the AI from executing unauthorized financial operations.

```mermaid
flowchart TD
    In[Failed Transaction Context] --> Prep[Feature Extraction]
    Prep --> Ag[AI Diagnosis Agent]
    
    subgraph AIEngine["AI Decision Generation"]
        Ag --> Groq[Groq LLM: Causal Diagnosis]
        Ag --> ML[Scikit-Learn: Probability Score]
        Groq --> Comb[Combined AI Recommendation]
        ML --> Comb
    end
    
    Comb --> PE[Policy Engine]
    
    subgraph SafetyLayer["Deterministic Safety Layer"]
        PE -- "Is amount <= Max Auto Limit?" --> Rule1{Check Limit}
        Rule1 -- Yes --> Rule2{Check Retry Count}
        Rule1 -- No --> Reject[Action Denied -> ESCALATE]
        Rule2 -- Yes --> Approve[Action Allowed]
        Rule2 -- No --> Reject
    end
    
    Approve --> EG[Execution Guard]
    
    subgraph GatewaySafety["Gateway Limitations"]
        EG -- "Is Action supported by Gateway?" --> GWCheck{Check Capabilities}
        GWCheck -- "Yes (e.g. Send Email)" --> Exec[Execute Action]
        GWCheck -- "No (e.g. Blind Retry on Checkout)" --> SafeBlock[Recovery Blocked Safely]
    end
    
    classDef red fill:#fee2e2,stroke:#ef4444,stroke-width:2px,color:#0f172a;
    classDef green fill:#dcfce7,stroke:#22c55e,stroke-width:2px,color:#0f172a;
    class Reject,SafeBlock red;
    class Approve,Exec green;
```

### Razorpay Webhook Flow
When a real failure occurs in the external world, the webhook payload traverses the security layers before reaching the background workers.

```mermaid
sequenceDiagram
    autonumber
    participant RZP as External: Razorpay
    participant API as FastAPI (/webhooks/gateway)
    participant DB as PostgreSQL
    participant Redis as Redis Queue
    participant Celery as Celery Worker
    
    RZP->>API: POST Webhook (payment.failed)
    API->>API: Verify HMAC-SHA256 Signature
    API->>DB: Check Idempotency (Event ID exists?)
    
    alt Event already processed
        API-->>RZP: 200 OK (Ignore)
    else New Event
        API->>DB: Persist Webhook Event
        API->>Redis: Push to 'process_webhook' queue
        API-->>RZP: 202 Accepted (Fast Return)
        
        Redis-->>Celery: Consume Event
        Celery->>DB: Lookup Transaction by gateway_id
        Celery->>Celery: Trigger Recovery Orchestrator Pipeline
    end
```

### Transaction State Machine
The system rigorously controls transaction state to ensure asynchronous task failures don't leave transactions in invalid states.

```mermaid
stateDiagram-v2
    [*] --> PENDING: Payment Failure Detected
    
    PENDING --> WAITING: AI Analysis & Scheduling
    WAITING --> AUTHORIZED: Policy Engine Approved
    WAITING --> ESCALATED: Policy Engine Rejected
    
    AUTHORIZED --> EXECUTING: Gateway Guard Approved
    AUTHORIZED --> STOPPED: Gateway Guard Blocked (e.g. Blind Retry)
    
    EXECUTING --> RECOVERED: Recovery Action Succeeded
    EXECUTING --> FAILED_RECOVERY: Recovery Action Failed
    
    RECOVERED --> [*]
    FAILED_RECOVERY --> [*]
    ESCALATED --> [*]
    STOPPED --> [*]
```

---

## Deployment Architecture

The application is fully cloud-native. The frontend is hosted on Vercel, securely communicating with a Render container hosting both the FastAPI web server and the Celery background worker, backed by Render PostgreSQL and Redis.

```mermaid
flowchart LR
    User((User / Customer))
    
    subgraph Vercel["Vercel Cloud (Frontend)"]
        React[React SPA]
    end
    
    subgraph Render["Render Cloud (Backend)"]
        subgraph WebService["Web Service (Container)"]
            FastAPI[FastAPI Uvicorn]
            Celery["Celery Worker<br>concurrency=1"]
            Bash[start.sh script]
        end
        
        DB[(PostgreSQL)]
        Redis[(Redis)]
    end
    
    RZP[Razorpay Servers]
    Groq[Groq API]
    
    User -- "HTTPS" --> React
    React -- "REST (VITE_API_URL)" --> FastAPI
    RZP -- "HTTPS Webhook" --> FastAPI
    
    Bash --> FastAPI
    Bash --> Celery
    
    FastAPI -- "SQLAlchemy" --> DB
    FastAPI -- "Enqueue Tasks" --> Redis
    Celery -- "Consume Tasks" --> Redis
    Celery -- "SQLAlchemy" --> DB
    
    Celery -- "LLM Requests" --> Groq
```

---

## Database ER Diagram
The system permanently records all decisions for compliance and auditing.

```mermaid
erDiagram
    TRANSACTION ||--o{ RECOVERY_ATTEMPT : "has many"
    TRANSACTION ||--o{ AUDIT_TRAIL : "has many"
    TRANSACTION ||--o{ WEBHOOK_EVENT : "has many"
    
    TRANSACTION {
        string id PK
        string gateway_payment_id
        string customer_id
        float amount
        string currency
        string status "PENDING, FAILED, SUCCEEDED"
        string failure_code
        datetime created_at
    }
    
    RECOVERY_ATTEMPT {
        string id PK
        string transaction_id FK
        string ai_diagnosis
        string recommended_action
        string policy_decision "ALLOWED / REJECTED"
        string outcome_status "WAITING, SUCCEEDED, FAILED"
        integer latency_ms
        datetime created_at
    }
    
    AUDIT_TRAIL {
        string id PK
        string transaction_id FK
        string event_type "DETECTION, STATE_TRANSITION"
        string previous_state
        string new_state
        string message
        datetime created_at
    }
    
    WEBHOOK_EVENT {
        string id PK "Idempotency Key"
        string transaction_id FK
        string event_type "payment.failed"
        jsonb payload
        boolean processed
        datetime created_at
    }
```

---

## Project Structure
```text
recoverai/
├── backend/                             # Python Backend Workspace
│   ├── alembic/                         # Database Migration Scripts
│   ├── app/
│   │   ├── api/v1/                      # FastAPI Routers (Payments, Webhooks, Dashboard)
│   │   ├── core/                        # Core config, Database setup, State Machine
│   │   ├── models/                      # SQLAlchemy Database Models (Tables)
│   │   ├── schemas/                     # Pydantic Validation Schemas
│   │   ├── services/                    
│   │   │   ├── orchestration/           # The Recovery Orchestrator Pipeline
│   │   │   ├── agents/                  # AI Diagnosis Agent (Groq / ML Integration)
│   │   │   └── gateways/                # Razorpay and Mock Payment Adapters
│   │   ├── worker/                      # Celery App and Async Background Tasks
│   │   └── main.py                      # FastAPI Application Entrypoint
│   └── tests/                           # Pytest Test Suite
│
├── frontend/                            # React & Vite Frontend Workspace
│   ├── src/
│   │   ├── components/                  # Reusable UI (Buttons, Status Badges)
│   │   ├── context/                     # React Context (Payment Flow & Live Logs)
│   │   ├── pages/                       # App Views (Dashboard, Checkout, Details)
│   │   ├── services/                    # API client and WebSocket integration
│   │   └── index.css                    # Global Styles (Tailwind/Custom CSS)
│   ├── vercel.json                      # Vercel SPA Routing Configuration
│   └── package.json                     # NPM Dependencies
│
├── models/                              # Trained Machine Learning Assets
│   └── recovery_model_v2.pkl            # Pickled Random Forest Model
│
├── scripts/                             # Reproducibility & Build Scripts
│   └── reproduce_v2.ps1                 # Automated E2E Setup Script
│
├── assets/                              # Repository Images (Cover, Architecture)
├── system_architecture.md               # Extensive System Architecture Documentation
└── README.md                            # Main Project Documentation
```

## 🔌 Core API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/payments/...` | Create / simulate payment transaction |
| `POST` | `/api/v1/webhooks/gateway` | Receive payment gateway webhooks |
| `GET` | `/api/v1/transactions` | Retrieve transactions |
| `GET` | `/api/v1/dashboard/metrics` | Dashboard analytics |
| `GET` | `/api/v1/audit/{transaction_id}` | Retrieve transaction audit trail |
| `GET` | `/docs` | Interactive Swagger API documentation |

---

## Running Locally

### Environment Variables
Copy `.env.example` to `.env` and fill in the required keys.
```env
# AI Providers
LLM_PROVIDER=mock # options: groq, mock, auto
GROQ_API_KEY=your_groq_key_here

# Payment Providers
PAYMENT_PROVIDER=mock # options: mock, razorpay
RAZORPAY_KEY_ID=your_razorpay_key_here
RAZORPAY_KEY_SECRET=your_razorpay_secret_here
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here
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

---

## 🚀 Future Improvements

- Support additional payment gateways such as Stripe.
- Implement customer-safe retry flows using payment links.
- Add human-in-the-loop approval for high-value transactions.
- Introduce adaptive recovery policies using historical outcomes.
- Add anomaly detection for unusual failure patterns.
- Implement merchant-configurable financial risk limits.
- Support multi-currency recovery strategies.
- Add production-grade monitoring and observability dashboards.

---

## 💡 Project Philosophy

RecoverAI explores a critical question in financial AI:

> **How can we benefit from autonomous AI reasoning without giving an AI system unrestricted authority over money?**

The answer implemented in RecoverAI is **constrained autonomy**.

The AI can:

- Analyze
- Reason
- Diagnose
- Recommend

But deterministic software controls whether an action is actually allowed and technically possible.

```text
AI Intelligence
      ↓
Policy Constraints
      ↓
Execution Guard
      ↓
Safe Financial Action
```

RecoverAI demonstrates that in high-stakes systems, the goal should not be to maximize AI autonomy.
