import pytest
from unittest.mock import patch, MagicMock
from app.gateways.razorpay_gateway import RazorpayGateway
from app.gateways import get_gateway
from app.config import settings
from sqlalchemy.orm import Session
from app.models.db_models import Transaction, RecoveryAttempt, IdempotencyRecord
import razorpay

@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "test_id")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "test_secret")

@pytest.fixture
def db_session():
    # Simple mock session for DB
    return MagicMock(spec=Session)

def test_lazy_credential_validation(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    
    with pytest.raises(ValueError, match="RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are required"):
        RazorpayGateway()

def test_gateway_factory_selection_razorpay(mock_settings):
    gateway = get_gateway()
    assert isinstance(gateway, RazorpayGateway)

def test_gateway_factory_selection_mock(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "mock")
    from app.services.razorpay_mock import MockGateway
    gateway = get_gateway()
    assert isinstance(gateway, MockGateway)

def test_gateway_factory_selection_unknown(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "unknown_provider")
    with pytest.raises(ValueError, match="Unknown PAYMENT_PROVIDER"):
        get_gateway()

@patch('app.gateways.razorpay_gateway.transition_recovery_attempt')
@patch('razorpay.Client')
def test_execute_recovery_wait_and_retry(mock_client, mock_transition, mock_settings, db_session):
    mock_sdk = MagicMock()
    mock_client.return_value = mock_sdk
    
    # Mock payment fetch
    mock_sdk.payment.fetch.return_value = {"status": "captured"}
    
    gateway = RazorpayGateway()
    
    # Mock db interactions
    db_session.query().filter().first.side_effect = [
        None, # Idempotency record to update
        MagicMock(id="txn_123", gateway_payment_id="pay_123") # Transaction
    ]
    
    res = gateway.execute_recovery_action(db_session, "txn_123", "WAIT_AND_RETRY", "idem_1", "att_1")
    assert res["status"] == "SUCCEEDED"
    assert res["external_reference"] == "pay_123"

@patch('app.gateways.razorpay_gateway.transition_recovery_attempt')
@patch('razorpay.Client')
def test_execute_recovery_send_message(mock_client, mock_transition, mock_settings, db_session):
    mock_sdk = MagicMock()
    mock_client.return_value = mock_sdk
    
    mock_sdk.payment_link.create.return_value = {"id": "plink_123"}
    
    gateway = RazorpayGateway()
    db_session.query().filter().first.side_effect = [
        None,
        MagicMock(id="txn_123", amount=100.0, currency="INR")
    ]
    
    res = gateway.execute_recovery_action(db_session, "txn_123", "SEND_RECOVERY_MESSAGE", "idem_2", "att_2")
    assert res["status"] == "AWAITING_CUSTOMER"
    assert res["external_reference"] == "plink_123"
    
@patch('app.gateways.razorpay_gateway.transition_recovery_attempt')
@patch('razorpay.Client')
def test_sanitized_exception_handling(mock_client, mock_transition, mock_settings, db_session):
    mock_sdk = MagicMock()
    mock_client.return_value = mock_sdk
    
    mock_sdk.payment_link.create.side_effect = Exception("API error with test_id and test_secret")
    
    gateway = RazorpayGateway()
    db_session.query().filter().first.side_effect = [
        None,
        MagicMock(id="txn_123", amount=100.0, currency="INR")
    ]
    
    res = gateway.execute_recovery_action(db_session, "txn_123", "SEND_RECOVERY_MESSAGE", "idem_3", "att_3")
    assert res["status"] == "FAILED"
    # Secrets must be sanitized
    assert "test_id" not in res["result_message"]
    assert "test_secret" not in res["result_message"]
    assert "***" in res["result_message"]

@patch('razorpay.Client')
def test_process_refund(mock_client, mock_settings, db_session):
    mock_sdk = MagicMock()
    mock_client.return_value = mock_sdk
    
    mock_sdk.payment.refund.return_value = {"id": "rfnd_123", "status": "processed"}
    
    gateway = RazorpayGateway()
    
    # Needs a mock Transaction with gateway_payment_id
    mock_txn = MagicMock(id="txn_123", amount=100.0)
    mock_txn.gateway_payment_id = "pay_123"
    
    db_session.query().filter().first.side_effect = [
        None, # record to update
        mock_txn
    ]
    
    res = gateway.process_refund(db_session, "txn_123", "idem_ref")
    assert res["status"] == "SUCCEEDED"
    assert res["external_reference"] == "rfnd_123"

@patch('app.gateways.razorpay_gateway.transition_recovery_attempt')
def test_missing_payment_id_wait_and_retry(mock_transition, mock_settings, db_session):
    gateway = RazorpayGateway()
    db_session.query().filter().first.side_effect = [
        None,
        MagicMock(id="txn_123", gateway_payment_id=None) # No gateway ID
    ]
    
    res = gateway.execute_recovery_action(db_session, "txn_123", "WAIT_AND_RETRY", "idem_4", "att_4")
    assert res["status"] == "FAILED"
    assert "No gateway_payment_id" in res["result_message"]
