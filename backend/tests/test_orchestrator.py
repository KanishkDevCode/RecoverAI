import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.services.orchestrator import RecoveryOrchestrator
from app.schemas.transaction import TransactionIncoming

# Setup in-memory SQLite DB for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_orchestrator_full_flow_success(db_session):
    orchestrator = RecoveryOrchestrator(db_session)
    
    # Mock transaction that should be recoverable (e.g. low amount, bank timeout)
    txn = TransactionIncoming(**{
        "id": "txn_test_123",
        "customer_id": "cust_1",
        "amount": 50.0,
        "payment_status": "failed",
        "failure_code": "bank_timeout",
        "retry_count": 0
    })
    
    result = orchestrator.process_transaction(txn)
    
    assert result["transaction_id"] == "txn_test_123"
    # Agent will likely output WAIT_AND_RETRY due to mock logic for bank_timeout
    # Policy should allow it
    assert result["final_action"] in ["WAIT_AND_RETRY", "RETRY_PAYMENT", "SEND_RECOVERY_MESSAGE"]
    assert result["outcome"] == "SUCCEEDED"

def test_orchestrator_full_flow_escalation(db_session):
    orchestrator = RecoveryOrchestrator(db_session)
    
    # Mock transaction that should trigger high-value escalation
    txn = TransactionIncoming(**{
        "id": "txn_test_456",
        "customer_id": "cust_2",
        "amount": 10000.0, # Over the 5000 limit
        "payment_status": "failed",
        "failure_code": "bank_timeout",
        "retry_count": 0
    })
    
    result = orchestrator.process_transaction(txn)
    
    assert result["transaction_id"] == "txn_test_456"
    assert result["final_action"] == "CREATE_ESCALATION"
    assert result["outcome"] == "ESCALATED"
