# Batch 6.0 — External API Integration Readiness Audit

## 1. Executive Summary
This audit reviews the current integration readiness of the RecoverAI V2 application as of Batch 5.8. The architecture is fully established with robust boundaries, meaning the transition from mocked simulations to real external services is highly feasible with minimal architectural churn. The current system relies on a mock payment gateway, a mock-fallback AI diagnosis agent, and simulated webhook ingestions. It successfully abstracts provider implementations via the `GatewayInterface`.

## 2. Current Integration Architecture
The application adheres to a highly decoupled service-oriented architecture:
- **Provider Abstraction**: Gateways are abstracted via a standard Python `Protocol` (`GatewayInterface`).
- **Event-Driven Workflow**: The backend uses Celery to safely decouple internal orchestration from external API latencies. 
- **Deterministic Bounds**: Policy evaluation and execution guards sit safely *after* AI prediction/recommendation, preventing rogue LLM hallucinations from executing financial operations.

## 3. External Services Inventory
| Service Category | Verified File/Location | Current Status |
|-----------------|------------------------|----------------|
| **Payment Gateway** | `app/services/razorpay_mock.py` | MOCK |
| **Payment Webhooks** | `app/api/webhooks.py` | SIMULATED (Expects Razorpay HMAC signature) |
| **ML Probability** | `app/services/ml_service.py` | REAL (Loads `recovery_model_v2.pkl`) |
| **AI LLM Agent** | `app/agents/diagnosis_agent.py` | HYBRID (Mocks by default, OpenAI/Ollama implemented) |
| **Notification/Email** | Not found in source | NOT IMPLEMENTED |
| **Event Bus / PubSub** | `app/services/event_bus.py` | INTERNAL (Redis Pub/Sub) |
| **Observability** | `app/api/metrics.py` | INTERNAL SERVICE (Direct SQL aggregation) |

## 4. Mock vs Real Classification
- **MockGateway**: Fully mocked. Generates fake idempotency replays and success/failure JSON matching Razorpay shapes.
- **MLService**: Real. Uses `joblib` and `pandas` to evaluate transactions against a trained `.pkl` model. 
- **DiagnosisAgent**: Hybrid. Implements real calls to OpenAI (`gpt-4o-mini`) and Ollama local APIs, with templates for Anthropic and Gemini. However, if no keys are provided in `.env`, it falls back to a deterministic Mock response.

## 5. Payment Flow Trace
**Path:** React Checkout → Backend Orchestration
1. **React Checkout** (`frontend/src/services/api.js`): REAL request made to `/payments`.
2. **FastAPI Endpoint** (`app/api/payments.py`): SIMULATED logic forces success/failure based on test mode. Saves transaction to DB.
3. **Celery Worker** (`app/worker/tasks.py`): REAL durable task queues the recovery job.
4. **Recovery Orchestrator** (`app/services/orchestrator.py`): REAL internal state management and event propagation.
5. **Gateway Service** (`app/services/razorpay_mock.py`): MOCK execution of recovery charge. Needs substitution with `RazorpayGateway` or `StripeGateway`.
6. **Redis Pub/Sub** (`app/services/event_bus.py`): REAL internal event broadcasting.
7. **WebSocket** (`app/api/websockets.py`): REAL duplex connection streaming updates.
8. **React Recovery Console**: REAL UI rendering state changes in real-time.

## 6. AI Pipeline Trace
**Path:** Transaction Ingestion → AI Decision
1. **Transaction Object**: Ingested by `RecoveryOrchestrator`.
2. **Feature Extraction** (`app/services/ml_service.py`): REAL data mapping against `model_config_v2.json` features.
3. **ML Prediction** (`app/services/ml_service.py`): REAL inference via trained `joblib` model. Outputs probability `float`.
4. **AI Recommendation** (`app/agents/diagnosis_agent.py`): HYBRID. Analyzes failure + ML prob to suggest an action (`RETRY_PAYMENT`, `WAIT_AND_RETRY`, etc.).
5. **Policy Engine** (`app/policy/rules.py`): REAL deterministic engine evaluating AI suggestion against global system limits.
6. **Execution Guard** (`app/services/execution_guard.py`): REAL idempotency and concurrency lock before gateway action.

## 7. Provider Abstraction Analysis
The project uses strict Provider Abstraction. 
- **Base Interface**: `app/gateways/base.py` defines `GatewayInterface(Protocol)`.
- **Injection Point**: `app/gateways/__init__.py` exposes `get_gateway() -> GatewayInterface`.
**Conclusion**: The architecture easily supports swapping providers. Integrating Stripe or real Razorpay only requires creating a new class (e.g. `RazorpayGateway`) that implements the 5 required methods in the `GatewayInterface` Protocol, and updating `get_gateway()` to return the new instance.

