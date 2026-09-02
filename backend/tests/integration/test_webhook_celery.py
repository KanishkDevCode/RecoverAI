import pytest
import uuid
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from app.models.db_models import Transaction, WebhookEvent, AuditLog
from app.config import settings
from app.database import Base, engine, SessionLocal, get_db
from fastapi.testclient import TestClient
from app.main import app

TestingSessionLocal = SessionLocal

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

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
    session = TestingSessionLocal()
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def test_txn(db_session):
    txn_id = f"txn_mock_{uuid.uuid4().hex[:8]}"
    txn = Transaction(
        id=txn_id,
        amount=5000,
        currency="INR",
        status="success",
        recovery_status="SUCCEEDED",
        refund_status="REFUND_REQUESTED"
    )
    db_session.add(txn)
    db_session.commit()
    return txn

def generate_signature(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()

def test_webhook_persists_before_enqueue(client, db_session, test_txn, monkeypatch):
    """
    Test that the webhook endpoint successfully saves the WebhookEvent and enqueues.
    """
    enqueued = []
    def mock_apply_async(*args, **kwargs):
        enqueued.append(kwargs.get("args")[0])
        
    import app.worker.tasks
    monkeypatch.setattr(app.worker.tasks.process_webhook, "apply_async", mock_apply_async)
    
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": event_id,
        "event_type": "refund.completed",
        "transaction_id": test_txn.id
    }
    payload_bytes = json.dumps(payload).encode('utf-8')
    sig = generate_signature(payload_bytes, settings.RAZORPAY_WEBHOOK_SECRET)
    
    resp = client.post(
        "/api/v1/webhooks/gateway",
        content=payload_bytes,
        headers={"X-Razorpay-Signature": sig}
    )
    
    assert resp.status_code == 200
    
    event = db_session.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    assert event is not None
    assert event.processing_status == "PENDING"
    
    assert len(enqueued) == 1
    assert enqueued[0] == event_id

def test_successful_celery_processing(db_session, test_txn):
    """
    Test that process_webhook works and updates refund status securely.
    """
    from app.worker.tasks import process_webhook
    
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = WebhookEvent(
        event_id=event_id,
        event_type="refund.completed",
        transaction_id=test_txn.id,
        payload_hash="dummy",
        payload=json.dumps({"transaction_id": test_txn.id, "event_type": "refund.completed"}),
        processing_status="PENDING"
    )
    db_session.add(event)
    db_session.commit()
    
    # Process it directly via function call (like Celery does)
    process_webhook(event_id)
    
    db_session.expire_all()
    updated_txn = db_session.query(Transaction).filter(Transaction.id == test_txn.id).first()
    assert updated_txn.refund_status == "REFUNDED"
    
    updated_event = db_session.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    assert updated_event.processing_status == "PROCESSED"
    assert updated_event.processed_at is not None
    
    audit = db_session.query(AuditLog).filter(
        AuditLog.transaction_id == test_txn.id,
        AuditLog.event_type == "REFUND_STATE_CHANGE",
        AuditLog.new_state == "REFUNDED"
    ).first()
    assert audit is not None

def test_duplicate_event_delivery(db_session, test_txn):
    """
    Test duplicate Celery deliveries produce exactly one state transition.
    """
    from app.worker.tasks import process_webhook
    
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = WebhookEvent(
        event_id=event_id,
        event_type="refund.completed",
        transaction_id=test_txn.id,
        payload_hash="dummy",
        payload=json.dumps({"transaction_id": test_txn.id, "event_type": "refund.completed"}),
        processing_status="PENDING"
    )
    db_session.add(event)
    db_session.commit()
    
    # Process it multiple times
    process_webhook(event_id)
    process_webhook(event_id)
    process_webhook(event_id)
    
    db_session.expire_all()
    audits = db_session.query(AuditLog).filter(
        AuditLog.transaction_id == test_txn.id,
        AuditLog.event_type == "REFUND_STATE_CHANGE",
        AuditLog.new_state == "REFUNDED"
    ).all()
    
    assert len(audits) == 1

