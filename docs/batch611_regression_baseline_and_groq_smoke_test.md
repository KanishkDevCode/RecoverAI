# Batch 6.1.1 — Regression Baseline Verification & Real Groq Smoke Test

## 1. Test Isolation Root Cause
The regression test failure in `tests/api/test_metrics_dashboard_regression.py` (`psycopg2.errors.ForeignKeyViolation`) was caused by a pre-existing flaw in the test fixture's table cleanup logic. 
The test manually dropped `Transaction` and `RecoveryAttempt` rows to create a clean state. However, it failed to recognize that two other tables natively enforce a foreign key constraint to `transactions.id`:
- `AuditLog`
- `WebhookEvent`

Because previous tests in the test suite populated these tables, attempting to delete the parent `transactions` records triggered PostgreSQL's foreign key protection, blocking the deletion.

## 2. Fix Applied
**File Modified**: `backend/tests/api/test_metrics_dashboard_regression.py`

I surgically injected explicit cleanup of the dependent tables into the existing setup fixture before the parent records are removed:
```python
# Clean dependent records first
from app.models.db_models import AuditLog, WebhookEvent
db.query(AuditLog).delete()
db.query(WebhookEvent).delete()
db.query(RecoveryAttempt).delete()

# Parent records last
db.query(Transaction).delete()
db.commit()
```
I also fixed a secondary pre-existing regression test bug where the fixture passed invalid constructor kwargs (`payment_method="card"`) and a string formatted `amount="100.00"` to an `Integer` column, which were both syntactically incorrect. 

**Zero production models or architecture were modified.** Proper test isolation is achieved entirely inside the test fixtures without resorting to cascade deletes on production data.

## 3. Regression Results
| Suite | Result |
|-------|--------|
| Metrics Dashboard Regression | **PASS** (2/2) |
| Groq Unit Tests | **PASS** (6/6) |
| Full Backend Suite | **BLOCKED** |

**Exact Counts**:
- Metrics Dashboard Regression: `2 passed, 405 warnings in 3.93s`
- Groq Unit Tests: `6 passed in 0.29s`
- Full Backend Suite: *Hung infinitely during execution.*

**Investigation on Full Backend Suite**:
The test suite continuously hangs deadlocking the test runner exactly at `tests/api/test_payment_idempotency.py::test_payment_idempotency_conflict`. This is a **Test Infrastructure Issue**.
The idempotency tests heavily utilize `concurrent.futures.ThreadPoolExecutor(max_workers=5)` against the FastAPI test client. In `test_payment_idempotency.py`, there is a setup/teardown fixture that executes `Base.metadata.drop_all(bind=engine)`. Because `drop_all` requires an `ACCESS EXCLUSIVE` lock on PostgreSQL tables, it enters a deadlock whenever async background tasks (like `BackgroundTasks` in FastAPI or hanging sessions) fail to release their database connections rapidly.

## 4. Real Groq Smoke Test
**Script Created**: `backend/scripts/smoke_test_groq.py`
The smoke test script successfully instantiates the `DiagnosisAgent` configured with `LLM_PROVIDER=groq`. It strictly guarantees that the API key is NEVER committed, logged, or exposed.

- **Provider Used**: `groq`
- **Response Validation Status**: Successfully guarded against mock fallback false-positives. If the script intercepts the word "Mock" in the diagnosis output, it explicitly fails the test.
- **Key Validation**: If `$env:GROQ_API_KEY` is completely missing, it explicitly raises a `REAL_GROQ_SMOKE_TEST: FAILED` instead of silently falling back to mock logic, strictly following the instruction to not falsely report success.

## 5. Final Baseline Verdict
**BLOCKED — regression failures require investigation.**

While the Groq tests and the targeted Metric regression test failures are perfectly resolved and 100% green, the full backend test suite cannot reliably complete due to severe PostgreSQL deadlocking during `Base.metadata.drop_all()` teardown inside `test_payment_idempotency.py`. 

**Next Steps**: We must eliminate the catastrophic use of `Base.metadata.drop_all(bind=engine)` from the function-level fixture inside `test_payment_idempotency.py` to achieve a true, unblocked green baseline.
