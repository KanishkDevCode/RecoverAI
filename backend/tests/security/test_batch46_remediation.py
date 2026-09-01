import pytest
import threading
import uuid
import time
from datetime import datetime, timedelta
from app.database import Base, engine, SessionLocal
from app.models.db_models import Transaction, RecoveryAttempt, IdempotencyRecord, WebhookEvent
from app.services.refund_service import get_refund_service
from app.services.orchestrator import RecoveryOrchestrator
from app.services.execution_guard import get_execution_guard
from app.services.reconciliation import reconcile_orphaned_attempts
from app.schemas.transaction import PaymentCreateRequest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

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
    session = SessionLocal()
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()

# ---------------------------------------------------------
# P0 #1: CONCURRENT REFUND SAFETY
# ---------------------------------------------------------
def test_concurrent_refund_race(db_session):
    """
    Simulates 10 concurrent refund requests using different idempotency keys.
    Validates that only ONE refund operation reaches REFUND_PROCESSING or REFUNDED,
    and gateway execution only happens once.
    """
    txn_id = f"txn_{uuid.uuid4().hex[:8]}"
    db_session.add(Transaction(
        id=txn_id,
        customer_id="cust_1",
        amount=1000,
        currency="USD",
        status="success",
        recovery_status="NOT_STARTED"
    ))
    db_session.commit()

    results = []
    
    def run_refund(idem_key):
        # We need a new session per thread
        session = SessionLocal()
        try:
            refund_service = get_refund_service(session)
            res = refund_service.initiate_refund(txn_id, idem_key)
            results.append(res)
        except Exception as e:
            results.append({"status": "FAILED", "error": str(e)})
        finally:
            session.close()

    threads = []
    for i in range(10):
        t = threading.Thread(target=run_refund, args=(f"idem_{i}_{uuid.uuid4().hex[:4]}",))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Analyze results
    success_count = sum(1 for r in results if r.get("status") in ["REFUND_PROCESSING", "REFUNDED"])
    failed_count = sum(1 for r in results if r.get("status") == "FAILED")

    assert success_count == 1, f"Expected exactly 1 successful refund initiation, got {success_count}. Results: {results}"
    assert failed_count == 9, f"Expected exactly 9 failed refund initiations, got {failed_count}"

    db_session.expire_all()
    txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.refund_status in ["REFUND_PROCESSING", "REFUNDED"]

# ---------------------------------------------------------
# P0 #2: GATEWAY SUCCESS + DB CRASH WINDOW
# ---------------------------------------------------------
def test_gateway_success_db_crash_window(db_session, monkeypatch):
    """
    Simulates a crash after gateway success but before orchestrator updates the Transaction.
    ExecutionGuard must block subsequent attempts because a SUCCEEDED attempt exists.
    """
    txn_id = f"txn_{uuid.uuid4().hex[:8]}"
    db_session.add(Transaction(
        id=txn_id,
        customer_id="cust_1",
        amount=1000,
        currency="USD",
        status="failed",
        recovery_status="NOT_STARTED" # CRASH SCENARIO: this didn't get updated
    ))
    db_session.commit()

    attempt_id = f"att_{uuid.uuid4().hex[:8]}"
    db_session.add(RecoveryAttempt(
        id=attempt_id,
        transaction_id=txn_id,
        outcome_status="SUCCEEDED", # CRASH SCENARIO: attempt updated
    ))
    db_session.commit()

    guard = get_execution_guard(db_session)
    
    new_attempt_id = f"att_new_{uuid.uuid4().hex[:8]}"
    db_session.add(RecoveryAttempt(
        id=new_attempt_id,
        transaction_id=txn_id,
        outcome_status="AUTHORIZED"
    ))
    db_session.commit()

    result = guard.execute(txn_id, new_attempt_id, "RETRY_PAYMENT", f"idem_{uuid.uuid4()}", 1)
    
    assert result["status"] == "FAILED"
    assert "Conflicting attempt" in result["result_message"]

