import pytest
import uuid
import time
from datetime import datetime, timedelta
from app.database import Base, engine, SessionLocal
from app.models.db_models import Transaction, RecoveryAttempt, IdempotencyRecord
from app.services.execution_guard import get_execution_guard
from app.services.reconciliation import reconcile_unknown_attempts, reconcile_orphaned_attempts, reconcile_stuck_refunds
from app.services.state_machine import transition_recovery_attempt
from app.services.refund_service import get_refund_service
from app.services.orchestrator import RecoveryOrchestrator
from app.schemas.transaction import TransactionIncoming
from app.gateways import get_gateway
from app.gateways.base import GatewayInterface
from app.services.razorpay_mock import MockGateway
from unittest.mock import patch, MagicMock

@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # Safe cleanup using reversed sorted_tables to respect FKs
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

@pytest.fixture
def db_session(setup_db):
    db = SessionLocal()
    yield db
    db.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

def setup_transaction(db, txn_id):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        txn = Transaction(
            id=txn_id,
            customer_id="cust_123",
            amount=1000,
            currency="USD",
            status="failed",
            recovery_status="NOT_STARTED",
            refund_status="NOT_REQUESTED"
        )
        db.add(txn)
        db.commit()
    return txn

# Test 1 — ESCALATED retry protection
def test_escalated_retry_protection(db_session):
    txn_id = f"txn_esc_retry_{uuid.uuid4().hex[:8]}"
    setup_transaction(db_session, txn_id)
    
    attempt1_id = f"att_1_{uuid.uuid4().hex[:8]}"
    att1 = RecoveryAttempt(
        id=attempt1_id,
        transaction_id=txn_id,
        outcome_status="ESCALATED"
    )
    db_session.add(att1)
    db_session.commit()
    
    # Try Attempt 2 via ExecutionGuard
    attempt2_id = f"att_2_{uuid.uuid4().hex[:8]}"
    att2 = RecoveryAttempt(
        id=attempt2_id,
        transaction_id=txn_id,
        outcome_status="AUTHORIZED"
    )
    db_session.add(att2)
    db_session.commit()
    
    guard = get_execution_guard(db_session)
    result = guard.execute(txn_id, attempt2_id, "RETRY_PAYMENT", f"idem_{txn_id}_RETRY_PAYMENT_1", 1)
    
    assert result["status"] == "FAILED"
    assert "blocked: Conflicting attempt" in result["result_message"]
    assert "ESCALATED" in result["result_message"]

# Test 2 — ESCALATED cannot bypass ExecutionGuard
def test_escalated_direct_guard_bypass(db_session):
    txn_id = f"txn_esc_bypass_{uuid.uuid4().hex[:8]}"
    setup_transaction(db_session, txn_id)
    
    attempt1_id = f"att_1_{uuid.uuid4().hex[:8]}"
    att1 = RecoveryAttempt(
        id=attempt1_id,
        transaction_id=txn_id,
        outcome_status="ESCALATED"
    )
    db_session.add(att1)
    db_session.commit()
    
    attempt2_id = f"att_2_{uuid.uuid4().hex[:8]}"
    att2 = RecoveryAttempt(
        id=attempt2_id,
        transaction_id=txn_id,
        outcome_status="AUTHORIZED"
    )
    db_session.add(att2)
    db_session.commit()
    
    guard = get_execution_guard(db_session)
    result = guard.execute(txn_id, attempt2_id, "RETRY_PAYMENT", "some_key", 0)
    assert result["status"] == "FAILED"
    assert "Conflicting attempt" in result["result_message"]

# Test 3 — Multiple ambiguous attempts
def test_multiple_ambiguous_attempts(db_session):
    txn_id = f"txn_mult_amb_{uuid.uuid4().hex[:8]}"
    setup_transaction(db_session, txn_id)
    
    attempt1_id = f"att_1_{uuid.uuid4().hex[:8]}"
    att1 = RecoveryAttempt(
        id=attempt1_id,
        transaction_id=txn_id,
        outcome_status="UNKNOWN"
    )
    db_session.add(att1)
    
    attempt2_id = f"att_2_{uuid.uuid4().hex[:8]}"
    att2 = RecoveryAttempt(
        id=attempt2_id,
        transaction_id=txn_id,
        outcome_status="ESCALATED"
    )
    db_session.add(att2)
    db_session.commit()
    
    attempt3_id = f"att_3_{uuid.uuid4().hex[:8]}"
    att3 = RecoveryAttempt(
        id=attempt3_id,
        transaction_id=txn_id,
        outcome_status="AUTHORIZED"
    )
    db_session.add(att3)
    db_session.commit()
    
    guard = get_execution_guard(db_session)
    result = guard.execute(txn_id, attempt3_id, "RETRY_PAYMENT", "key", 0)
    assert result["status"] == "FAILED"
    assert "blocked: Conflicting attempt" in result["result_message"]