## 8. API Integration Matrix

| Integration | Current Status | Current File | Real Provider Option | Difficulty | Demo Impact | Risk |
|-------------|---------------|--------------|---------------------|------------|-------------|------|
| Payment Gateway | Mocked | `razorpay_mock.py` | Razorpay (Test) / Stripe | Medium | High | High (Financial logic) |
| Webhooks | Simulated | `api/webhooks.py` | Razorpay Webhooks | Low | Medium | Low |
| AI / LLM | Hybrid/Mock | `diagnosis_agent.py` | OpenAI API (gpt-4o) | Low | High | Low (Guarded) |
| ML Model | Real | `ml_service.py` | Existing `.pkl` | N/A | High | N/A |
| Email | Not Implemented | N/A | Resend / SendGrid | Low | Medium | Low |
| Notifications | Not Implemented | N/A | Slack / Discord Hooks | Low | Low | Low |

## 9. Security Considerations
- **LLM Prompt Injection**: The `DiagnosisAgent` passes raw transaction data to the LLM. If the customer inputs a malicious `failure_reason`, the LLM might hallucinate. **Mitigation:** The system successfully confines the LLM output to a strict JSON format recommending predefined actions, which are strictly validated by the deterministic `PolicyEngine`.
- **API Keys**: Ensure `OPENAI_API_KEY` and real `RAZORPAY_KEY_SECRET` are never exposed to the frontend or committed.
- **Idempotency**: The `ExecutionGuard` currently protects against double-charges. Any new Real Gateway integration MUST properly utilize external idempotency keys provided by the API (e.g., Stripe's `Idempotency-Key` header).

## 10. Recommended Integration Priority
1. **OpenAI API**: The lowest hanging fruit with the highest visual impact. Simply requires injecting the `OPENAI_API_KEY` into `.env`.
2. **Razorpay Test Gateway**: High impact. Validates the end-to-end mission of the product.
3. **Resend / Email**: Low effort integration to notify users of `SEND_RECOVERY_MESSAGE` states.

## 11. Batch 6.x Roadmap

**Batch 6.1 — Real AI Integration (OpenAI)**
- **Goal**: Enable actual contextual diagnosis instead of mocked responses.
- **Files Affected**: `.env`
- **External API**: OpenAI
- **Risk**: Very Low
- **Demo Impact**: High

**Batch 6.2 — Payment Provider Integration (Razorpay Test Mode)**
- **Goal**: Implement the real `RazorpayGateway` conforming to `GatewayInterface`.
- **Files Affected**: `app/gateways/razorpay.py`, `app/gateways/__init__.py`
- **External API**: Razorpay Orders/Payments API
- **Risk**: Medium (Ensuring proper error translations)
- **Demo Impact**: Very High

**Batch 6.3 — Customer Communications (Email/SMS)**
- **Goal**: Implement external messaging when AI decides to `SEND_RECOVERY_MESSAGE`.
- **Files Affected**: `app/services/communication.py`, `app/services/orchestrator.py`
- **External API**: Resend API
- **Risk**: Low
- **Demo Impact**: Medium

**Batch 6.4 — End-to-End Production QA**
- **Goal**: Verify Idempotency, Concurrency, and Webhooks against real Sandbox APIs.

## 12. Risks Before Real API Integration
- Real gateways have strict rate limits and network latency that the mock gateway bypasses. The Celery workers must be configured with appropriate connection timeout and retry logic for the HTTP requests.
- The webhook processor currently assumes payload hashes and signatures are constructed perfectly; testing against real provider webhooks (e.g. via ngrok) is required to ensure HMAC verification matches.

---

### SUMMARY
**CURRENT STATE**: The system is a highly robust, event-driven orchestration engine utilizing safe boundaries between heuristic AI and deterministic financial execution.
**WHAT IS MOCKED**: Razorpay Gateway, Webhook emission, AI LLM (if keys missing).
**WHAT IS READY FOR REAL APIs**: The `GatewayInterface` abstraction is perfectly staged for a real integration. The `DiagnosisAgent` is fully coded for OpenAI and simply needs a key.
**RECOMMENDED NEXT STEP**: Batch 6.1 (Provide OpenAI Key) followed by Batch 6.2 (Implement Razorpay Test Gateway).
