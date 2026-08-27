import logging
import time
import hmac
import hashlib
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.db_models import IdempotencyRecord
from app.gateways.base import GatewayInterface

logger = logging.getLogger(__name__)

class MockGateway(GatewayInterface):
    """
    A mock wrapper simulating the external Razorpay SDK.
    In a real environment, this connects to Razorpay Test Mode APIs.
    """
    
    def __init__(self):
        pass

    def execute_recovery_action(self, db: Session, transaction_id: str, action: str, idempotency_key: str, attempt_id: str) -> Dict[str, Any]:
        """
        Executes a safe, idempotent action against the payment gateway.
        """
        from app.services.state_machine import transition_recovery_attempt
        from app.models.db_models import RecoveryAttempt
        
        logger.info(f"Preparing to execute {action} on {transaction_id} using key {idempotency_key}")
        
        # 0. Gateway Defense in Depth: Explicit Action Allowlist
        if action != "RETRY_PAYMENT":
            logger.error(f"Gateway rejected unsupported financial action: {action}")
            return {"status": "FAILED", "idempotent_replay": False, "result_message": f"Gateway rejected unsupported action: {action}"}
            
        # 1. Persistent Idempotency Check using Database Constraint
        try:
            new_record = IdempotencyRecord(key=idempotency_key, attempt_id=attempt_id, status="PENDING")
            db.add(new_record)
            db.commit()
        except IntegrityError:
            # Idempotency key already exists.
            db.rollback()
            existing_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == idempotency_key).first()
            if not existing_record or not existing_record.attempt_id:
                return {"status": "FAILED", "idempotent_replay": True, "result_message": "Duplicate key error but record missing"}
            
            existing_attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == existing_record.attempt_id).first()
            if not existing_attempt:
                return {"status": "FAILED", "idempotent_replay": True, "result_message": "Duplicate key error but attempt missing"}
                
            logger.warning(f"Idempotency hit! Action {action} with key {idempotency_key} already exists with status {existing_attempt.outcome_status}.")
            return {
                "status": existing_attempt.outcome_status,
                "idempotent_replay": True,
                "external_reference": existing_record.external_reference,
                "result_message": existing_record.result_message
            }
            
        # 2. Transition to EXECUTING
        transition_recovery_attempt(db, attempt_id, "EXECUTING", reason="Initiating external gateway call")
        record_to_update = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == idempotency_key).first()
        status = "FAILED"
        ext_ref = None
        result_msg = None
        
        try:
            # Simulate network latency
            time.sleep(0.1)
            
            # For realistic evaluation, we check the ground truth of the synthetic transaction.
            from app.services.feature_store import feature_store
            features = feature_store.get_features(transaction_id)
            is_recoverable = True
            if features and 'ground_truth_recoverable' in features:
                is_recoverable = features['ground_truth_recoverable']
            
            if "timeout" in transaction_id:
                raise TimeoutError("Simulated gateway timeout")
            elif "explicit_fail" in transaction_id or not is_recoverable:
                raise ValueError("Simulated explicit gateway rejection (Insufficient Funds / Hard Decline)")
            
            if action == "RETRY_PAYMENT":
                import uuid
                ext_ref = f"pay_mock_{int(time.time())}_{uuid.uuid4().hex[:4]}"
                result_msg = "RETRY_PAYMENT successful."
                status = "SUCCEEDED"
            else:
                result_msg = f"Unknown action type: {action}"
                status = "FAILED"
                
            transition_recovery_attempt(db, attempt_id, status, reason=result_msg)
            
        except TimeoutError as e:
            logger.error(f"External API timeout: {e}")
            status = "UNKNOWN"
            result_msg = f"timeout_error: {str(e)}"
            transition_recovery_attempt(db, attempt_id, status, reason=result_msg)
        except Exception as e:
            logger.error(f"External API explicitly failed: {e}")
            status = "FAILED"
            result_msg = f"api_error: {str(e)}"
            transition_recovery_attempt(db, attempt_id, status, reason=result_msg)
            
        # 3. Update the record
        if record_to_update:
            record_to_update.status = status
            record_to_update.external_reference = ext_ref
            record_to_update.result_message = result_msg
            db.commit()
        
        return {
            "status": status,
            "idempotent_replay": False,
            "external_reference": ext_ref,
            "result_message": result_msg
        }

    def verify_transaction_state(self, db: Session, transaction_id: str, attempt_id: str) -> str:
        """
        Mock method to verify an UNKNOWN transaction state.
        """
        from app.services.state_machine import transition_recovery_attempt
        
        transition_recovery_attempt(db, attempt_id, "VERIFYING", reason="Initiating gateway verification query")
        
        try:
            time.sleep(0.1)
            if "verify_success" in transaction_id:
                transition_recovery_attempt(db, attempt_id, "SUCCEEDED", reason="Gateway confirmed success")
                return "SUCCEEDED"
            elif "verify_fail" in transaction_id:
                transition_recovery_attempt(db, attempt_id, "FAILED", reason="Gateway confirmed failure")
                return "FAILED"
            elif "verify_unavailable" in transaction_id:
                transition_recovery_attempt(db, attempt_id, "UNKNOWN", reason="Gateway unreachable during verification")
                return "UNKNOWN"
            else:
                transition_recovery_attempt(db, attempt_id, "ESCALATED", reason="Max verification attempts reached / escalation required")
                return "ESCALATED"
        except Exception as e:
            transition_recovery_attempt(db, attempt_id, "UNKNOWN", reason=f"Error during verification: {e}")
            return "UNKNOWN"

    def process_refund(self, db: Session, transaction_id: str, idempotency_key: str) -> Dict[str, Any]:
        """
        Mock method to process a refund, simulating async processing over time.
        """
        from app.models.db_models import Transaction
        
        logger.info(f"Preparing to refund {transaction_id} using key {idempotency_key}")
        
        # 1. Persistent Idempotency Check
        try:
            new_record = IdempotencyRecord(key=idempotency_key, status="PENDING")
            db.add(new_record)
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == idempotency_key).first()
            if not existing_record:
                return {"status": "FAILED", "idempotent_replay": True, "result_message": "Duplicate key error but record missing"}
                
            logger.warning(f"Idempotency hit! Refund with key {idempotency_key} already exists with status {existing_record.status}.")
            return {
                "status": existing_record.status,
                "idempotent_replay": True,
                "external_reference": existing_record.external_reference,
                "result_message": existing_record.result_message
            }
            
        record_to_update = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == idempotency_key).first()
        status = "FAILED"
        ext_ref = None
        result_msg = None
        
        try:
            # Simulate network latency
            time.sleep(0.1)
            
            # In a real async refund, the gateway accepts the request, returns REFUND_PROCESSING, 
            # and later fires a webhook. For our mock, we simulate returning REFUND_PROCESSING initially,
            # but since this is a synchronous mock simulator without a separate background worker for webhooks,
            # we'll still use the mock delay, but we'll fulfill it.
            
            ext_ref = f"refund_mock_{int(time.time())}"
            result_msg = "Refund successfully initiated and processed."
            status = "REFUND_PROCESSING"
            
        except Exception as e:
            logger.error(f"External API explicitly failed during refund: {e}")
            status = "FAILED"
            result_msg = f"api_error: {str(e)}"
            
        # 3. Update the record
        if record_to_update:
            record_to_update.status = status
            record_to_update.external_reference = ext_ref
            record_to_update.result_message = result_msg
            db.commit()
        
        return {
            "status": status,
            "idempotent_replay": False,
            "external_reference": ext_ref,
            "result_message": result_msg
        }

    def verify_refund(self, db: Session, transaction_id: str) -> str:
        """
        Mock method to verify the ground-truth state of a refund with the gateway.
        """
        try:
            time.sleep(0.1)
            # Deterministic mock verification based on transaction_id content
            if "verify_refund_success" in transaction_id:
                return "REFUNDED"
            elif "verify_refund_fail" in transaction_id:
                return "REFUND_FAILED"
            elif "verify_refund_unavailable" in transaction_id:
                return "REFUND_UNKNOWN"
            else:
                # Default for mock: Assume it succeeded if we reach here without special flags
                return "REFUNDED"
        except Exception as e:
            logger.error(f"Error during mock refund verification: {e}")
            return "REFUND_UNKNOWN"

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """
        Mock method for verifying webhook HMAC-SHA256 signatures.
        """
        try:
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False

# Legacy export for backwards compatibility until refactor is complete
razorpay_service = MockGateway()
