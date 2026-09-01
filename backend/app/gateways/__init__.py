from app.gateways.base import GatewayInterface

# Provide a configured instance for the application to use
def get_gateway() -> GatewayInterface:
    from app.services.razorpay_mock import MockGateway
    return MockGateway()
