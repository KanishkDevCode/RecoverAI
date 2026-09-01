import pytest
from app.services.execution_guard import get_execution_guard
from app.models.db_models import Transaction, RecoveryAttempt
from app.database import engine, Base
from sqlalchemy.orm import sessionmaker

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # Safe cleanup using reversed sorted_tables to respect FKs
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

def test_execution_guard_bypassed_invalid_action():
    db = TestingSessionLocal()
    try:
        guard = get_execution_guard(db)
    
        res = guard.execute("txn_1", "att_1", "SEND_RECOVERY_MESSAGE", "idem_1", 0)
        assert res["status"] == "FAILED"
        assert "not allowed" in res["result_message"].lower()
    finally:
        db.close()



def test_execution_guard_missing_attempt():
    db = TestingSessionLocal()
    try:
        guard = get_execution_guard(db)
    
        res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
        assert res["status"] == "FAILED"
        assert "attempt not found" in res["result_message"].lower()
    finally:
        db.close()



def test_execution_guard_mismatched_transaction():
    db = TestingSessionLocal()
    try:
        txn1 = Transaction(id="txn_1", amount=100)
        txn2 = Transaction(id="txn_2", amount=100)
        db.add(txn1)
        db.add(txn2)
        db.flush()
        
        att = RecoveryAttempt(id="att_1", transaction_id="txn_2", outcome_status="AUTHORIZED")
        db.add(att)
        db.commit()
    
        guard = get_execution_guard(db)
        res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
        assert res["status"] == "FAILED"
        assert "mismatch" in res["result_message"].lower()
    finally:
        db.close()



def test_execution_guard_not_authorized():
    db = TestingSessionLocal()
    try:
        txn = Transaction(id="txn_1", amount=100)
        db.add(txn)
        db.flush()
        
        att = RecoveryAttempt(id="att_1", transaction_id="txn_1", outcome_status="PENDING")
        db.add(att)
        db.commit()
    
        guard = get_execution_guard(db)
        res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
        assert res["status"] == "FAILED"
        assert "not in authorized state" in res["result_message"].lower()
    finally:
        db.close()



def test_execution_guard_already_terminal():
    db = TestingSessionLocal()
    try:
        txn = Transaction(id="txn_1", amount=100, recovery_status="SUCCEEDED")
        db.add(txn)
        db.flush()
        
        att = RecoveryAttempt(id="att_1", transaction_id="txn_1", outcome_status="AUTHORIZED")
        db.add(att)
        db.commit()
    
        guard = get_execution_guard(db)
        res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
        assert res["status"] == "FAILED"
        assert "terminal" in res["result_message"].lower()

    finally:
        db.close()
