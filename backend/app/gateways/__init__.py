from app.gateways.base import GatewayInterface
from app.config import settings

# Provide a configured instance for the application to use
def get_gateway() -> GatewayInterface:
    if settings.PAYMENT_PROVIDER == "razorpay":
        from app.gateways.razorpay_gateway import RazorpayGateway
        return RazorpayGateway()
        
    if settings.PAYMENT_PROVIDER == "mock":
        from app.services.razorpay_mock import MockGateway
        return MockGateway()
        
    raise ValueError(f"CONFIGURATION ERROR: Unknown PAYMENT_PROVIDER '{settings.PAYMENT_PROVIDER}'")
