import logging
from sqlalchemy.orm import Session
from app.models.db_models import Transaction, RecoveryAttempt
from app.gateways.base import GatewayInterface
from app.gateways import get_gateway
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Explicitly allowed financial actions that can reach the gateway
ALLOWED_FINANCIAL_ACTIONS = {"RETRY_PAYMENT"}

class ExecutionGuard:
    def __init__(self, db: Session, gateway: GatewayInterface):
        self.db = db
        self.gateway = gateway
        
    def execute(self, transaction_id: str, attempt_id: str, action: str, idempotency_key: str, retry_count: int) -> Dict[str, Any]:
        """
        The absolute boundary before calling a financial gateway.
        Fails closed on any invariant violation.
        """
        logger.info(f"ExecutionGuard analyzing execution request for {transaction_id}, action: {action}")
        
        # 1. Action Allowlist Check
        if action not in ALLOWED_FINANCIAL_ACTIONS:
            logger.error(f"ExecutionGuard blocked execution: '{action}' is not an authorized financial operation.")
            return {"status": "FAILED", "result_message": f"ExecutionGuard blocked: '{action}' not allowed."}
            
        # 2. Attempt Existence & Association Check
        attempt = self.db.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).first()
        if not attempt:
            logger.error(f"ExecutionGuard blocked execution: Attempt {attempt_id} does not exist.")
            return {"status": "FAILED", "result_message": "ExecutionGuard blocked: Attempt not found."}
            
        if attempt.transaction_id != transaction_id:
            logger.error(f"ExecutionGuard blocked execution: Attempt {attempt_id} does not belong to transaction {transaction_id}.")
            return {"status": "FAILED", "result_message": "ExecutionGuard blocked: Transaction mismatch."}
            
        # 3. Transaction Existence Check
        txn = self.db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn:
            logger.error(f"ExecutionGuard blocked execution: Transaction {transaction_id} does not exist.")
            return {"status": "FAILED", "result_message": "ExecutionGuard blocked: Transaction not found."}
            
        # 4. State Check
        if attempt.outcome_status != "AUTHORIZED":
            logger.error(f"ExecutionGuard blocked execution: Attempt {attempt_id} is in state {attempt.outcome_status}, expected AUTHORIZED.")
            return {"status": "FAILED", "result_message": "ExecutionGuard blocked: Not in AUTHORIZED state."}
            
        # 5. Terminal State & Replay Check (Crash-safe boundary)
        if txn.recovery_status in ["SUCCEEDED"]:
            logger.error(f"ExecutionGuard blocked execution: Transaction {transaction_id} is in a terminal recovery state: {txn.recovery_status}.")
            return {"status": "FAILED", "result_message": f"ExecutionGuard blocked: Transaction already terminal ({txn.recovery_status})."}
            
        # Instead of just checking txn.recovery_status (which might not be written if a crash occurs post-gateway),
        # we inspect ALL attempts for this transaction to see if ANY execution could have started/finished.
        existing_attempts = self.db.query(RecoveryAttempt).filter(RecoveryAttempt.transaction_id == transaction_id).all()
        
        # Deny-by-default: only states that provably guarantee no gateway execution are allowed
        SAFE_RETRY_STATES = {"PENDING", "AUTHORIZED", "STOPPED", "WAITING", "AWAITING_CUSTOMER"}
        
        for existing in existing_attempts:
            if existing.id != attempt_id:
                if existing.outcome_status not in SAFE_RETRY_STATES:
                    logger.error(f"ExecutionGuard blocked execution: Transaction {transaction_id} already has attempt {existing.id} in state {existing.outcome_status}.")
                    return {"status": "FAILED", "result_message": f"ExecutionGuard blocked: Conflicting attempt {existing.id} in state {existing.outcome_status}."}

        # 6. Execute via Gateway
        logger.info(f"ExecutionGuard invariants passed. Passing to gateway for {transaction_id}.")
        try:
            # We pass the idempotency key down. The gateway handles the DB-level idempotency record.
            result = self.gateway.execute_recovery_action(
                self.db, 
                transaction_id, 
                action, 
                idempotency_key, 
                attempt_id
            )
            return result
        except Exception as e:
            logger.error(f"ExecutionGuard caught exception during gateway execution: {e}")
            return {"status": "FAILED", "result_message": "ExecutionGuard caught gateway exception."}

def get_execution_guard(db: Session, gateway: GatewayInterface = None) -> ExecutionGuard:
    if not gateway:
        gateway = get_gateway()
    return ExecutionGuard(db, gateway)
