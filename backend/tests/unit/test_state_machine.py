import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from app.database import Base
from app.models.db_models import RecoveryAttempt, AuditLog
from app.services.state_machine import transition_recovery_attempt
from app.services.razorpay_mock import razorpay_service

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

def create_pending_attempt(db):
    attempt_id = f"att_test_{uuid.uuid4().hex[:8]}"
    attempt = RecoveryAttempt(id=attempt_id, transaction_id="txn_test", outcome_status="PENDING")
    db.add(attempt)
    db.commit()
    return attempt_id

def test_happy_path_transitions(db_session):
    attempt_id = create_pending_attempt(db_session)
    
    transition_recovery_attempt(db_session, attempt_id, "AUTHORIZED", "Policy approved")
    transition_recovery_attempt(db_session, attempt_id, "EXECUTING", "Starting call")
    transition_recovery_attempt(db_session, attempt_id, "SUCCEEDED", "Success")
    
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    assert attempt.outcome_status == "SUCCEEDED"

def test_explicit_failure_transitions(db_session):
    attempt_id = create_pending_attempt(db_session)
    
    transition_recovery_attempt(db_session, attempt_id, "AUTHORIZED", "Policy approved")
    transition_recovery_attempt(db_session, attempt_id, "EXECUTING", "Starting call")
    transition_recovery_attempt(db_session, attempt_id, "FAILED", "Failed")
    
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    assert attempt.outcome_status == "FAILED"

def test_timeout_transitions(db_session):
    attempt_id = create_pending_attempt(db_session)
    
    transition_recovery_attempt(db_session, attempt_id, "AUTHORIZED", "Policy approved")
    transition_recovery_attempt(db_session, attempt_id, "EXECUTING", "Starting call")
    transition_recovery_attempt(db_session, attempt_id, "UNKNOWN", "Timeout")
    
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    assert attempt.outcome_status == "UNKNOWN"

def test_verification_success(db_session):
    attempt_id = create_pending_attempt(db_session)
    transition_recovery_attempt(db_session, attempt_id, "AUTHORIZED", "")
    transition_recovery_attempt(db_session, attempt_id, "EXECUTING", "")
    transition_recovery_attempt(db_session, attempt_id, "UNKNOWN", "")
    
    # Verification flow
    res = razorpay_service.verify_transaction_state(db_session, "txn_verify_success", attempt_id)
    assert res == "SUCCEEDED"
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    assert attempt.outcome_status == "SUCCEEDED"

def test_verification_failure(db_session):
    attempt_id = create_pending_attempt(db_session)
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    attempt.outcome_status = "UNKNOWN"
    db_session.commit()
    
    res = razorpay_service.verify_transaction_state(db_session, "txn_verify_fail", attempt_id)
    assert res == "FAILED"
    db_session.refresh(attempt)
    assert attempt.outcome_status == "FAILED"

def test_verification_unavailable(db_session):
    attempt_id = create_pending_attempt(db_session)
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    attempt.outcome_status = "UNKNOWN"
    db_session.commit()
    
    res = razorpay_service.verify_transaction_state(db_session, "txn_verify_unavailable", attempt_id)
    assert res == "UNKNOWN"
    db_session.refresh(attempt)
    assert attempt.outcome_status == "UNKNOWN"

def test_max_reconciliation_attempts(db_session):
    attempt_id = create_pending_attempt(db_session)
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    attempt.outcome_status = "UNKNOWN"
    db_session.commit()
    
    # Simulate hitting max attempts
    res = razorpay_service.verify_transaction_state(db_session, "txn_max_attempts", attempt_id)
    assert res == "ESCALATED"
    db_session.refresh(attempt)
    assert attempt.outcome_status == "ESCALATED"

def test_no_blind_retry(db_session):
    attempt_id = create_pending_attempt(db_session)
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    attempt.outcome_status = "UNKNOWN"
    db_session.commit()
    
    with pytest.raises(ValueError, match="Invalid state transition from UNKNOWN to EXECUTING"):
        transition_recovery_attempt(db_session, attempt_id, "EXECUTING", "Blind retry")

def test_invalid_transitions(db_session):
    attempt_id = create_pending_attempt(db_session)
    attempt = db_session.query(RecoveryAttempt).get(attempt_id)
    attempt.outcome_status = "SUCCEEDED"
    db_session.commit()
    
    with pytest.raises(ValueError):
        transition_recovery_attempt(db_session, attempt_id, "EXECUTING", "Bad transition")
        
    with pytest.raises(ValueError):
        transition_recovery_attempt(db_session, attempt_id, "FAILED", "Bad transition")
        
    # Verify state didn't change (Test 15)
    db_session.refresh(attempt)
    assert attempt.outcome_status == "SUCCEEDED"

def test_audit_event_generated(db_session):
    attempt_id = create_pending_attempt(db_session)
    
    initial_audits = db_session.query(AuditLog).count()
    transition_recovery_attempt(db_session, attempt_id, "AUTHORIZED", "Test audit")
    
    final_audits = db_session.query(AuditLog).count()
    assert final_audits == initial_audits + 1
    
    latest_audit = db_session.query(AuditLog).order_by(AuditLog.id.desc()).first()
    assert latest_audit.event_type == "STATE_TRANSITION"
    assert latest_audit.previous_state == "PENDING"
    assert latest_audit.new_state == "AUTHORIZED"
    assert latest_audit.reasoning == "Test audit"
