from typing import Dict, Any, Protocol
from sqlalchemy.orm import Session

class GatewayInterface(Protocol):
    """
    Defines the required capabilities for a payment gateway adapter.
    Implementations must handle execution, verification, and refunds.
    """
    def execute_recovery_action(
        self, 
        db: Session, 
        transaction_id: str, 
        action: str, 
        idempotency_key: str, 
        attempt_id: str
    ) -> Dict[str, Any]:
        """
        Executes a safe, idempotent action against the payment gateway.
        Returns a dictionary containing 'status', 'idempotent_replay', 'external_reference', 'result_message'.
        """
        ...

    def verify_transaction_state(self, db: Session, transaction_id: str, attempt_id: str) -> str:
        """
        Verifies the current ground-truth state of a transaction with the gateway.
        Returns a status string like 'SUCCEEDED', 'FAILED', 'UNKNOWN', 'ESCALATED'.
        """
        ...

    def process_refund(self, db: Session, transaction_id: str, idempotency_key: str) -> Dict[str, Any]:
        """
        Initiates a refund for a previously captured transaction.
        Returns a dictionary containing 'status', 'idempotent_replay', 'external_reference', 'result_message'.
        """
        ...

    def verify_refund(self, db: Session, transaction_id: str) -> str:
        """
        Verifies the ground-truth state of a refund with the gateway.
        Returns a status string: 'REFUNDED', 'REFUND_FAILED', or 'REFUND_UNKNOWN'.
        """
        ...

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """
        Verifies the cryptographic signature of an incoming webhook payload.
        """
        ...
