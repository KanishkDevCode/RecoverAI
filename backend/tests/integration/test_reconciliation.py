import pytest
import time
import uuid
from datetime import datetime, timedelta
from app.database import Base, engine, SessionLocal
from app.models.db_models import Transaction, RecoveryAttempt, IdempotencyRecord
from app.services.reconciliation import reconcile_unknown_attempts, reconcile_orphaned_attempts
from app.services.state_machine import transition_recovery_attempt

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # Safe cleanup using reversed sorted_tables to respect FKs
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

def create_mock_transaction(db, txn_id):
    txn = Transaction(
        id=txn_id,
        customer_id="cust_recon",
        amount=5000,
        currency="INR",
        status="failed",
        recovery_status="NOT_STARTED"
    )
    db.add(txn)
    db.commit()

def test_reconcile_unknown_to_success():
    db = SessionLocal()
    txn_id = f"txn_verify_success_{uuid.uuid4().hex[:6]}"
    create_mock_transaction(db, txn_id)
    
    attempt_id = f"att_{uuid.uuid4().hex[:12]}"
    attempt = RecoveryAttempt(
        id=attempt_id,
        transaction_id=txn_id,
        outcome_status="UNKNOWN"
    )
    db.add(attempt)
    
    idem = IdempotencyRecord(
        key=f"idem_{txn_id}_RETRY_PAYMENT_0",
        attempt_id=attempt_id,
        status="UNKNOWN"
    )
    db.add(idem)
    db.commit()
    
    # Run reconciliation
    reconcile_unknown_attempts(db)
    
    # Check outcomes
    db.refresh(attempt)
    assert attempt.outcome_status == "SUCCEEDED"
    
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.recovery_status == "SUCCEEDED"
    db.close()

def test_reconcile_orphaned_attempts():
    db = SessionLocal()
    txn_id = f"txn_orphan_{uuid.uuid4().hex[:6]}"
    create_mock_transaction(db, txn_id)
    
    attempt_id = f"att_{uuid.uuid4().hex[:12]}"
    attempt = RecoveryAttempt(
        id=attempt_id,
        transaction_id=txn_id,
        outcome_status="PENDING",
        created_at=datetime.utcnow() - timedelta(minutes=10) # Older than 5 min timeout
    )
    db.add(attempt)
    db.commit()
    
    # Run orphan cleanup
    reconcile_orphaned_attempts(db)
    
    db.refresh(attempt)
    assert attempt.outcome_status == "UNKNOWN"
    
    # Run unknown reconciliation (since it's not verify_success/verify_fail, it should become ESCALATED or remain UNKNOWN based on razorpay_mock logic)
    reconcile_unknown_attempts(db)
    
    db.refresh(attempt)
    assert attempt.outcome_status in ["ESCALATED", "UNKNOWN"]
    db.close()

def test_reconciliation_is_idempotent():
    db = SessionLocal()
    txn_id = f"txn_verify_fail_{uuid.uuid4().hex[:6]}"
    create_mock_transaction(db, txn_id)
    
    attempt_id = f"att_{uuid.uuid4().hex[:12]}"
    attempt = RecoveryAttempt(
        id=attempt_id,
        transaction_id=txn_id,
        outcome_status="UNKNOWN"
    )
    db.add(attempt)
    db.commit()
    
    # Run reconciliation multiple times
    reconcile_unknown_attempts(db)
    reconcile_unknown_attempts(db)
    reconcile_unknown_attempts(db)
    
    db.refresh(attempt)
    assert attempt.outcome_status == "FAILED" # verify_fail triggers FAILED
    
    # Ensuring no duplicate external calls created side effects
    db.close()
