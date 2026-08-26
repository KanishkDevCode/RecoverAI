import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, Base, engine
from sqlalchemy.orm import sessionmaker

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def test_developer_overrides_propagate_safe_recovery():
    response = client.post("/api/v1/payments", json={
        "id": "txn_test_safe_recovery",
        "customer_id": "cust_test",
        "amount": 450,
        "currency": "INR",
        "payment_method": "card",
        "mode": "test",
        "developer_overrides": {
            "failure_code": "bank_timeout",
            "failure_reason": "Temporary bank failure",
            "retry_count": 0
        }
    }, headers={"X-API-Key": "test_secret_key_123"})
    
    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"
    
    # Verify in DB
    db = TestingSessionLocal()
    from app.models.db_models import Transaction
    txn = db.query(Transaction).filter(Transaction.id == "txn_test_safe_recovery").first()
    assert txn is not None
    assert txn.failure_code == "bank_timeout"
    assert txn.amount == 450

def test_developer_overrides_propagate_fraud():
    response = client.post("/api/v1/payments", json={
        "id": "txn_test_fraud",
        "customer_id": "cust_test",
        "amount": 200,
        "currency": "INR",
        "payment_method": "card",
        "mode": "test",
        "developer_overrides": {
            "failure_code": "fraud_suspected",
            "failure_reason": "Stolen card",
            "retry_count": 0
        }
    }, headers={"X-API-Key": "test_secret_key_123"})
    
    assert response.status_code == 200
    
    db = TestingSessionLocal()
    from app.models.db_models import Transaction
    txn = db.query(Transaction).filter(Transaction.id == "txn_test_fraud").first()
    assert txn is not None
    assert txn.failure_code == "fraud_suspected"
    assert txn.amount == 200

def test_developer_overrides_propagate_high_value():
    response = client.post("/api/v1/payments", json={
        "id": "txn_test_high_value",
        "customer_id": "cust_test",
        "amount": 6500,
        "currency": "INR",
        "payment_method": "card",
        "mode": "test",
        "developer_overrides": {
            "failure_code": "bank_timeout",
            "failure_reason": "Bank timeout",
            "retry_count": 0
        }
    }, headers={"X-API-Key": "test_secret_key_123"})
    
    assert response.status_code == 200
    
    db = TestingSessionLocal()
    from app.models.db_models import Transaction
    txn = db.query(Transaction).filter(Transaction.id == "txn_test_high_value").first()
    assert txn is not None
    assert txn.failure_code == "bank_timeout"

def test_developer_overrides_propagate_retry_limit():
    response = client.post("/api/v1/payments", json={
        "id": "txn_test_retry_limit",
        "customer_id": "cust_test",
        "amount": 900,
        "currency": "INR",
        "payment_method": "card",
        "mode": "test",
        "developer_overrides": {
            "failure_code": "bank_timeout",
            "failure_reason": "Timeout",
            "retry_count": 2
        }
    }, headers={"X-API-Key": "test_secret_key_123"})
    
    assert response.status_code == 200
    
    db = TestingSessionLocal()
    from app.models.db_models import Transaction
    txn = db.query(Transaction).filter(Transaction.id == "txn_test_retry_limit").first()
    assert txn is not None
    assert txn.failure_code == "bank_timeout"
