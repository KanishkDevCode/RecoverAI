# Batch 5.1 PostgreSQL Preflight Inspection

## 1. Current DB Architecture & SQLite Assumptions
The current architecture relies on SQLAlchemy with `sqlite:///./recoverai.db`.
- **Primary SQLite-specific behavior:** `connect_args={"check_same_thread": False}` is explicitly used in `app/database.py`.
- **Database Initialization:** The application likely relies on `Base.metadata.create_all(bind=engine)` rather than a robust migration framework like Alembic.
- **Concurrency & Locking:** SQLite implements database-level or table-level locking, which handles concurrent writes serially but throws `OperationalError` ("database is locked") under high contention. The current financial code uses optimistic locking (e.g., `UPDATE ... WHERE version = X` or `WHERE status = Y`), which is safe but yields errors instead of cleanly queuing row locks.

## 2. Transaction Boundaries
Financial operations are strictly separated from external gateway calls:
1. **Payments/Recovery:** 
   - Write `IdempotencyRecord` and update `RecoveryAttempt` (Commit)
   - Call Gateway (`gateway.execute_recovery_action`)
   - Update `RecoveryAttempt` based on response (Commit)
2. **Refunds:**
   - Write optimistic lock `UPDATE transactions SET refund_status = 'REFUND_PROCESSING' WHERE refund_status = 'NOT_REQUESTED'` (Commit)
   - Call Gateway (`gateway.process_refund`)
   - Update `Transaction.refund_status` to `REFUNDED` or `REFUND_FAILED` (Commit)

*Critical Safety Rule preserved:* We NEVER span a single database transaction across an external HTTP call.

## 3. Required PostgreSQL Changes
1. **Driver & URL:** Use `postgresql+psycopg2://` or `postgresql+asyncpg://` (since the app seems synchronous in DB operations, `psycopg2` or `psycopg` is appropriate). Update `config.py` to require `DATABASE_URL` for production.
2. **Migrations:** Introduce Alembic. We must generate an initial baseline migration that matches `Base.metadata`.
3. **Connection Pooling:** Configure SQLAlchemy's `QueuePool` with reasonable defaults (e.g., `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`) for production stability.
4. **Pessimistic Locking (FOR UPDATE):** For PostgreSQL, optimistic locking is perfectly valid and safe, but `SELECT ... FOR UPDATE` (using `with_for_update()`) can be introduced in reconciliation workers or idempotency checks to allow concurrent requests to block and wait rather than throwing immediate errors, reducing failure rates.

## 4. Schema Incompatibilities & Migration Risks
- **Data Types:** `Boolean` in SQLite is mapped to integer 0/1. PostgreSQL uses a true `BOOLEAN`. SQLAlchemy handles this translation, but we must ensure the Alembic generation maps it properly. `DateTime(timezone=True)` is used, which maps well to PostgreSQL's `TIMESTAMP WITH TIME ZONE`. `Float` and `Integer` are standard. 
- **Migration Strategy:** The initial Alembic revision will create tables. If migrating existing SQLite data, we would need a custom script to dump from SQLite and load into PostgreSQL. The user indicated "Create a deterministic migration/import utility if required", so we will provide a Python script `scripts/migrate_sqlite_to_postgres.py` to transfer the records preserving all IDs and timestamps.

## 5. Test Strategy
- Add a new pytest fixture or workflow that spins up a PostgreSQL container (or expects one at a specific test database URL).
- Run the full suite `pytest tests/` against it.
- Explicitly write concurrency tests (threading) to ensure PostgreSQL handles the optimistic locks and `FOR UPDATE` clauses correctly without deadlocking or duplicating execution.
