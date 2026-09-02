import logging
import razorpay
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.gateways.base import GatewayInterface
from app.models.db_models import Transaction, IdempotencyRecord, RecoveryAttempt
from app.services.state_machine import transition_recovery_attempt

logger = logging.getLogger(__name__)

class RazorpayGateway(GatewayInterface):
    """
    Real integration with Razorpay Test Mode.
    Strictly sanitizes errors and never logs credentials.
    """
    def __init__(self):
        # Lazy initialization of credentials
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        if not self.key_id or not self.key_secret:
            raise ValueError("CONFIGURATION ERROR: RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are required for RazorpayGateway.")
        
        # Instantiate the official SDK client
        self.client = razorpay.Client(auth=(self.key_id, self.key_secret))

    def _sanitize_error(self, e: Exception) -> str:
        """Removes any sensitive data from the exception message."""
        err_msg = str(e)
        if self.key_id and self.key_id in err_msg:
            err_msg = err_msg.replace(self.key_id, "***")
        if self.key_secret and self.key_secret in err_msg:
            err_msg = err_msg.replace(self.key_secret, "***")
        return f"gateway_error: {err_msg}"

    def execute_recovery_action(
        self, 
        db: Session, 
        transaction_id: str, 
        action: str, 
        idempotency_key: str, 
        attempt_id: str
    ) -> Dict[str, Any]:
        
        logger.info(f"RazorpayGateway: Preparing action {action} for {transaction_id}")
        
        # 1. Idempotency Check
        try:
            new_record = IdempotencyRecord(key=idempotency_key, attempt_id=attempt_id, status="PENDING")
            db.add(new_record)
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == idempotency_key).first()
            if not existing_record or not existing_record.attempt_id:
                return {"status": "FAILED", "idempotent_replay": True, "result_message": "Duplicate key error but record missing"}
            
            existing_attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == existing_record.attempt_id).first()
            if not existing_attempt:
                return {"status": "FAILED", "idempotent_replay": True, "result_message": "Duplicate key error but attempt missing"}
                
            return {
                "status": existing_attempt.outcome_status,
                "idempotent_replay": True,
                "external_reference": existing_record.external_reference,
                "result_message": existing_record.result_message
            }

        # 2. Setup
        transition_recovery_attempt(db, attempt_id, "EXECUTING", reason="Initiating real gateway call")
        record_to_update = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == idempotency_key).first()
        status = "FAILED"
        ext_ref = None
        result_msg = None

        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn:
            status = "FAILED"
            result_msg = "Transaction not found."
            transition_recovery_attempt(db, attempt_id, status, reason=result_msg)
            if record_to_update:
                record_to_update.status = status
                record_to_update.result_message = result_msg
                db.commit()
            return {"status": status, "idempotent_replay": False, "external_reference": None, "result_message": result_msg}

        # 3. Action Mapping
        try:
            if action == "WAIT_AND_RETRY":
                # Real Razorpay cannot 'retry' a failed payment. 
                # We fetch status to see if it eventually succeeded (late auth).
                if getattr(txn, 'gateway_payment_id', None):
                    payment = self.client.payment.fetch(txn.gateway_payment_id)
                    rp_status = payment.get('status')
                    if rp_status == 'captured':
                        status = "SUCCEEDED"
                        result_msg = "Late auth captured successfully."
                        ext_ref = txn.gateway_payment_id
                    else:
                        status = "FAILED"
                        result_msg = f"Payment status remains: {rp_status}"
                else:
                    status = "FAILED"
                    result_msg = "No gateway_payment_id available to verify."

            elif action == "SEND_RECOVERY_MESSAGE":
                # Generate a Razorpay Payment Link
                pl_data = {
                    "amount": int(txn.amount * 100), # minor units expected by razorpay
                    "currency": txn.currency,
                    "accept_partial": False,
                    "description": f"Recovery for failed transaction {transaction_id}",
                    "notify": {
                        "sms": True,
                        "email": True
                    },
                    "reminder_enable": True
                }
                
                link = self.client.payment_link.create(pl_data)
                ext_ref = link.get('id')
                status = "AWAITING_CUSTOMER"
                result_msg = "Payment link generated successfully."

            elif action == "CREATE_ESCALATION":
                status = "ESCALATED"
                result_msg = "Internal escalation created. No gateway action taken."

            elif action == "RETRY_PAYMENT":
                # Explicitly blocking blind retry mapping
                status = "FAILED"
                result_msg = "RETRY_PAYMENT is unsupported for real Razorpay. Cannot blindly retry."

            else:
                status = "FAILED"
                result_msg = f"Unknown action mapping: {action}"

            transition_recovery_attempt(db, attempt_id, status, reason=result_msg)
            
        except razorpay.errors.ServerError as e:
            logger.error("Razorpay Server Error")
            status = "UNKNOWN"
            result_msg = self._sanitize_error(e)
            transition_recovery_attempt(db, attempt_id, status, reason=result_msg)
        except Exception as e:
            logger.error("Razorpay SDK Error")
            status = "FAILED"
            result_msg = self._sanitize_error(e)
            transition_recovery_attempt(db, attempt_id, status, reason=result_msg)

        # 4. Update the record
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
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn or not getattr(txn, 'gateway_payment_id', None):
            return "UNKNOWN"
            
        transition_recovery_attempt(db, attempt_id, "VERIFYING", reason="Initiating gateway verification query")
        try:
            payment = self.client.payment.fetch(txn.gateway_payment_id)
            rp_status = payment.get('status')
            
            if rp_status == 'captured':
                transition_recovery_attempt(db, attempt_id, "SUCCEEDED", reason="Gateway confirmed success")
                return "SUCCEEDED"
            elif rp_status in ['failed', 'created']:
                transition_recovery_attempt(db, attempt_id, "FAILED", reason=f"Gateway confirmed status: {rp_status}")
                return "FAILED"
            else:
                return "UNKNOWN"
        except Exception as e:
            transition_recovery_attempt(db, attempt_id, "UNKNOWN", reason=self._sanitize_error(e))
            return "UNKNOWN"

    def process_refund(self, db: Session, transaction_id: str, idempotency_key: str) -> Dict[str, Any]:
        logger.info(f"RazorpayGateway: Preparing refund for {transaction_id}")
        
        # 1. Idempotency Check
        try:
            new_record = IdempotencyRecord(key=idempotency_key, status="PENDING")
            db.add(new_record)
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == idempotency_key).first()
            if not existing_record:
                return {"status": "FAILED", "idempotent_replay": True, "result_message": "Duplicate key error but record missing"}
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

        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        
        try:
            if not txn or not getattr(txn, 'gateway_payment_id', None):
                raise ValueError("Transaction missing gateway_payment_id")
                
            refund_data = {
                "amount": int(txn.amount * 100),
                "receipt": idempotency_key
            }
            refund = self.client.payment.refund(txn.gateway_payment_id, refund_data)
            
            ext_ref = refund.get('id')
            rp_status = refund.get('status') # usually 'processed'
            
            if rp_status == 'processed':
                status = "SUCCEEDED"
                result_msg = "Refund successfully completed."
            else:
                status = "FAILED"
                result_msg = f"Refund status: {rp_status}"
                
        except Exception as e:
            logger.error("Razorpay Refund Error")
            status = "FAILED"
            result_msg = self._sanitize_error(e)

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
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn or not getattr(txn, 'gateway_refund_id', None):
            return "REFUND_UNKNOWN"
            
        try:
            refund = self.client.refund.fetch(txn.gateway_refund_id)
            rp_status = refund.get('status')
            if rp_status == 'processed':
                return "REFUNDED"
            elif rp_status == 'failed':
                return "REFUND_FAILED"
            return "REFUND_UNKNOWN"
        except Exception:
            return "REFUND_UNKNOWN"

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        try:
            return self.client.utility.verify_webhook_signature(payload.decode('utf-8'), signature, secret)
        except Exception as e:
            logger.error(f"Signature verification error: {self._sanitize_error(e)}")
            return False
