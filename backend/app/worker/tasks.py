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


MAX_WEBHOOK_RETRIES = 3

@celery_app.task(bind=True, max_retries=0)  # We handle retries natively using our bounded logic
def process_webhook(self, event_id: str):
    """
    SAFE TO RETRY. Processes webhooks durably.
    """
    from datetime import datetime, timezone
    from app.models.db_models import WebhookEvent, AuditLog
    
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

        transaction_id = webhook_event.transaction_id
        if not transaction_id:
            logger.warning(f"Webhook {event_id} has no transaction_id. Marking processed.")
            webhook_event.processing_status = "PROCESSED"
            webhook_event.processed_at = datetime.now(timezone.utc)
            db.commit()
            return
            
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).with_for_update().first()
        if not txn:
            logger.warning(f"Webhook {event_id} references unknown transaction {transaction_id}")
            webhook_event.processing_status = "PROCESSED"
            webhook_event.processed_at = datetime.now(timezone.utc)
            db.commit()
            return

        event_type = webhook_event.event_type
        
        if event_type == "refund.completed":
            if txn.refund_status not in ["REFUND_REQUESTED", "REFUND_PROCESSING"]:
                logger.warning(f"Webhook {event_id} ignored: Transaction {transaction_id} is in invalid state for refund completion ({txn.refund_status})")
            elif txn.refund_status != "REFUNDED":
                old_status = txn.refund_status
                txn.refund_status = "REFUNDED"
                
                audit = AuditLog(
                    transaction_id=transaction_id,
                    event_type="REFUND_STATE_CHANGE",
                    previous_state=old_status,
                    new_state="REFUNDED",
                    reasoning=f"Webhook event: {event_id}"
                )
                db.add(audit)
                
        elif event_type == "refund.failed":
            if txn.refund_status not in ["REFUND_REQUESTED", "REFUND_PROCESSING"]:
                logger.warning(f"Webhook {event_id} ignored: Transaction {transaction_id} is in invalid state for refund failure ({txn.refund_status})")
            elif txn.refund_status not in ["REFUNDED", "REFUND_FAILED"]:
                old_status = txn.refund_status
                txn.refund_status = "REFUND_FAILED"
                
                audit = AuditLog(
                    transaction_id=transaction_id,
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
