import os
import pytest
import concurrent.futures
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db_models import IdempotencyRecord
from app.services.razorpay_mock import RazorpayMockService

# Use a file-based SQLite DB to allow cross-thread access during concurrent tests
TEST_DB_URL = "sqlite:///./test_idempotency.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_idempotency.db"):
        try:
            os.remove("./test_idempotency.db")
        except:
            pass

def execute_with_new_session(transaction_id, action, key, attempt_id=None):
    service = RazorpayMockService()
    session = TestingSessionLocal()
    import uuid
    from app.models.db_models import RecoveryAttempt
    
    try:
        if not attempt_id:
            attempt_id = f"att_test_{uuid.uuid4().hex[:8]}"
            attempt = RecoveryAttempt(id=attempt_id, transaction_id=transaction_id, outcome_status="AUTHORIZED")
            session.add(attempt)
            session.commit()
            
        return service.execute_recovery_action(session, transaction_id, action, key, attempt_id)
    finally:
        session.close()

def test_sequential_duplicate_request():
    key = "idem_seq_1"
    
    # First request
    res1 = execute_with_new_session("txn_1", "RETRY_PAYMENT", key)
    assert res1["status"] == "SUCCEEDED"
    assert res1["idempotent_replay"] is False
    
    # Second request
    res2 = execute_with_new_session("txn_1", "RETRY_PAYMENT", key)
    assert res2["status"] == "SUCCEEDED"
    assert res2["idempotent_replay"] is True
    assert res2["external_reference"] == res1["external_reference"]

def test_different_idempotency_keys():
    res1 = execute_with_new_session("txn_2", "RETRY_PAYMENT", "key_1")
    res2 = execute_with_new_session("txn_2", "WAIT_AND_RETRY", "key_2")
    
    assert res1["idempotent_replay"] is False
    assert res2["idempotent_replay"] is False
    assert res1["external_reference"] != res2["external_reference"]

def test_same_transaction_different_keys():
    res1 = execute_with_new_session("txn_same", "RETRY_PAYMENT", "key_a")
    res2 = execute_with_new_session("txn_same", "RETRY_PAYMENT", "key_b")
    
    assert res1["idempotent_replay"] is False
    assert res2["idempotent_replay"] is False

def test_existing_failed_operation_replay():
    key = "idem_fail_1"
    
    # First request: simulate an explicit failure
    res1 = execute_with_new_session("txn_explicit_fail", "RETRY_PAYMENT", key)
    assert res1["status"] == "FAILED"
    
    # Attempt to execute duplicate
    res2 = execute_with_new_session("txn_explicit_fail", "RETRY_PAYMENT", key)
    
    assert res2["status"] == "FAILED"
    assert res2["idempotent_replay"] is True

def test_existing_pending_operation():
    # Since execute_with_new_session is synchronous, we can't easily pause it at PENDING.
    # We will simulate it by injecting an IdempotencyRecord and RecoveryAttempt manually.
    key = "idem_pending_1"
    
    session = TestingSessionLocal()
    from app.models.db_models import RecoveryAttempt
    
    attempt = RecoveryAttempt(id="att_test_123", transaction_id="txn_4", outcome_status="PENDING")
    session.add(attempt)
    pending_record = IdempotencyRecord(key=key, attempt_id="att_test_123", status="PENDING")
    session.add(pending_record)
    session.commit()
    session.close()
    
    res = execute_with_new_session("txn_4", "RETRY_PAYMENT", key)
    
    assert res["status"] == "PENDING"
    assert res["idempotent_replay"] is True

def test_five_concurrent_identical_requests():
    key = "idem_concurrent_1"
    
    def make_request():
        return execute_with_new_session("txn_5", "RETRY_PAYMENT", key)
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request) for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    original_executions = [r for r in results if r["idempotent_replay"] is False]
    replays = [r for r in results if r["idempotent_replay"] is True]
    
    assert len(original_executions) == 1
    assert len(replays) == 4
    
    session = TestingSessionLocal()
    record_count = session.query(IdempotencyRecord).filter(IdempotencyRecord.key == key).count()
    session.close()
    
    assert record_count == 1
