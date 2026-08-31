# Batch 5.5: End-to-End Product Flow Audit

## 1. Current Architecture Map
```mermaid
graph TD
    UI[Frontend (React/Vite)] -->|HTTP POST| API_POST[FastAPI: POST /payments]
    UI <-->|WebSocket| API_WS[FastAPI: /ws/recovery]
    UI -->|HTTP GET| API_GET[FastAPI: Dashboard/Transactions]
    
    API_POST --> DB[(PostgreSQL)]
    API_POST --> Broker[Redis / Celery Broker]
    
    Broker --> CeleryWorker[Celery Worker Process]
    CeleryWorker --> Orchestrator[Recovery Orchestrator]
    
    Orchestrator --> StateMachine[State Machine]
    StateMachine --> Guard[Execution Guard]
    Guard --> MockGateway[Mock Razorpay Gateway]
    
    MockGateway -->|State Update| DB
    MockGateway -->|Result PubSub| RedisBus[Redis Event Bus]
    
    RedisBus --> API_WS
    API_WS -->|Live Events| UI
```

## 2. Frontend Map
- **Overview (`/`)**: Displays top-line metrics and recent payments. (Consumes `/dashboard/metrics`, `/transactions`)
- **Checkout (`/checkout`)**: The live/dev-mode simulation form. (Consumes `POST /payments`)
- **PaymentProcessing (`/payment-processing`)**: Live timeline view reacting to WebSocket events during recovery.
- **PaymentSuccess (`/payment-success`)**: Terminal success view.
- **PaymentFailed (`/payment-failed`)**: Terminal failure view.
- **Payments (`/payments`)**: Historical list of transactions. (Consumes `/transactions`)
- **PaymentDetails (`/payments/:transactionId`)**: Deep dive view into a single payment, showing recovery attempts and audit trails. (Consumes `/payments/{id}`, `/audit/{id}`, `POST /payments/{id}/refund`)
- **RecoveryConsole (`/recovery`)**: Dedicated AI recovery statistics view. (Consumes `/dashboard/metrics`, `/transactions`)
- **Customers (`/customers`)**: View aggregated customer values. (Consumes `/customers`)
- **Settings (`/settings`)**: Settings page (Currently not fully wired / static).

## 3. Backend API Map

| Endpoint | Method | Purpose | Frontend Consumer | Auth Required |
|----------|--------|---------|-------------------|---------------|
| `/payments` | POST | Initiate new payment (simulates failure) | Checkout | API Key |
| `/payments/{id}` | GET | Fetch detailed transaction and recovery status | PaymentDetails | API Key |
| `/payments/{id}/refund` | POST | Trigger refund | PaymentDetails | API Key |
| `/transactions` | GET | List recent transactions | Overview, Payments, Recovery | API Key |
| `/dashboard/metrics`| GET | High-level business metrics | Overview, Recovery | API Key |
| `/customers` | GET | Aggregate customer metrics | Customers | API Key |
| `/audit/{id}` | GET | List state transitions for a transaction | PaymentDetails | API Key |
| `/ws/recovery/{id}` | WS | Real-time WebSocket stream for orchestrator | PaymentProcessing | WS API Key |
| `/health/live` | GET | Basic alive check | (Infrastructure) | None |
| `/metrics` | GET | Operational observability metrics | (Infrastructure) | Obs Key |

## 4. Complete End-to-End Transaction Lifecycle (Demo Path)
1. **Merchant/Developer** opens `Checkout` (`/checkout`).
2. **Action**: Submits form using Developer "Safe Recovery" preset.
3. **API**: `POST /payments` creates a `Transaction` in Postgres (status: failed) and enqueues a Celery task.
4. **UI**: Navigates to `PaymentProcessing` and opens WebSocket `/ws/recovery/{id}`.
5. **Worker**: Celery consumes task -> `RecoveryOrchestrator` starts.
6. **Orchestration Phase**:
   - `StateMachine` emits `ML_PREDICTION` -> WS updates UI.
   - `StateMachine` emits `AI_RECOMMENDATION` -> WS updates UI.
   - `StateMachine` emits `POLICY_DECISION` -> WS updates UI.
7. **Gateway Phase**: `ExecutionGuard` permits action. `MockGateway` executes simulated recovery (e.g., `RETRY_PAYMENT`).
8. **Completion**: `MockGateway` directly updates Postgres state to `SUCCEEDED`. State machine emits `GATEWAY_RESULT` and `RECOVERY_COMPLETE`.
9. **UI**: WebSocket receives terminal success. Navigates to `PaymentSuccess` (`/payment-success`).
10. **Post-Event**: Merchant views `PaymentDetails` to see the full audit trail and recovery reasoning.

## 5. Missing Integrations & Bugs
- **[BUG]** `RecoveryConsole.jsx` expects `getPayments` to return `a.outcome` and `a.agent_diagnosis`, but the backend `transactions.py` returns `a.recovery_status_attempt`. This causes the Recovery table to render incorrectly.
- **[MISSING]** Loading and empty states are present across pages, but the `Settings` page lacks backend integration (should perhaps fetch environment configs or health).
- **[GAP]** `MockGateway` acts synchronously without actual simulated webhook delays. While acceptable for a demo, true webhook-driven workflows via `/webhooks/gateway` are not naturally exercised by the standard Checkout flow.

## 6. Demo Readiness Assessment
The project is **HIGHLY READY** for a hackathon demonstration. The core value prop (AI-driven autonomous recovery with safety guardrails) is visible and dynamic via the `PaymentProcessing` timeline. 

## 7. Identify Missing Product Features

### P0 — Demo Blockers
- Fix the data mapping bug in `RecoveryConsole.jsx` where `outcome` vs `recovery_status_attempt` mismatch breaks the display.

### P1 — Important (Hackathon Polish)
- Enhance the `PaymentProcessing` view to cleanly handle edge cases like WebSockets disconnecting before terminal state.
- Wire up a quick `Settings` page to show system health (connected to `/health/ready` or `/health/live`) to prove the infrastructure hardening work from Batch 5.4.

### P2 — Nice to Have
- Add a "Trigger Webhook" manual button in the developer panel to show off the Batch 5.3 webhook deduplication logic.

## 8. Recommended Implementation Plan for Batch 5.5
1. **Fix `RecoveryConsole.jsx`**: Update the table mapping to correctly read `recovery_status_attempt`, `agent_diagnosis`, and `policy_action` from the `/transactions` API schema.
2. **Wire `Settings.jsx`**: Create a view that fetches `/health/ready` and displays database/redis connection status to show off the production architecture.
3. **Verify Edge Cases**: Test WebSocket timeout behavior.

## 9. Final Question Answer
**Can a hackathon judge currently open the frontend and successfully experience the complete RecoverAI recovery workflow without manually interacting with backend APIs?**

**YES.** The judge can use the "Checkout" page in developer mode, trigger a failed payment, watch the real-time WebSocket recovery pipeline in the "Payment Processing" view, and see the final result in the "Overview" and "Payment Details" screens—all completely driven by the frontend UI. The only minor blocker is a rendering bug in the Recovery Console table, which can be fixed in 2 minutes.
