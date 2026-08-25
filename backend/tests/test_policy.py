import pytest
from app.policy.rules import evaluate_policy
from app.schemas.transaction import TransactionIncoming

def get_base_txn(txn_id: str, amount: float, failure_code: str = "insufficient_funds") -> TransactionIncoming:
    return TransactionIncoming(**{
        "id": txn_id,
        "customer_id": "cust_1",
        "amount": amount,
        "payment_status": "failed",
        "failure_code": failure_code
    })

def test_1_low_risk_low_value():
    # ml=0.9 (LOW_RISK), amount=100 (SMALL) -> max action RETRY_PAYMENT
    txn = get_base_txn("txn_1", 100.0)
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.9)
    assert allowed is True
    assert action == "RETRY_PAYMENT"

def test_2_low_risk_high_value():
    # ml=0.9 (LOW_RISK), amount=6000 (LARGE) -> max action CREATE_ESCALATION
    txn = get_base_txn("txn_2", 6000.0)
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.9)
    assert allowed is False
    assert action == "CREATE_ESCALATION"

def test_3_medium_risk_bounded():
    # ml=0.3 (MEDIUM_RISK), amount=500 (SMALL) -> max action WAIT_AND_RETRY
    txn = get_base_txn("txn_3", 500.0)
    # If agent requests RETRY_PAYMENT, it is denied and bounded to WAIT_AND_RETRY
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.3)
    assert allowed is False
    assert action == "WAIT_AND_RETRY"

def test_4_fraud_stopped():
    # failure_code = fraud_suspected -> PERMANENT_FRAUD -> max action STOP_AUTOMATION
    txn = get_base_txn("txn_4", 100.0, failure_code="fraud_suspected")
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.9)
    assert allowed is False
    assert action == "STOP_AUTOMATION"

def test_5_permanent_failure_stopped():
    # failure_code = limit_exceeded -> PERMANENT_FRAUD -> max action STOP_AUTOMATION
    txn = get_base_txn("txn_5", 100.0, failure_code="limit_exceeded")
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.9)
    assert allowed is False
    assert action == "STOP_AUTOMATION"

def test_6_retry_limit_exceeded():
    # retry_count >= 2 -> max action STOP_AUTOMATION (for small)
    txn = get_base_txn("txn_6", 100.0)
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.9, current_retry_count=2)
    assert allowed is False
    assert action == "STOP_AUTOMATION"

def test_7_unknown_no_blind_retry():
    # If ML prob is default 0.0 (High Risk), small amount -> max SEND_RECOVERY_MESSAGE
    txn = get_base_txn("txn_7", 100.0)
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.0)
    assert allowed is False
    assert action == "SEND_RECOVERY_MESSAGE"

def test_8_high_value_escalation():
    # High value > 5000 is always escalation
    txn = get_base_txn("txn_8", 10000.0)
    allowed, action, reason = evaluate_policy(txn, agent_action="WAIT_AND_RETRY", ml_probability=0.9)
    assert allowed is False
    assert action == "CREATE_ESCALATION"

def test_9_invalid_ai_recommendation():
    # Unknown agent action
    txn = get_base_txn("txn_9", 100.0)
    allowed, action, reason = evaluate_policy(txn, agent_action="INITIATE_REFUND_NOW", ml_probability=0.9)
    assert allowed is False
    assert action == "RETRY_PAYMENT"  # Bounded to max allowed for this tier

def test_10_deterministic_identical_result():
    txn = get_base_txn("txn_10", 2000.0)
    # Medium risk, medium amount -> max action SEND_RECOVERY_MESSAGE
    res1 = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.3)
    res2 = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.3)
    assert res1 == res2
    assert res1[1] == "SEND_RECOVERY_MESSAGE"

def test_11_policy_cannot_be_bypassed_by_ml():
    # If fraud, high ML prob shouldn't override it
    txn = get_base_txn("txn_11", 100.0, failure_code="fraud_suspected")
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.99)
    assert allowed is False
    assert action == "STOP_AUTOMATION"

def test_12_prompt_injection_safety():
    # LLM recommends aggressive action due to prompt injection
    txn = get_base_txn("txn_12", 2000.0, failure_code="fraud_suspected")
    allowed, action, reason = evaluate_policy(txn, agent_action="RETRY_PAYMENT", ml_probability=0.99)
    assert allowed is False
    assert action == "STOP_AUTOMATION"
