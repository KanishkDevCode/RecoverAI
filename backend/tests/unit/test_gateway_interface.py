from app.gateways.base import GatewayInterface
from app.gateways import get_gateway
from app.services.razorpay_mock import MockGateway

def test_gateway_implements_interface():
    # This will fail at runtime if the mock doesn't implement the methods properly
    # though Python typing.Protocol only checks type hints if using mypy.
    # We can at least check if methods exist.
    gateway: GatewayInterface = get_gateway()
    
    assert hasattr(gateway, "execute_recovery_action")
    assert hasattr(gateway, "verify_transaction_state")
    assert hasattr(gateway, "process_refund")
    assert hasattr(gateway, "verify_refund")
    assert hasattr(gateway, "verify_webhook_signature")

def test_mock_gateway_signature():
    gateway = get_gateway()
    payload = b'{"test":"data"}'
    secret = "secret123"
    
    import hmac
    import hashlib
    valid_signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    assert gateway.verify_webhook_signature(payload, valid_signature, secret) is True
    assert gateway.verify_webhook_signature(payload, "invalid", secret) is False