def test_worker_crash_recovery(db_session, test_txn, monkeypatch):
    """
    Simulate a crash after modifying the transaction, before modifying the WebhookEvent.
    """
    from app.worker.tasks import process_webhook
    
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = WebhookEvent(
        event_id=event_id,
        event_type="refund.completed",
        transaction_id=test_txn.id,
        payload_hash="dummy",
        payload=json.dumps({"transaction_id": test_txn.id, "event_type": "refund.completed"}),
        processing_status="PENDING"
    )
    db_session.add(event)
    db_session.commit()
    
    # We will simulate the crash manually
    txn = db_session.query(Transaction).filter(Transaction.id == test_txn.id).first()
    txn.refund_status = "REFUNDED"
    db_session.commit()
    
    # Now Celery retries it
    process_webhook(event_id)
    
    db_session.expire_all()
    updated_event = db_session.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    assert updated_event.processing_status == "PROCESSED"
    # It gracefully handled it

def test_invalid_signature_rejected(client):
    payload = b'{"event_id": "test"}'
    resp = client.post(
        "/api/v1/webhooks/gateway",
        content=payload,
        headers={"X-Razorpay-Signature": "invalid"}
    )
    assert resp.status_code == 401

def test_invalid_webhook_intent_cannot_change_state(db_session, test_txn):
    """
    If a refund is not REFUND_REQUESTED/PROCESSING, a webhook cannot blind-refund it.
    """
    from app.worker.tasks import process_webhook
    
    test_txn.refund_status = None
    db_session.commit()
    
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = WebhookEvent(
        event_id=event_id,
        event_type="refund.completed",
        transaction_id=test_txn.id,
        payload_hash="dummy",
        payload=json.dumps({"transaction_id": test_txn.id, "event_type": "refund.completed"}),
        processing_status="PENDING"
    )
    db_session.add(event)
    db_session.commit()
    
    process_webhook(event_id)
    
    db_session.expire_all()
    updated_txn = db_session.query(Transaction).filter(Transaction.id == test_txn.id).first()
    assert updated_txn.refund_status is None # Unchanged
    
    updated_event = db_session.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    assert updated_event.processing_status == "PROCESSED" # Event is consumed so it doesn't loop
    
def test_redis_task_loss_recovery(db_session, test_txn):
    """
    If the Celery task is lost, reconcile_pending_webhooks should re-enqueue it.
    """
    from app.services.reconciliation import reconcile_pending_webhooks
    import app.worker.tasks
    
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = WebhookEvent(
        event_id=event_id,
        event_type="refund.completed",
        transaction_id=test_txn.id,
        payload_hash="dummy",
        payload=json.dumps({"transaction_id": test_txn.id, "event_type": "refund.completed"}),
        processing_status="PENDING",
        received_at=datetime.utcnow() - timedelta(minutes=10) # 10 mins ago (stuck)
    )
    db_session.add(event)
    db_session.commit()
    
    enqueued = []
    def mock_apply_async(*args, **kwargs):
        enqueued.append(kwargs.get("args")[0])
        
    original_apply_async = app.worker.tasks.process_webhook.apply_async
    app.worker.tasks.process_webhook.apply_async = mock_apply_async
    
    reconcile_pending_webhooks(db_session)
    
    app.worker.tasks.process_webhook.apply_async = original_apply_async
    
    assert len(enqueued) == 1
    assert enqueued[0] == event_id

def test_webhook_worker_cannot_execute_financial_commands(db_session, test_txn, monkeypatch):
    from app.worker.tasks import process_webhook
    
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = WebhookEvent(
        event_id=event_id,
        event_type="refund.completed",
        transaction_id=test_txn.id,
        payload_hash="dummy",
        payload=json.dumps({"transaction_id": test_txn.id, "event_type": "refund.completed"}),
        processing_status="PENDING"
    )
    db_session.add(event)
    db_session.commit()
    
    # We monkeypatch the gateway to strictly raise if called
    from app.gateways import get_gateway
    gw = get_gateway()
    
    def raise_if_called(*args, **kwargs):
        raise RuntimeError("FINANCIAL EXECUTION CALLED BY WEBHOOK")
        
    monkeypatch.setattr(gw, "execute_recovery_action", raise_if_called)
    monkeypatch.setattr(gw, "process_refund", raise_if_called)
    
    # If it calls any of those, it will raise RuntimeError and fail the test
    process_webhook(event_id)
    
    db_session.expire_all()
    updated_txn = db_session.query(Transaction).filter(Transaction.id == test_txn.id).first()
    assert updated_txn.refund_status == "REFUNDED"
