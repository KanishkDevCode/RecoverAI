# Problems Faced & Resolutions

This document tracks all the technical challenges and hurdles we face during the development of RecoverAI, starting from Day 1. We keep this updated as the project progresses to serve as a knowledge base.

---

### 1. Python Path & Virtual Environment Issues
**Problem:** 
When trying to create the initial Python virtual environment, running `python -m venv .venv` failed with an error stating `Python was not found...` indicating the standard `python` alias wasn't mapped globally on Windows.
**Resolution:**
We fell back to using the Windows Python launcher `py`. Running `py -m venv .venv` successfully created the virtual environment.

### 2. VS Code IDE Interpreter Mismatch
**Problem:**
After setting up the virtual environment (`.venv`) and installing FastAPI, the VS Code editor (or Pyrefly) showed red squiggly error lines under `from fastapi import FastAPI` in `main.py`. This happened because the IDE was still using the global Windows Python interpreter instead of the project's virtual environment.
**Resolution:**
We verified that the `.venv` was valid and `fastapi` was successfully installed in it using shell commands. The fix for the user was to open the Command Palette (`Ctrl + Shift + P`), select **Python: Select Interpreter**, and manually point it to `C:\CODE\RevenueAi\recoverai\backend\.venv\Scripts\python.exe`.

### 3. Execution Permissions / Kaggle Training
**Problem:**
When the AI attempted to run the ML training script (`train_ml_model.py`) locally, permission was denied. The user also pointed out that for a production-level project, ML models should ideally be trained in a dedicated environment like Kaggle, rather than running random Python scripts locally.
**Resolution:**
We established a pipeline: The user will upload the `synthetic_train.csv` and the training script to a Kaggle Notebook, run the heavy ML training there, download the resulting `recovery_model.pkl`, and drop it back into the local `/models` folder for the FastAPI application to consume.

### 4. Need for Strong Architectural Boundaries
**Problem:**
A major risk identified in the Buildathon spec is allowing an LLM (Agent) to directly make financial API calls. LLMs can hallucinate or be tricked (Prompt Injection).
**Resolution:**
We strictly separated the **Diagnosis Agent** (which only outputs a recommendation) from the **Policy Engine** (deterministic Python code). The Agent can never execute an action; it can only request one. The Policy Engine has the final say.

---

### 5. LLM API Key vs. Mock Fallback
**Problem:**
To use an LLM (like OpenAI GPT-4o or Gemini) to reason about complex payment failure strings, the system requires an API key. During development and bulk synthetic testing, hitting a real LLM API 500 times can cause rate limits and cost money.
**Resolution:**
We built a dual-mode `DiagnosisAgent`. If `OPENAI_API_KEY` is not found in the `.env` file, the system automatically falls back to a deterministic "mock" mode that uses simple if/else logic on the failure codes. This allowed us to build and test the entire orchestrator pipeline without being blocked by API keys.

### 6. Production Limitations (Tech Debt to clear)
As of completing the backend architecture, these are the known limitations before deploying to a real merchant:
- **In-Memory Idempotency**: `razorpay_mock.py` stores executed keys in a Python `set()`. If the server restarts, this memory is cleared. In true production, this MUST be moved to Redis or PostgreSQL to prevent double-charging a customer.
- **Database**: We are using SQLite (`recoverai.db`). This needs to be swapped to PostgreSQL by changing the `DATABASE_URL` environment variable.
- **Authentication**: The FastAPI routes (`/api/v1/recovery/process`) are completely open. They need a JWT or API Key dependency added before public deployment.
- **Razorpay SDK**: The current payment executor is a mock. It needs to be swapped with the official `razorpay` Python SDK operating in Test Mode.
