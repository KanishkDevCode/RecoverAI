# Batch 6.1.6-A: Razorpay Gateway Core

## Overview
This document captures the architectural changes implemented in Batch 6.1.6-A to transition RecoverAI from a simulated MockGateway to a real Razorpay Gateway integration, while preserving the existing test suite and fallback architecture.

## Architecture Before and After

**Before:**
The application strictly used a simulated `MockGateway` internally for all testing and operations. `ExecutionGuard` relied on mock delays and internal testing variables to execute recovery operations.

**After:**
The application uses a `GatewayFactory` pattern that lazily provisions either the `MockGateway` or the `RazorpayGateway` based on the `PAYMENT_PROVIDER` environment variable. The core `ExecutionGuard` and orchestration layers remain unchanged and completely agnostic to the underlying gateway provider.

## `PAYMENT_PROVIDER` Modes

The application respects the following configuration modes:
1. `mock` (Default): Uses `MockGateway`. The application will start successfully even if all Razorpay credentials are missing. This is strictly required for preserving the baseline unit and integration tests.
2. `razorpay`: Uses `RazorpayGateway`. The application strictly enforces the presence of `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` at initialization.

## Supported Razorpay Operations

To satisfy the `GatewayInterface`, `RazorpayGateway` implements the following action mappings:

| Internal Action | Gateway Implementation |
| :--- | :--- |
| `WAIT_AND_RETRY` | Uses `client.payment.fetch` to check if late-authorization succeeded for the gateway ID. Cannot blindly capture payments. |
| `SEND_RECOVERY_MESSAGE` | Generates a secure recovery link using `client.payment_link.create`. |
| `CREATE_ESCALATION` | Internal state escalation, no gateway call. |
| `PROCESS_REFUND` | Uses the `client.payment.refund` API. |
| `VERIFY_STATE` | Uses `client.payment.fetch` to assert ground-truth payment status. |

## Limitations of Real Payment Retries

An important clarification codified in this batch is that **external gateways like Razorpay cannot "retry" arbitrary failed transactions blindly.** A user must re-authorize or provide a payment method. 

Thus, the internal `RETRY_PAYMENT` action is strictly blocked within `RazorpayGateway`. The `WAIT_AND_RETRY` action is implemented safely as a status poll (for delayed successful captures). Instead of silently faking captures, recovery workflows strictly rely on `SEND_RECOVERY_MESSAGE` (Payment Links) to execute actual re-authentication.

## Security Model
- **Lazy Credential Validation:** `PAYMENT_PROVIDER=mock` requires zero external credentials.
- **Strict Exception Sanitization:** Any exceptions emitted by the Razorpay SDK are sanitized via `_sanitize_error()`. The raw request headers, secrets, or keys are aggressively stripped (`***`) before the exception bubbles up to the application's audit logs.
- **No Test Spillage:** The full test suite runs under `PAYMENT_PROVIDER=mock`, meaning no real network traffic occurs unless explicitly requested in a smoke test.

## Unit Test Results
- **9 RazorpayGateway specific unit tests:** Testing factory injection, dependency mocking, sanitization, and interface compliance. (All Passing)
- **167 Backend Integration/Security tests:** Run safely under the mock configuration. (All Passing)

## Exact Files Changed

**New Files:**
- `app/gateways/razorpay_gateway.py`
- `tests/unit/test_razorpay_gateway.py`
- `docs/batch616a_razorpay_gateway_core.md`

**Modified Files:**
- `app/config.py` (Added `PAYMENT_PROVIDER`, `RAZORPAY_*` keys)
- `.env.example` (Added empty placeholders)
- `app/gateways/__init__.py` (Updated factory pattern)
- `requirements.txt` (Added `razorpay>=1.4.1`)
