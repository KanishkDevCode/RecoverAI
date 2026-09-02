import logging
from celery.exceptions import Ignore
from app.worker.celery_app import celery_app
from app.database import SessionLocal
from app.models.db_models import Transaction
from app.schemas.transaction import TransactionIncoming
from app.services.orchestrator import RecoveryOrchestrator
from app.services.reconciliation import (
    reconcile_orphaned_attempts,
    reconcile_unknown_attempts,
    reconcile_stuck_refunds,
    reconcile_pending_webhooks
)
from app.services.money import to_major_units

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=0)
def process_orchestrator(self, transaction_id: str):
    """
    Durable celery task to process a failed payment.
    NEVER RETRY automatically to avoid ambiguous financial execution.
    """
    logger.info(f"Celery processing orchestration for transaction {transaction_id}")
    db = SessionLocal()
    try:
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn:
            logger.error(f"Transaction {transaction_id} not found in DB.")
            return

        if txn.recovery_status != "NOT_STARTED":
            logger.warning(f"Transaction {transaction_id} already processing (status: {txn.recovery_status}).")
            return
            
        # Reconstruct TransactionIncoming
        incoming = TransactionIncoming(
            id=txn.id,
            customer_id=txn.customer_id or "unknown",
            amount=to_major_units(txn.amount),  
            currency=txn.currency,
            payment_status=txn.status,
            payment_method="card", 
            failure_code=txn.failure_code,
            failure_reason=txn.failure_reason,
            retry_count=0 
        )
        
        orchestrator = RecoveryOrchestrator(db)
        orchestrator.process_transaction(incoming)
        
    except Exception as e:
        logger.error(f"Error during Celery orchestration for {transaction_id}: {e}")
        # We do NOT retry. PostgreSQL will catch orphans in reconciliation sweep.
        raise Ignore()
    finally:
        db.close()
        db.close()

def execute_scheduled_retry(attempt_id: str):
    """
    Executes a retry safely by using the execution guard.
    """
    from app.models.db_models import RecoveryAttempt, Transaction
    from app.services.state_machine import transition_recovery_attempt
    from app.services.execution_guard import get_execution_guard
    from app.services.event_bus import event_bus
    from app.schemas.events import RecoveryEvent
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"[Recovery] Executing scheduled retry for attempt {attempt_id}")
    
    db = SessionLocal()
    try:
        attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).first()
        if not attempt:
            logger.error(f"[Recovery] Attempt {attempt_id} not found.")
            return
            
        if attempt.outcome_status != "WAITING":
            logger.warning(f"[Recovery] Attempt {attempt_id} is not WAITING (status: {attempt.outcome_status}). Skipping.")
            return
            
        txn_id = attempt.transaction_id
        final_action = attempt.executed_action
        
        # Retry count is not on the Transaction model, default to 0 for idempotency
        retry_count = 0
        
        transition_recovery_attempt(db, attempt_id, "AUTHORIZED", reason="Executing scheduled retry")
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="STATE_CHANGE",
            data={"previous_state": "WAITING", "new_state": "AUTHORIZED", "reason": "Executing scheduled retry"}
        ))
        
        idempotency_key = f"idem_{txn_id}_{final_action}_{retry_count}"
        guard = get_execution_guard(db)
        
        # Gateway expects RETRY_PAYMENT
        gateway_action = "RETRY_PAYMENT" if final_action == "WAIT_AND_RETRY" else final_action
        
        result_dict = guard.execute(txn_id, attempt_id, gateway_action, idempotency_key, retry_count)
        
        outcome_status = result_dict.get("status", "FAILED")
        external_ref = result_dict.get("external_reference") or result_dict.get("result_message")
        
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="GATEWAY_RESULT",
            data={"action_executed": final_action, "status": outcome_status, "message": external_ref}
        ))
        
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if txn:
            txn.recovery_status = outcome_status
            db.commit()
                
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="RECOVERY_COMPLETE",
            data={
                "outcome": outcome_status,
                "net_value_recovered": txn.amount if outcome_status == "SUCCEEDED" else 0.0
            }
        ))
        
    except Exception as e:
        logger.error(f"[Recovery] Error executing retry for {attempt_id}: {e}")
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=0)
def process_scheduled_retry(self, attempt_id: str):
    """
    Celery task wrapper for executing a scheduled retry.
    """
    return execute_scheduled_retry(attempt_id)


MAX_WEBHOOK_RETRIES = 3

