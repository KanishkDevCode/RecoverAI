# RecoverAI — Autonomous Revenue Recovery Agent

<div align="center">
  <h3>🚀 <a href="https://recover-ai-xi-ten.vercel.app/" target="_blank"><strong>Live Interactive Demo</strong></a> 🚀</h3>
  <p><strong><a href="https://recover-ai-xi-ten.vercel.app/">https://recover-ai-xi-ten.vercel.app/</a></strong></p>
</div>
<p align="center">
  <img src="assets/RecoverAi_Cover.png" alt="RecoverAI Cover" width="100%">
</p>

RecoverAI is a financial safety-first autonomous system that recovers failed payments while strictly prohibiting the LLM from executing unauthorized or unsafe financial actions.

<p align="center">
  <img src="assets/RecoverAi_Architecture.png" alt="RecoverAI Architecture" width="100%">
</p>

## Problem
Payment failures (e.g., bank timeouts, insufficient funds) result in millions of dollars in lost revenue for merchants. Traditional rule-based retry engines are too rigid, while modern autonomous AI agents are too dangerous to be given direct authority over financial transactions.

## Solution
RecoverAI uses a hybrid pipeline combining machine learning, an LLM reasoning engine, and a deterministic state machine. It evaluates failed payments, infers the root cause, and orchestrates recovery actions without ever granting the LLM direct API access to the payment gateway. 

---

## Key Safety Principle
**The LLM NEVER has direct authority to move money.**
The LLM generates reasoning and a recommended action, but a deterministic Policy Engine evaluates that recommendation against financial safety invariants before any execution is permitted.

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

### 1. ML Component (Random Forest)
A machine learning model evaluates historical transaction features to generate a deterministic probability of successful recovery. It is optimized for Expected Value (EV) by balancing the cost of intervention against potential recovered revenue.

### 2. LLM Component (Diagnosis Agent)
The LLM analyzes the failure context, the raw ML probability, and business constraints to reason about the failure mode. It outputs a structured diagnosis and a recommended recovery action (e.g., `RETRY_PAYMENT`, `WAIT_AND_RETRY`, `CREATE_ESCALATION`).

### 3. Deterministic Policy Engine & Safety Guard
A strict rules engine that intercepts the LLM's recommendation. It enforces hard constraints (e.g., max retries, minimum ML probability thresholds, allowed actions per failure code). Finally, the **Execution Guard** ensures the requested action is actually supported by the physical payment gateway before executing it.

### 4. Configurable Payment Gateways (Factory Pattern)
The application dynamically switches between gateway abstractions using the `PAYMENT_PROVIDER` environment variable:
- **MockGateway (`PAYMENT_PROVIDER=mock`)**: A highly robust local simulator that acts like a real gateway. It enforces strict idempotency, simulates network latency, and allows for massive parallel automated testing without requiring real API keys.
- **RazorpayGateway (`PAYMENT_PROVIDER=razorpay`)**: The production-ready integration with Razorpay Test Mode. It safely maps internal semantic actions to strict real-world API endpoints. It fully implements Razorpay webhooks (`payment.failed`, `payment.captured`) using strict HMAC-SHA256 signature verification to achieve true real-time end-to-end integration.

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
├── backend/            # FastAPI backend, Orchestrator, Policy Engine
├── frontend/           # React live-visualization UI
├── models/             # Trained ML model and configuration
├── scripts/            # Reproducibility and evaluation scripts
└── README.md           # Documentation
```

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
