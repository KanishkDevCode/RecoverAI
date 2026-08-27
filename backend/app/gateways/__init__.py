from app.gateways.base import GatewayInterface
from app.services.razorpay_mock import MockGateway

# Provide a configured instance for the application to use
def get_gateway() -> GatewayInterface:
    return MockGateway()