@celery_app.task(bind=True, max_retries=0)  # We handle retries natively using our bounded logic
def process_webhook(self, event_id: str):
    """
    SAFE TO RETRY. Processes webhooks durably.
    """
    from datetime import datetime, timezone
    import json
    from app.models.db_models import WebhookEvent, AuditLog
    from app.services.webhook_parser import normalize_webhook_payload
    
    logger.info(f"Celery processing webhook {event_id}")
    db = SessionLocal()
    try:
        # Load and lock event atomically
        webhook_event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).with_for_update().first()
        if not webhook_event:
            logger.error(f"WebhookEvent {event_id} not found in DB.")
            return

        if webhook_event.processing_status in ["PROCESSED", "FAILED_PERMANENTLY"]:
            logger.info(f"Webhook {event_id} already processed or permanently failed. Exiting.")
            return
            
        if webhook_event.processing_status == "FAILED" and webhook_event.retry_count >= MAX_WEBHOOK_RETRIES:
            logger.info(f"Webhook {event_id} reached max retries. Marking FAILED_PERMANENTLY.")
            webhook_event.processing_status = "FAILED_PERMANENTLY"
            db.commit()
            return

        # Record attempt
        webhook_event.last_attempt_at = datetime.now(timezone.utc)
        db.commit()

        # Re-parse payload and normalize
        try:
            raw_payload = json.loads(webhook_event.payload)
        except json.JSONDecodeError:
            logger.error(f"Webhook {event_id} has invalid JSON payload")
            webhook_event.processing_status = "FAILED_PERMANENTLY"
            db.commit()
            return
            
        normalized = normalize_webhook_payload(raw_payload, {})
        gateway_payment_id = normalized.get("gateway_payment_id")
        legacy_txn_id = normalized.get("transaction_id")
        
        # Transaction Lookup
        txn = None
        if gateway_payment_id:
            txn = db.query(Transaction).filter(Transaction.gateway_payment_id == gateway_payment_id).with_for_update().first()
        if not txn and legacy_txn_id:
            txn = db.query(Transaction).filter(Transaction.id == legacy_txn_id).with_for_update().first()
            
        if not txn:
            logger.warning(f"Webhook {event_id} references missing transaction (payment_id: {gateway_payment_id}, txn_id: {legacy_txn_id}). Retrying.")
            db.rollback() # Release locks before retrying
            # Celery native retry for missing transactions (handles race condition)
            raise self.retry(exc=Exception("Transaction not found"), countdown=60, max_retries=5)

        event_type = normalized.get("event_type")
        
        if event_type == "payment.failed":
            if txn.recovery_status == "NOT_STARTED":
                txn.recovery_status = "PROCESSING"
                db.commit()
                # Enqueue recovery orchestrator
                from app.worker.tasks import process_orchestrator
                process_orchestrator.apply_async(args=[txn.id])
            else:
                logger.info(f"Webhook {event_id} ignored: Transaction {txn.id} recovery already started ({txn.recovery_status})")
                
        elif event_type == "payment.captured":
            txn.status = "success"
            audit = AuditLog(
                transaction_id=txn.id,
                event_type="PAYMENT_CAPTURED",
                previous_state="failed", # We only recover failed ones, but anyway
                new_state="success",
                reasoning=f"Webhook event: {event_id}"
            )
            db.add(audit)
            
        elif event_type == "refund.created":
            if normalized.get("gateway_refund_id") and not txn.gateway_refund_id:
                txn.gateway_refund_id = normalized.get("gateway_refund_id")
            audit = AuditLog(
                transaction_id=txn.id,
                event_type="REFUND_CREATED",
                previous_state=txn.refund_status,
                new_state=txn.refund_status,
                reasoning=f"Webhook event: {event_id}"
            )
            db.add(audit)
            
        elif event_type in ["refund.processed", "refund.completed"]:
            if normalized.get("gateway_refund_id") and not txn.gateway_refund_id:
                txn.gateway_refund_id = normalized.get("gateway_refund_id")
            
            if txn.refund_status not in ["REFUND_REQUESTED", "REFUND_PROCESSING"]:
                logger.warning(f"Webhook {event_id} ignored: Transaction {txn.id} is in invalid state for refund completion ({txn.refund_status})")
            elif txn.refund_status != "REFUNDED":
                old_status = txn.refund_status
                txn.refund_status = "REFUNDED"
                
                audit = AuditLog(
                    transaction_id=txn.id,
                    event_type="REFUND_STATE_CHANGE",
                    previous_state=old_status,
                    new_state="REFUNDED",
                    reasoning=f"Webhook event: {event_id}"
                )
                db.add(audit)
                
        elif event_type == "refund.failed":
            if txn.refund_status not in ["REFUNDED", "REFUND_FAILED"]:
                old_status = txn.refund_status
                txn.refund_status = "REFUND_FAILED"
                
                audit = AuditLog(
                    transaction_id=txn.id,
                    event_type="REFUND_STATE_CHANGE",
                    previous_state=old_status,
                    new_state="REFUND_FAILED",
                    reasoning=f"Webhook event: {event_id}"
                )
                db.add(audit)
        else:
            logger.info(f"Ignoring unhandled webhook event type: {event_type}")

        webhook_event.processing_status = "PROCESSED"
        webhook_event.processed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        logger.error(f"Error processing webhook {event_id}: {e}")
        db.rollback()
        # Explicit retry budget enforcement
        try:
            webhook_event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).with_for_update().first()
            if webhook_event:
                webhook_event.retry_count += 1
                webhook_event.last_attempt_at = datetime.now(timezone.utc)
                
                if webhook_event.retry_count >= MAX_WEBHOOK_RETRIES:
                    logger.warning(f"Webhook {event_id} reached max retries. Marked as FAILED_PERMANENTLY.")
                    webhook_event.processing_status = "FAILED_PERMANENTLY"
                else:
                    webhook_event.processing_status = "FAILED"
                    
                db.commit()
        except:
            db.rollback()
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def reconcile_all_pending(self):
    """
    SAFE TO RETRY.
    Sweeps for stuck transactions, unknown gateway states, and orphaned recovery attempts.
    Triggered by Celery Beat every 1 minute.
    """
    logger.info("Starting Celery reconciliation sweep")
    db = SessionLocal()
    try:
        reconcile_orphaned_attempts(db)
        reconcile_unknown_attempts(db)
        reconcile_stuck_refunds(db)
        reconcile_pending_webhooks(db)
    except Exception as e:
        logger.error(f"Error in reconciliation sweep: {e}")
        self.retry(exc=e)
    finally:
        db.close()
