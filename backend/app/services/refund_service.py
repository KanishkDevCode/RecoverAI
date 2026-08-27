import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models.db_models import Transaction, AuditLog
from app.gateways.base import GatewayInterface
from app.gateways import get_gateway

logger = logging.getLogger(__name__)

class RefundService:
    def __init__(self, db: Session, gateway: GatewayInterface = None):
        self.db = db
        self.gateway = gateway or get_gateway()
        
    def initiate_refund(self, transaction_id: str, idempotency_key: str) -> Dict[str, Any]:
        """
        Validates the transaction state and initiates a refund securely.
        """
        # 1. Validation with Row-level Lock
        txn = self.db.query(Transaction).filter(Transaction.id == transaction_id).with_for_update().first()
        if not txn:
            logger.error(f"RefundService: Transaction {transaction_id} not found")
            return {"status": "FAILED", "result_message": "Transaction not found"}
            
        if txn.status != "success" and txn.recovery_status != "SUCCEEDED":
            logger.error(f"RefundService: Transaction {transaction_id} not eligible for refund. Status: {txn.status}, Recovery: {txn.recovery_status}")
            return {"status": "FAILED", "result_message": "Only successfully captured payments can be refunded"}
            
        if txn.refund_status in ["REFUND_REQUESTED", "REFUND_PROCESSING", "REFUNDED"]:
            logger.warning(f"RefundService: Transaction {transaction_id} refund already in progress or completed.")
            return {"status": "FAILED", "result_message": f"Refund already in progress or completed (status: {txn.refund_status})"}
            
        # 2. State Transition: REQUESTED
        old_status = txn.refund_status
        
        # Optimistic concurrency check (since SQLite ignores with_for_update)
        updated_rows = self.db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.refund_status == old_status
        ).update({
            "refund_status": "REFUND_REQUESTED",
            "refund_amount": txn.amount
        })
        
        if updated_rows == 0:
            self.db.rollback()
            logger.warning(f"RefundService: Concurrency collision for {transaction_id}. Refund already initiated by another thread.")
            return {"status": "FAILED", "result_message": "Refund already in progress (concurrency conflict)"}
            
        self.db.commit()
        self._audit(transaction_id, old_status, "REFUND_REQUESTED", "Refund initiated by user")
        
        # 3. Gateway Call
        try:
            result = self.gateway.process_refund(self.db, transaction_id, idempotency_key)
            status = result.get("status", "FAILED")
            
            # Map gateway status to our internal states
            # We don't blind-set REFUNDED unless the gateway actually says so immediately, 
            # usually it is REFUND_PROCESSING.
            new_status = status
            if status == "SUCCEEDED":
                new_status = "REFUNDED"
            elif status == "FAILED":
                new_status = "REFUND_FAILED"
                
            txn.refund_status = new_status
            self.db.commit()
            
            self._audit(transaction_id, "REFUND_REQUESTED", new_status, result.get("result_message", "Gateway response"))
            
            return {
                "transaction_id": transaction_id,
                "status": new_status,
                "idempotent_replay": result.get("idempotent_replay", False),
                "external_reference": result.get("external_reference"),
                "result_message": result.get("result_message")
            }
            
        except Exception as e:
            logger.error(f"RefundService: Error processing refund for {transaction_id}: {e}")
            txn.refund_status = "REFUND_FAILED"
            self.db.commit()
            self._audit(transaction_id, "REFUND_REQUESTED", "REFUND_FAILED", f"System error: {str(e)}")
            return {"status": "REFUND_FAILED", "result_message": "System error during gateway call"}
            
    def _audit(self, transaction_id: str, old_state: str, new_state: str, reason: str):
        audit = AuditLog(
            transaction_id=transaction_id,
            event_type="REFUND_STATE_CHANGE",
            previous_state=old_state,
            new_state=new_state,
            reasoning=reason
        )
        self.db.add(audit)
        self.db.commit()

def get_refund_service(db: Session) -> RefundService:
    return RefundService(db)
