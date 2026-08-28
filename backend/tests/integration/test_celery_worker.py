import pytest
import uuid
from sqlalchemy.orm import sessionmaker
from app.models.db_models import Transaction, RecoveryAttempt, Base
from app.worker.tasks import process_orchestrator
from app.gateways.base import GatewayInterface
from app.database import engine, SessionLocal

# Mock Gateway that records calls
class MockGatewayCelery(GatewayInterface):
    def __init__(self):
        self.execute_calls = 0
        self.refund_calls = 0

    def execute_recovery_action(self, db_session, transaction_id, action, idempotency_key, attempt_id):
        from app.services.state_machine import transition_recovery_attempt
        self.execute_calls += 1
        transition_recovery_attempt(db_session, attempt_id, "EXECUTING", reason="Initiating external gateway call")
        transition_recovery_attempt(db_session, attempt_id, "SUCCEEDED", reason="Mock Success")
        return {"status": "SUCCEEDED", "external_reference": f"mock_ext_{uuid.uuid4().hex[:8]}"}
        
    def process_refund(self, db_session, transaction_id, amount, reason):
        self.refund_calls += 1
        return {"status": "REFUNDED"}

    def verify_transaction_state(self, db_session, transaction_id, attempt_id):
        return "UNKNOWN"
        
    def verify_refund(self, db_session, transaction_id):
        return "REFUND_UNKNOWN"

@pytest.fixture(autouse=True)
def override_gateway(monkeypatch):
    mock = MockGatewayCelery()
    monkeypatch.setattr("app.services.execution_guard.get_gateway", lambda: mock)
    monkeypatch.setattr("app.services.reconciliation.get_gateway", lambda: mock)
    return mock

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_celery_worker_executes_orchestration(override_gateway):
    """1. Celery task executes orchestration."""
    sess = SessionLocal()
    
    txn_id = f"txn_celery_{uuid.uuid4().hex[:8]}"
    txn = Transaction(id=txn_id, amount=1000, status="failed", recovery_status="NOT_STARTED", currency="INR")
    sess.add(txn)
    sess.commit()
    sess.close()
    
    # Process synchronously by calling the task directly for test
    process_orchestrator(txn_id)
    
    # Verify DB state
    sess2 = SessionLocal()
    txn_after = sess2.query(Transaction).filter(Transaction.id == txn_id).first()
    attempts = sess2.query(RecoveryAttempt).filter(RecoveryAttempt.transaction_id == txn_id).all()
    
    assert txn_after.recovery_status == "SUCCEEDED"
    assert len(attempts) > 0
    assert attempts[-1].outcome_status == "SUCCEEDED"
    
    assert override_gateway.execute_calls == 1
    sess2.close()

def test_celery_worker_duplicate_task_delivery(override_gateway):
    """3. Duplicate task delivery does not duplicate execution."""
    sess = SessionLocal()
    
    txn_id = f"txn_celery_dup_{uuid.uuid4().hex[:8]}"
    txn = Transaction(id=txn_id, amount=1000, status="failed", recovery_status="NOT_STARTED", currency="INR")
    sess.add(txn)
    sess.commit()
    sess.close()
    
    # Simulate duplicate delivery: task runs twice sequentially
    process_orchestrator(txn_id)
    process_orchestrator(txn_id)
    
    # Verify DB state
    sess2 = SessionLocal()
    txn_after = sess2.query(Transaction).filter(Transaction.id == txn_id).first()
    
    assert txn_after.recovery_status == "SUCCEEDED"
    
    # Only one gateway call should be made
    assert override_gateway.execute_calls == 1
    sess2.close()
