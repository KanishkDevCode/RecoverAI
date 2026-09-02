import pytest
from app.services.webhook_parser import normalize_webhook_payload

def test_parse_razorpay_payment_failed():
    payload = {
        "entity": "event",
        "account_id": "acc_xyz",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_failed123",
                    "amount": 1000,
                    "currency": "INR",
                    "status": "failed"
                }
            }
        },
        "created_at": 1400826750
    }
    headers = {"X-Razorpay-Event-Id": "ev_failed123"}
    
    result = normalize_webhook_payload(payload, headers)
    assert result["event_id"] == "ev_failed123"
    assert result["event_type"] == "payment.failed"
    assert result["gateway_payment_id"] == "pay_failed123"
    assert result["gateway_refund_id"] is None
    assert result["provider"] == "razorpay"

def test_parse_razorpay_payment_captured():
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_captured123"
                }
            }
        }
    }
    headers = {"x-razorpay-event-id": "ev_captured123"} # lowercase header test
    
    result = normalize_webhook_payload(payload, headers)
    assert result["event_id"] == "ev_captured123"
    assert result["event_type"] == "payment.captured"
    assert result["gateway_payment_id"] == "pay_captured123"
    assert result["provider"] == "razorpay"

def test_parse_razorpay_refund_created():
    payload = {
        "event": "refund.created",
        "payload": {
            "refund": {
                "entity": {
                    "id": "rfnd_123",
                    "payment_id": "pay_refunded123"
                }
            }
        }
    }
    headers = {"X-Razorpay-Event-Id": "ev_refund123"}
    
    result = normalize_webhook_payload(payload, headers)
    assert result["event_id"] == "ev_refund123"
    assert result["event_type"] == "refund.created"
    assert result["gateway_payment_id"] == "pay_refunded123"
    assert result["gateway_refund_id"] == "rfnd_123"
    assert result["provider"] == "razorpay"

def test_parse_legacy_mock_payload():
    payload = {
        "event_id": "mock_ev_123",
        "event_type": "refund.completed",
        "gateway_payment_id": "pay_mock123",
        "gateway_refund_id": "rfnd_mock123",
        "transaction_id": "txn_12345"
    }
    headers = {}
    
    result = normalize_webhook_payload(payload, headers)
    assert result["event_id"] == "mock_ev_123"
    assert result["event_type"] == "refund.completed"
    assert result["gateway_payment_id"] == "pay_mock123"
    assert result["gateway_refund_id"] == "rfnd_mock123"
    assert result["transaction_id"] == "txn_12345"
    assert result["provider"] == "mock"

def test_parse_razorpay_missing_nested_fields_safely():
    payload = {
        "event": "unknown_event"
        # missing payload -> payment -> entity
    }
    headers = {"X-Razorpay-Event-Id": "ev_unknown"}
    
    result = normalize_webhook_payload(payload, headers)
    assert result["event_id"] == "ev_unknown"
    assert result["event_type"] == "unknown_event"
    assert result["gateway_payment_id"] is None
    assert result["gateway_refund_id"] is None
