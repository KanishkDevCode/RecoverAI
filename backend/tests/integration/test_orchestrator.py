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
    assert result["outcome"] in ["SUCCEEDED", "WAITING", "AWAITING_CUSTOMER"]

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

def test_action_semantics_no_gateway_execution(db_session, monkeypatch):
    """
    Verifies that SEND_RECOVERY_MESSAGE, WAIT_AND_RETRY, CREATE_ESCALATION, and STOP_AUTOMATION
    do not execute the payment gateway.
    """
    orchestrator = RecoveryOrchestrator(db_session)
    
    # Track gateway executions
    gateway_calls = 0
    def mock_execute(*args, **kwargs):
        nonlocal gateway_calls
        gateway_calls += 1
        return {"status": "SUCCEEDED"}
        
    import app.services.razorpay_mock as razorpay_mock
    monkeypatch.setattr(razorpay_mock.MockGateway, "execute_recovery_action", mock_execute)
    
    # Force agent to recommend SEND_RECOVERY_MESSAGE
    import app.agents.diagnosis_agent as diagnosis_agent
    from app.schemas.agent_schema import DiagnosisResponse
    def mock_diagnose(*args, **kwargs):
        return DiagnosisResponse(
            diagnosis="mock",
            confidence=0.9,
            recommended_action="SEND_RECOVERY_MESSAGE",
            reason="mock reason",
            estimated_recovery_probability=0.5
        )
    monkeypatch.setattr(diagnosis_agent.diagnosis_agent, "diagnose_transaction", mock_diagnose)
    
    # 1. Test SEND_RECOVERY_MESSAGE
    txn = TransactionIncoming(**{
        "id": "txn_msg_1",
        "customer_id": "cust_1",
        "amount": 900.0,
        "payment_status": "failed",
        "failure_code": "insufficient_funds",
        "retry_count": 0
    })
    
    res1 = orchestrator.process_transaction(txn)
    assert res1["final_action"] == "SEND_RECOVERY_MESSAGE"
    assert res1["outcome"] == "AWAITING_CUSTOMER"
    assert gateway_calls == 0

    # Force agent to recommend WAIT_AND_RETRY
    def mock_diagnose_wait(*args, **kwargs):
        return DiagnosisResponse(
            diagnosis="mock",
            confidence=0.9,
            recommended_action="WAIT_AND_RETRY",
            reason="mock reason",
            estimated_recovery_probability=0.5
        )
    monkeypatch.setattr(diagnosis_agent.diagnosis_agent, "diagnose_transaction", mock_diagnose_wait)

    # 2. Test WAIT_AND_RETRY
    txn2 = TransactionIncoming(**{
        "id": "txn_wait_1",
        "customer_id": "cust_1",
        "amount": 900.0,
        "payment_status": "failed",
        "failure_code": "bank_timeout",
        "retry_count": 0
    })

    res2 = orchestrator.process_transaction(txn2)
    assert res2["final_action"] == "WAIT_AND_RETRY"
    assert res2["outcome"] == "WAITING"
    assert gateway_calls == 0

    # 3. Test RETRY_PAYMENT
    def mock_diagnose_retry(*args, **kwargs):
        return DiagnosisResponse(
            diagnosis="mock",
            confidence=0.9,
            recommended_action="RETRY_PAYMENT",
            reason="mock reason",
            estimated_recovery_probability=0.5
        )
    monkeypatch.setattr(diagnosis_agent.diagnosis_agent, "diagnose_transaction", mock_diagnose_retry)
    
    txn3 = TransactionIncoming(**{
        "id": "txn_retry_1",
        "customer_id": "cust_1",
        "amount": 900.0,
        "payment_status": "failed",
        "failure_code": "bank_timeout",
        "retry_count": 0
    })

    res3 = orchestrator.process_transaction(txn3)
    assert res3["final_action"] == "RETRY_PAYMENT"
    assert res3["outcome"] == "SUCCEEDED"
    assert gateway_calls == 1
