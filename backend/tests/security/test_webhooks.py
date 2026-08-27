import pytest
import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from app.main import app
from app.database import engine, Base, get_db
from app.config import settings
from app.models.db_models import Transaction, WebhookEvent
from sqlalchemy.orm import sessionmaker

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def generate_signature(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def test_webhook_missing_signature():
    payload = {"event_id": "evt_1", "event_type": "refund.completed", "transaction_id": "txn_1"}
    response = client.post("/api/v1/webhooks/gateway", json=payload)
    assert response.status_code == 401
    assert "Missing signature" in response.json()["detail"]

def test_webhook_invalid_signature():
    payload = {"event_id": "evt_1", "event_type": "refund.completed", "transaction_id": "txn_1"}
    headers = {"X-Razorpay-Signature": "invalid_signature"}
    response = client.post("/api/v1/webhooks/gateway", json=payload, headers=headers)
    assert response.status_code == 401
    assert "Invalid signature" in response.json()["detail"]

def test_webhook_valid_signature_success():
    db = TestingSessionLocal()
    txn = Transaction(id="txn_1", status="success", refund_status="REFUND_PROCESSING", amount=100)
    db.add(txn)
    db.commit()
    db.close()
    
    payload = {"event_id": "evt_1", "event_type": "refund.completed", "transaction_id": "txn_1"}
    payload_str = json.dumps(payload).replace(" ", "")
    # Note: TestClient json dumps might have spaces. We send data directly as bytes for strict signature matching.
    payload_bytes = json.dumps(payload).encode('utf-8')
    sig = generate_signature(payload_bytes.decode('utf-8'), settings.WEBHOOK_SECRET)
    
    headers = {"X-Razorpay-Signature": sig, "Content-Type": "application/json"}
    response = client.post("/api/v1/webhooks/gateway", data=payload_bytes, headers=headers)
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    db = TestingSessionLocal()
    txn = db.query(Transaction).filter(Transaction.id == "txn_1").first()
    assert txn.refund_status == "REFUNDED"
    
    # test duplicate idempotency
    response2 = client.post("/api/v1/webhooks/gateway", data=payload_bytes, headers=headers)
    assert response2.status_code == 200
    assert response2.json()["message"] == "already processed"
    
    events = db.query(WebhookEvent).filter(WebhookEvent.event_id == "evt_1").all()
    assert len(events) == 1
