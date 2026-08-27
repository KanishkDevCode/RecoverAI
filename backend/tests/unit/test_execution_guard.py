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
    Base.metadata.drop_all(bind=engine)

def test_execution_guard_bypassed_invalid_action():
    db = TestingSessionLocal()
    guard = get_execution_guard(db)
    
    res = guard.execute("txn_1", "att_1", "SEND_RECOVERY_MESSAGE", "idem_1", 0)
    assert res["status"] == "FAILED"
    assert "not allowed" in res["result_message"].lower()

def test_execution_guard_missing_attempt():
    db = TestingSessionLocal()
    guard = get_execution_guard(db)
    
    res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
    assert res["status"] == "FAILED"
    assert "attempt not found" in res["result_message"].lower()

def test_execution_guard_mismatched_transaction():
    db = TestingSessionLocal()
    txn = Transaction(id="txn_1", amount=100)
    att = RecoveryAttempt(id="att_1", transaction_id="txn_2", outcome_status="AUTHORIZED")
    db.add_all([txn, att])
    db.commit()
    
    guard = get_execution_guard(db)
    res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
    assert res["status"] == "FAILED"
    assert "mismatch" in res["result_message"].lower()

def test_execution_guard_not_authorized():
    db = TestingSessionLocal()
    txn = Transaction(id="txn_1", amount=100)
    att = RecoveryAttempt(id="att_1", transaction_id="txn_1", outcome_status="PENDING")
    db.add_all([txn, att])
    db.commit()
    
    guard = get_execution_guard(db)
    res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
    assert res["status"] == "FAILED"
    assert "not in authorized state" in res["result_message"].lower()

def test_execution_guard_already_terminal():
    db = TestingSessionLocal()
    txn = Transaction(id="txn_1", amount=100, recovery_status="SUCCEEDED")
    att = RecoveryAttempt(id="att_1", transaction_id="txn_1", outcome_status="AUTHORIZED")
    db.add_all([txn, att])
    db.commit()
    
    guard = get_execution_guard(db)
    res = guard.execute("txn_1", "att_1", "RETRY_PAYMENT", "idem_1", 0)
    assert res["status"] == "FAILED"
    assert "terminal" in res["result_message"].lower()