# Test 4 — REFUND_REQUESTED orphan
def test_refund_requested_orphan(db_session):
    txn_id = f"txn_ref_req_orphan_{uuid.uuid4().hex[:8]}"
    txn = setup_transaction(db_session, txn_id)
    txn.status = "success"
    txn.refund_status = "REFUND_REQUESTED"
    # Backdate to trigger reconciliation
    txn.updated_at = datetime.utcnow() - timedelta(minutes=10)
    db_session.commit()
    
    with patch.object(MockGateway, 'verify_refund', return_value="REFUND_UNKNOWN") as mock_verify:
        with patch.object(MockGateway, 'process_refund') as mock_process:
            reconcile_stuck_refunds(db_session)
            mock_verify.assert_called_once_with(db_session, txn_id)
            mock_process.assert_not_called()
            
            db_session.expire_all()
            txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
            assert txn.refund_status == "REFUND_UNKNOWN"

# Test 5 — REFUND_REQUESTED gateway success
def test_refund_requested_success(db_session):
    txn_id = f"verify_refund_success_{uuid.uuid4().hex[:8]}"
    txn = setup_transaction(db_session, txn_id)
    txn.status = "success"
    txn.refund_status = "REFUND_REQUESTED"
    txn.updated_at = datetime.utcnow() - timedelta(minutes=10)
    db_session.commit()
    
    reconcile_stuck_refunds(db_session)
    
    db_session.expire_all()
    txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.refund_status == "REFUNDED"

# Test 6 — REFUND_REQUESTED gateway failure
def test_refund_requested_failure(db_session):
    txn_id = f"verify_refund_fail_{uuid.uuid4().hex[:8]}"
    txn = setup_transaction(db_session, txn_id)
    txn.status = "success"
    txn.refund_status = "REFUND_REQUESTED"
    txn.updated_at = datetime.utcnow() - timedelta(minutes=10)
    db_session.commit()
    
    reconcile_stuck_refunds(db_session)
    
    db_session.expire_all()
    txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.refund_status == "REFUND_FAILED"

# Test 7 — REFUND_REQUESTED gateway ambiguity
def test_refund_requested_ambiguity(db_session):
    txn_id = f"verify_refund_unavailable_{uuid.uuid4().hex[:8]}"
    txn = setup_transaction(db_session, txn_id)
    txn.status = "success"
    txn.refund_status = "REFUND_REQUESTED"
    txn.updated_at = datetime.utcnow() - timedelta(minutes=10)
    db_session.commit()
    
    reconcile_stuck_refunds(db_session)
    
    db_session.expire_all()
    txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.refund_status == "REFUND_UNKNOWN"

# Test 8 — Concurrent reconciliation
def test_concurrent_reconciliation(db_session):
    txn_id = f"verify_refund_success_{uuid.uuid4().hex[:8]}"
    txn = setup_transaction(db_session, txn_id)
    txn.status = "success"
    txn.refund_status = "REFUND_REQUESTED"
    txn.updated_at = datetime.utcnow() - timedelta(minutes=10)
    db_session.commit()
    
    # Run twice consecutively, simulate concurrent sweeps (or one after another)
    with patch.object(MockGateway, 'process_refund') as mock_process:
        reconcile_stuck_refunds(db_session)
        
        # Second run should ignore it because it's now REFUNDED
        reconcile_stuck_refunds(db_session)
        
        mock_process.assert_not_called()
        
    db_session.expire_all()
    txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.refund_status == "REFUNDED"

# Test 9 — Retry after ESCALATED
def test_retry_after_escalated(db_session):
    txn_id = f"txn_retry_after_{uuid.uuid4().hex[:8]}"
    txn = setup_transaction(db_session, txn_id)
    
    attempt1_id = f"att_1_{uuid.uuid4().hex[:8]}"
    att1 = RecoveryAttempt(
        id=attempt1_id,
        transaction_id=txn_id,
        outcome_status="ESCALATED"
    )
    db_session.add(att1)
    db_session.commit()
    
    # User calls /payments/{txn_id}/recover, this invokes orchestrator
    txn_incoming = TransactionIncoming(
        id=txn_id,
        customer_id=txn.customer_id,
        amount=txn.amount,
        currency=txn.currency,
        payment_status="failed",
        payment_method="card",
        retry_count=1
    )
    
    # Mock Policy to ALWAYS allow, forcing it to reach ExecutionGuard
    with patch('app.services.orchestrator.evaluate_policy', return_value=(True, "RETRY_PAYMENT", "Mock allowed")):
        with patch.object(get_gateway(), 'execute_recovery_action') as mock_gateway_exec:
            orchestrator = RecoveryOrchestrator(db_session)
            result = orchestrator.process_transaction(txn_incoming)
            
            # The orchestrator should return the FAILED block from ExecutionGuard
            assert result["outcome"] == "FAILED"
            # And gateway must never have been called!
            mock_gateway_exec.assert_not_called()
