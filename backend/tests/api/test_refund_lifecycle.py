import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, Base, engine
from sqlalchemy.orm import sessionmaker
import uuid

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def setup_db_transaction(status, id):
    db = TestingSessionLocal()
    from app.models.db_models import Transaction
    txn = Transaction(
        id=id,
        customer_id="cust_1",
        amount=500.0,
        currency="INR",
        status=status
    )
    db.add(txn)
    db.commit()
    db.close()

def test_refund_unallowed_on_failed():
    txn_id = f"txn_fail_{uuid.uuid4().hex[:6]}"
    setup_db_transaction("failed", txn_id)
    response = client.post(f"/api/v1/payments/{txn_id}/refund", headers={"X-API-Key": "test_secret_key_123"})
    assert response.status_code == 400
    assert "Only successfully captured payments" in response.json()["detail"]

def test_refund_success_payment():
    txn_id = f"txn_succ_{uuid.uuid4().hex[:6]}"
    setup_db_transaction("success", txn_id)
    response = client.post(f"/api/v1/payments/{txn_id}/refund", headers={"X-API-Key": "test_secret_key_123"})
    assert response.status_code == 200
    assert response.json()["status"] == "REFUND_PROCESSING"
    
    # Check duplicate refund hits idempotency or already processing check
    response2 = client.post(f"/api/v1/payments/{txn_id}/refund", headers={"X-API-Key": "test_secret_key_123"})
    assert response2.status_code == 400
    assert "already in progress" in response2.json()["detail"]

def test_refund_recovered_payment():
    txn_id = f"txn_rec_{uuid.uuid4().hex[:6]}"
    setup_db_transaction("recovered", txn_id)
    response = client.post(f"/api/v1/payments/{txn_id}/refund", headers={"X-API-Key": "test_secret_key_123"})
    assert response.status_code == 200
    assert response.json()["status"] == "REFUND_PROCESSING"
