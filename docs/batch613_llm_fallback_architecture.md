# Batch 6.1.3 — Resilient Multi-Provider LLM Fallback Architecture

## Overview

As part of Batch 6.1.3, RecoverAI's AI diagnosis pipeline has been upgraded to a resilient, multi-provider architecture. The primary objective is to guarantee that the `DiagnosisAgent` always returns a valid `DiagnosisResponse`, ensuring the core orchestration loop (Celery pipelines) never crashes due to AI provider failures.

## Architecture

The system utilizes an automated fallback chain prioritized by speed, capability, and cost-efficiency.

```text
                 AI Diagnosis Request
                         │
                         ▼
                    LLM_PROVIDER
                         │
        ┌────────────────┼────────────────┐
        │                │                │
       AUTO            OLLAMA            MOCK
        │                │                │
        ▼                ▼                ▼
      GROQ             Ollama          Mock Rules
        │                │
      failure         failure
        │                │
        ▼                ▼
      Ollama         Mock Rules
        │
      failure
        │
        ▼
    Mock Rules
```

### Supported Modes (`LLM_PROVIDER` environment variable)

1. **`auto` (Default)**: Attempts Cloud AI (Groq). If it fails, falls back to Local AI (Ollama). If that fails, falls back to Deterministic Mock Rules.
2. **`groq`**: Aliased to `auto` for the fallback chain (Groq → Ollama → Mock).
3. **`ollama`**: Attempts Local AI (Ollama). Falls back to Deterministic Mock Rules.
4. **`mock`**: Skips all LLMs and immediately uses Deterministic Mock Rules.
5. **`openai`**: Attempts OpenAI. Falls back to Deterministic Mock Rules. Note: OpenAI is explicitly excluded from the `auto` chain to preserve the zero-cost deployment objective.

## Key Improvements

- **Graceful Degradation**: Instead of crashing or bubbling up `URLError`, provider failures (e.g., missing keys, network timeouts, invalid JSON responses, malformed Pydantic structures) are caught and routed to the next available provider.
- **Strict Validation**: All LLM responses are parsed and validated strictly against the `DiagnosisResponse` schema using Pydantic. If an LLM hallucinates an invalid `recommended_action`, it triggers an exception that gracefully falls back.
- **Zero-Crash Startup**: Missing API keys no longer crash the application on startup. If `GROQ_API_KEY` is missing in `auto` mode, the system seamlessly skips Groq and defaults directly to Ollama.
- **Timeout Bounds**: Both Groq and Ollama are bounded by strict `10.0` second network timeouts to prevent Celery workers from hanging indefinitely.
- **Idempotent Retries**: Provider state is stateless per-request.

## Testing & Verification

1. **Test Coverage**: 10 new scenarios introduced in `tests/unit/test_llm_fallback_chain.py` verifying all failure and success transitions.
2. **Regression Check**: Legacy Groq tests in `tests/unit/test_groq_integration.py` successfully updated to match the new public `diagnose_transaction` router behavior.
3. **Manual Verification**: A smoke test script is available at `backend/scripts/smoke_test_fallback.py` to demonstrate the three core fallback paths by dynamically modifying environment variables at runtime.

### Running the Smoke Test

```bash
$env:PYTHONPATH="C:\CODE\RevenueAi\recoverai\backend"; .\.venv\Scripts\python scripts/smoke_test_fallback.py
```
