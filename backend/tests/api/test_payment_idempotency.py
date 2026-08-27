import pytest
import concurrent.futures
from fastapi.testclient import TestClient
import uuid
import hashlib
from app.main import app
from app.database import get_db, Base, engine
from sqlalchemy.orm import sessionmaker

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)
API_KEY = "test_secret_key_123"
HEADERS = {"X-API-Key": API_KEY}

def test_payment_idempotency_same_request():
    txn_id = f"txn_{uuid.uuid4().hex[:10]}"
    idempotency_key = f"idem_{uuid.uuid4().hex}"
    payload = {
        "id": txn_id,
        "amount": 1000.0,
        "currency": "INR",
        "customer_id": "cust_123",
        "payment_method": "card",
        "mode": "test"
    }
    
    headers = {**HEADERS, "Idempotency-Key": idempotency_key}
    
    # First request
    resp1 = client.post("/api/v1/payments", json=payload, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "Idempotent-Replay" not in resp1.headers
    
    # Second request
    resp2 = client.post("/api/v1/payments", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    
    assert data1 == data2
    assert resp2.headers.get("Idempotent-Replay") == "true"
    
def test_payment_idempotency_conflict():
    txn_id = f"txn_{uuid.uuid4().hex[:10]}"
    idempotency_key = f"idem_{uuid.uuid4().hex}"
    
    headers = {**HEADERS, "Idempotency-Key": idempotency_key}
    
    payload1 = {
        "id": txn_id,
        "amount": 1000.0,
        "currency": "INR",
        "customer_id": "cust_123",
        "payment_method": "card",
        "mode": "test"
    }
    
    client.post("/api/v1/payments", json=payload1, headers=headers)
    
    # Second request with different amount but same key
    payload2 = {
        "id": txn_id,
        "amount": 5000.0,  # Changed
        "currency": "INR",
        "customer_id": "cust_123",
        "payment_method": "card",
        "mode": "test"
    }
    
    resp2 = client.post("/api/v1/payments", json=payload2, headers=headers)
    assert resp2.status_code == 409
    assert "different parameters" in resp2.json()["detail"]

def test_payment_idempotency_concurrent_requests():
    txn_id = f"txn_{uuid.uuid4().hex[:10]}"
    idempotency_key = f"idem_concurrent_{uuid.uuid4().hex}"
    
    headers = {**HEADERS, "Idempotency-Key": idempotency_key}
    
    payload = {
        "id": txn_id,
        "amount": 2500.0,
        "currency": "INR",
        "customer_id": "cust_concurrent",
        "payment_method": "card",
        "mode": "live"
    }
    
    def make_request():
        # Create a new TestClient instance per thread to avoid event loop issues
        client_thread = TestClient(app)
        return client_thread.post("/api/v1/payments", json=payload, headers=headers)
        
    # Simulate 5 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request) for _ in range(5)]
        responses = [f.result() for f in futures]
        
    status_codes = [r.status_code for r in responses]
    replays = [r.headers.get("Idempotent-Replay") for r in responses]
    
    # Some might get 409 (Request already in progress) if they hit exactly while the first is PENDING
    # Some might get 200 with replay if they hit after the first is COMPLETED
    # One must get 200 without replay (the original)
    assert 200 in status_codes
    original_success = [r for r in responses if r.status_code == 200 and r.headers.get("Idempotent-Replay") != "true"]
    assert len(original_success) == 1
    
    # Check DB for single transaction and IdempotencyRecord
    db = TestingSessionLocal()
    from app.models.db_models import Transaction, IdempotencyRecord
    txns = db.query(Transaction).filter(Transaction.id == txn_id).all()
    assert len(txns) == 1
    
    api_key_hash = hashlib.sha256(API_KEY.encode()).hexdigest()[:8]
    scoped_key = f"pay_{api_key_hash}_{idempotency_key}"
    
    idems = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == scoped_key).all()
    assert len(idems) == 1
    db.close()
