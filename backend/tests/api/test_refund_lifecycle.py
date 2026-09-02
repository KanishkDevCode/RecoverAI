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

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # Safe cleanup using reversed sorted_tables to respect FKs
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

def setup_db_transaction(status, id, recovery_status="NOT_STARTED"):
    db = TestingSessionLocal()
    from app.models.db_models import Transaction
    txn = Transaction(
        id=id,
        customer_id="cust_1",
        amount=50000,
        currency="INR",
        status=status,
        recovery_status=recovery_status
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
    assert response.json()["status"] == "REFUNDED"
    
    # Check duplicate refund hits idempotency or already processing check
    response2 = client.post(f"/api/v1/payments/{txn_id}/refund", headers={"X-API-Key": "test_secret_key_123"})
    assert response2.status_code == 400
    assert "already in progress" in response2.json()["detail"]

def test_refund_recovered_payment():
    txn_id = f"txn_rec_{uuid.uuid4().hex[:6]}"
    setup_db_transaction("failed", txn_id, recovery_status="SUCCEEDED")
    response = client.post(f"/api/v1/payments/{txn_id}/refund", headers={"X-API-Key": "test_secret_key_123"})
    assert response.status_code == 200
    assert response.json()["status"] == "REFUNDED"
