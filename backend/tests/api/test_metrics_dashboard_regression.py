import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.database import get_db, Base, engine
from app.models.db_models import Transaction, RecoveryAttempt

# Setup Test DB
Base.metadata.create_all(bind=engine)

@pytest.fixture
def client():
    # Provide a clean db session for each test
    from app.database import SessionLocal
    db = SessionLocal()
    
    # Clean up before test
    db.query(RecoveryAttempt).delete()
    db.query(Transaction).delete()
    db.commit()
    
    # Insert test data
    txn1 = Transaction(id="txn_dash_1", customer_id="c1", amount=10000, currency="USD", status="failed", recovery_status="SUCCEEDED")
    txn2 = Transaction(id="txn_dash_2", customer_id="c2", amount=20000, currency="USD", status="failed", recovery_status="FAILED")
    txn3 = Transaction(id="txn_dash_3", customer_id="c3", amount=30000, currency="USD", status="failed", recovery_status="FAILED")
    
    db.add_all([txn1, txn2, txn3])
    db.commit()
    
    ra1 = RecoveryAttempt(id="ra_1", transaction_id="txn_dash_1", outcome_status="SUCCEEDED")
    ra2 = RecoveryAttempt(id="ra_2", transaction_id="txn_dash_2", outcome_status="ESCALATED")
    ra3 = RecoveryAttempt(id="ra_3", transaction_id="txn_dash_3", outcome_status="STOPPED")
    
    db.add_all([ra1, ra2, ra3])
    db.commit()
    
    def override_get_db():
        try:
            yield db
        finally:
            db.close()
            
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c
        
    app.dependency_overrides.clear()

def test_dashboard_metrics_accuracy(client):
    """
    Tests that dashboard metrics accurately filter by SUCCEEDED, ESCALATED, and STOPPED 
    instead of the old incorrect values.
    """
    response = client.get("/api/v1/dashboard/metrics", headers={"X-API-Key": "test_secret_key_123"})
    assert response.status_code == 200
    data = response.json()
    
    assert data["successful_actions"] == 1
    assert data["escalations"] == 1
    assert data["stopped_automations"] == 1

def test_observability_metrics_accuracy(client):
    """
    Tests that observability metrics query the correct outcome_status column 
    and don't crash on PostgreSQL.
    """
    from app.database import SessionLocal
    db = SessionLocal()
    txn4 = Transaction(id="txn_dash_4", customer_id="c4", amount=40000, currency="USD", status="failed", recovery_status="PROCESSING")
    db.add(txn4)
    db.commit()
    
    ra4 = RecoveryAttempt(id="ra_4", transaction_id="txn_dash_4", outcome_status="UNKNOWN")
    ra5 = RecoveryAttempt(id="ra_5", transaction_id="txn_dash_4", outcome_status="EXECUTING")
    db.add_all([ra4, ra5])
    db.commit()
    db.close()

    response = client.get("/api/v1/metrics", headers={"X-Observability-API-Key": "test_obs_key_123"})
    assert response.status_code == 200
    data = response.json()
    
    assert data["recovery_attempts_unknown"] >= 1
    assert data["recovery_attempts_escalated"] >= 1
    assert "recovery_attempts_stuck_executing" in data