# ---------------------------------------------------------
# P1 #1: PAYMENT IntegrityError
# ---------------------------------------------------------
def test_payment_integrity_error_swallowing(db_session):
    """
    Validates that a duplicate transaction ID returns 409 Conflict,
    even if an idempotency key is provided, instead of swallowing it.
    """
    txn_id = "txn_duplicate_test"
    db_session.add(Transaction(
        id=txn_id, customer_id="cust_1", amount=1000, currency="USD", status="success"
    ))
    db_session.commit()

    from app.config import settings
    headers = {
        "X-API-Key": settings.MERCHANT_API_KEY,
        "Idempotency-Key": f"idem_{uuid.uuid4()}" # New key, existing txn
    }
    payload = {
        "id": txn_id,
        "amount": 10.0,
        "currency": "USD",
        "customer_id": "cust_1",
        "payment_method": "card",
        "mode": "test"
    }

    resp = client.post("/api/v1/payments", json=payload, headers=headers)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]

# ---------------------------------------------------------
# P1 #2: AUTHORIZED ORPHANS
# ---------------------------------------------------------
def test_authorized_orphan_no_evidence(db_session):
    """
    Orphaned AUTHORIZED attempt with NO idempotency record should transition to STOPPED.
    """
    txn_id = f"txn_{uuid.uuid4().hex[:8]}"
    attempt_id = f"att_{uuid.uuid4().hex[:8]}"
    db_session.add(Transaction(id=txn_id, amount=100, status="success", recovery_status="NOT_STARTED"))
    db_session.flush()
    db_session.add(RecoveryAttempt(
        id=attempt_id,
        transaction_id=txn_id,
        outcome_status="AUTHORIZED",
        created_at=datetime.utcnow() - timedelta(minutes=10)
    ))
    db_session.commit()

    reconcile_orphaned_attempts(db_session)
    
    db_session.expire_all()
    attempt = db_session.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).first()
    assert attempt.outcome_status == "STOPPED"

def test_authorized_orphan_with_evidence(db_session):
    """
    Orphaned AUTHORIZED attempt WITH idempotency record should transition to UNKNOWN.
    """
    txn_id = f"txn_{uuid.uuid4().hex[:8]}"
    attempt_id = f"att_{uuid.uuid4().hex[:8]}"
    db_session.add(Transaction(id=txn_id, amount=100, status="success", recovery_status="NOT_STARTED"))
    db_session.flush()
    db_session.add(RecoveryAttempt(
        id=attempt_id,
        transaction_id=txn_id,
        outcome_status="AUTHORIZED",
        created_at=datetime.utcnow() - timedelta(minutes=10)
    ))
    db_session.add(IdempotencyRecord(
        key=f"idem_{uuid.uuid4()}",
        attempt_id=attempt_id,
        status="PENDING"
    ))
    db_session.commit()

    reconcile_orphaned_attempts(db_session)
    
    db_session.expire_all()
    attempt = db_session.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).first()
    assert attempt.outcome_status == "UNKNOWN"

from app.worker.tasks import process_webhook

def test_webhook_intent_validation(db_session):
    """
    A webhook should not blindly transition a transaction to REFUNDED
    unless it was in REFUND_REQUESTED or REFUND_PROCESSING.
    """
    txn_id = f"txn_{uuid.uuid4().hex[:8]}"
    db_session.add(Transaction(
        id=txn_id,
        customer_id="cust_1",
        amount=1000,
        currency="USD",
        status="success",
        refund_status=None # No intent!
    ))
    db_session.commit()

    event_id = "evt_123"
    db_session.add(WebhookEvent(
        event_id=event_id,
        event_type="refund.completed",
        transaction_id=txn_id,
        payload_hash="dummy",
        payload="{}"
    ))
    db_session.commit()

    # Simulate webhook calling internal function
    process_webhook(event_id)
    
    db_session.expire_all()
    txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.refund_status is None, "Webhook bypassed intent validation"
    
    # Now set intent
    txn.refund_status = "REFUND_REQUESTED"
    db_session.commit()
    
    event_id2 = "evt_124"
    db_session.add(WebhookEvent(
        event_id=event_id2,
        event_type="refund.completed",
        transaction_id=txn_id,
        payload_hash="dummy",
        payload="{}"
    ))
    db_session.commit()

    process_webhook(event_id2)
    db_session.expire_all()
    txn = db_session.query(Transaction).filter(Transaction.id == txn_id).first()
    assert txn.refund_status == "REFUNDED", "Webhook failed to process valid intent"
