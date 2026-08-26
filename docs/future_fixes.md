# Future Fixes & Known Issues

This document tracks known issues, edge cases, and required fixes for future iterations of RecoverAI.

## 1. Prompt Injection Scenario with Mock LLM
- **Issue:** The "Prompt Injection" UI test currently passes the policy engine and executes a successful recovery (`RETRY_PAYMENT`) when the backend is running in `Mock LLM` mode. 
- **Cause:** The `Mock LLM` uses a naive `if/else` block that only inspects the `failure_code`. It ignores the malicious instructions hidden in the `failure_reason` payload. Because the transaction amount is artificially kept small (₹900) and the ML probability is kept high (54%), the deterministic Policy Engine views the `RETRY_PAYMENT` action as safe and allows it.
- **Why this is technically safe:** Even though the LLM is tricked, the Policy Engine prevents it from executing out-of-bounds actions (like large amounts) or modifying system variables (like `MAX_RETRIES=100`). The core separation of intelligence and safety holds.
- **Resolution for Production/Demo:** 
  1. Add an OpenAI API Key or Ollama Model to the backend `.env` file to activate the real LLM. 
  2. The real LLM is instructed via its system prompt to look for malicious instructions in untrusted data fields and will correctly output `CREATE_ESCALATION` when it encounters prompt injections.
