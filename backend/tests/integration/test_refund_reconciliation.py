import pytest
import os
from datetime import datetime, timedelta
from app.services.reconciliation import reconcile_stuck_refunds
from app.models.db_models import Transaction, AuditLog
from app.database import engine, Base
from sqlalchemy.orm import sessionmaker

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # Safe cleanup using reversed sorted_tables to respect FKs
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

def test_reconcile_stuck_refunds():
    db = TestingSessionLocal()
    os.environ["REFUND_RECONCILIATION_TIMEOUT_SECONDS"] = "0"
    
    # We use the special flags "verify_refund_success" and "verify_refund_fail" 
    # to control mock gateway verification outcome.
    
    txn_success = Transaction(
        id="txn_verify_refund_success_1", 
        status="success", 
        refund_status="REFUND_PROCESSING", 
        updated_at=datetime.utcnow() - timedelta(seconds=10),
        amount=100
    )
    
    txn_fail = Transaction(
        id="txn_verify_refund_fail_1", 
        status="success", 
        refund_status="REFUND_PROCESSING", 
        updated_at=datetime.utcnow() - timedelta(seconds=10),
        amount=100
    )
    
    db.add_all([txn_success, txn_fail])
    db.commit()
    
    reconcile_stuck_refunds(db)
    
    db.refresh(txn_success)
    db.refresh(txn_fail)
    
    assert txn_success.refund_status == "REFUNDED"
    assert txn_fail.refund_status == "REFUND_FAILED"
    
    # Verify audits
    audits_success = db.query(AuditLog).filter(AuditLog.transaction_id == txn_success.id).all()
    assert len(audits_success) == 1
    assert audits_success[0].new_state == "REFUNDED"
    
    audits_fail = db.query(AuditLog).filter(AuditLog.transaction_id == txn_fail.id).all()
    assert len(audits_fail) == 1
    assert audits_fail[0].new_state == "REFUND_FAILED"
