import pytest
from app.services.refund_service import get_refund_service
from app.models.db_models import Transaction, AuditLog
from app.database import engine, Base
from sqlalchemy.orm import sessionmaker

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_refund_service_missing_transaction():
    db = TestingSessionLocal()
    service = get_refund_service(db)
    res = service.initiate_refund("non_existent", "key_1")
    assert res["status"] == "FAILED"

def test_refund_service_unauthorized_state():
    db = TestingSessionLocal()
    txn = Transaction(id="txn_1", status="failed", recovery_status="FAILED", amount=100)
    db.add(txn)
    db.commit()
    
    service = get_refund_service(db)
    res = service.initiate_refund("txn_1", "key_1")
    assert res["status"] == "FAILED"
    assert "successfully captured" in res["result_message"].lower()

def test_refund_service_already_refunded():
    db = TestingSessionLocal()
    txn = Transaction(id="txn_1", status="success", refund_status="REFUNDED", amount=100)
    db.add(txn)
    db.commit()
    
    service = get_refund_service(db)
    res = service.initiate_refund("txn_1", "key_1")
    assert res["status"] == "FAILED"
    assert "already in progress" in res["result_message"].lower()

def test_refund_service_success_initiation():
    db = TestingSessionLocal()
    txn = Transaction(id="txn_1", status="success", amount=100)
    db.add(txn)
    db.commit()
    
    service = get_refund_service(db)
    res = service.initiate_refund("txn_1", "key_1")
    assert res["status"] in ["REFUND_PROCESSING", "REFUNDED"]
    
    db.refresh(txn)
    assert txn.refund_status == res["status"]
    
    audit = db.query(AuditLog).filter(AuditLog.transaction_id == "txn_1").all()
    assert len(audit) == 2 # REFUND_REQUESTED and then processing/refunded
