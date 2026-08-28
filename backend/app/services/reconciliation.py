import logging
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.db_models import RecoveryAttempt, IdempotencyRecord, Transaction, AuditLog
from app.gateways import get_gateway
from app.services.state_machine import transition_recovery_attempt, ConcurrencyError

logger = logging.getLogger(__name__)

def reconcile_unknown_attempts(db: Session):
    """
    Finds and resolves RecoveryAttempts in the UNKNOWN state.
    """
    unknown_attempts = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "UNKNOWN").all()
    for attempt in unknown_attempts:
        try:
            logger.info(f"Reconciling UNKNOWN attempt {attempt.id} for transaction {attempt.transaction_id}")
            
            # Verify gateway state directly via the gateway interface
            # The gateway verifies state but DOES NOT transition attempt (we do that here or let the gateway mock do it for backwards compatibility if needed, but orchestrator expects it to just return status)
            gateway = get_gateway()
            new_status = gateway.verify_transaction_state(db, attempt.transaction_id, attempt.id)
            
            if new_status == "SUCCEEDED":
                txn = db.query(Transaction).filter(Transaction.id == attempt.transaction_id).first()
                if txn:
                    txn.recovery_status = "SUCCEEDED"
                    db.commit()
            
            # Update IdempotencyRecord status if possible
            idem_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.attempt_id == attempt.id).first()
            if idem_record and new_status in ["SUCCEEDED", "FAILED", "ESCALATED"]:
                idem_record.status = new_status
                db.commit()
                
        except ConcurrencyError:
            logger.warning(f"Concurrency conflict during reconciliation of {attempt.id}. Skipping.")
        except Exception as e:
            logger.error(f"Error during reconciliation of {attempt.id}: {e}")

def reconcile_orphaned_attempts(db: Session):
    """
    Finds stuck/orphaned attempts and safely moves them to UNKNOWN or ESCALATED.
    """
    timeout_str = os.getenv("PENDING_ATTEMPT_TIMEOUT_SECONDS", "300")
    try:
        timeout_seconds = int(timeout_str)
    except ValueError:
        timeout_seconds = 300
        
    cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    
    orphans = db.query(RecoveryAttempt).filter(
        RecoveryAttempt.outcome_status.in_(["PENDING", "AUTHORIZED", "EXECUTING", "VERIFYING"]),
        RecoveryAttempt.created_at < cutoff_time
    ).all()
    
    for attempt in orphans:
        logger.warning(f"Found orphaned attempt {attempt.id} in state {attempt.outcome_status}.")
        try:
            if attempt.outcome_status == "AUTHORIZED":
                # Check for evidence of execution
                idem_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.attempt_id == attempt.id).first()
                if idem_record:
                    logger.warning(f"Orphan {attempt.id} (AUTHORIZED) has idempotency record {idem_record.key}. Transitioning to UNKNOWN.")
                    transition_recovery_attempt(db, attempt.id, "UNKNOWN", reason="Timeout orphan cleanup with execution evidence")
                else:
                    logger.warning(f"Orphan {attempt.id} (AUTHORIZED) has NO execution evidence. Transitioning to STOPPED.")
                    transition_recovery_attempt(db, attempt.id, "STOPPED", reason="Timeout orphan cleanup without execution evidence")
            else:
                # We safely transition to UNKNOWN because execution might be ambiguous
                transition_recovery_attempt(db, attempt.id, "UNKNOWN", reason="Timeout orphan cleanup")
        except ConcurrencyError:
            logger.warning(f"Concurrency conflict while cleaning orphan {attempt.id}. Skipping.")
        except Exception as e:
            logger.error(f"Failed to reconcile orphan {attempt.id}: {e}")

def reconcile_stuck_refunds(db: Session):
    """
    Finds refunds stuck in REFUND_PROCESSING or REFUND_UNKNOWN and queries the gateway.
    """
    timeout_str = os.getenv("REFUND_RECONCILIATION_TIMEOUT_SECONDS", "300")
    try:
        timeout_seconds = int(timeout_str)
    except ValueError:
        timeout_seconds = 300
        
    cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    
    stuck_refunds = db.query(Transaction).filter(
        Transaction.refund_status.in_(["REFUND_REQUESTED", "REFUND_PROCESSING", "REFUND_UNKNOWN"]),
        Transaction.updated_at < cutoff_time
    ).all()
    
    gateway = get_gateway()
    
    for txn in stuck_refunds:
        logger.info(f"Reconciling stuck refund for transaction {txn.id} in state {txn.refund_status}")
        try:
            old_status = txn.refund_status
            new_status = gateway.verify_refund(db, txn.id)
            
            if new_status in ["REFUNDED", "REFUND_FAILED", "REFUND_UNKNOWN"] and new_status != old_status:
                txn.refund_status = new_status
                db.commit()
                
                audit = AuditLog(
                    transaction_id=txn.id,
                    event_type="REFUND_STATE_CHANGE",
                    previous_state=old_status,
                    new_state=new_status,
                    reasoning="Reconciliation worker verification"
                )
                db.add(audit)
                db.commit()
                
        except Exception as e:
            logger.error(f"Error during refund reconciliation for {txn.id}: {e}")

def reconcile_pending_webhooks(db: Session):
    """
    Finds WebhookEvents stuck in PENDING or FAILED state and re-enqueues them.
    Respects retry budget and avoids concurrent enqueueing.
    """
    from app.models.db_models import WebhookEvent
    from app.worker.tasks import process_webhook, MAX_WEBHOOK_RETRIES
    from sqlalchemy import or_, and_
    
    timeout_seconds = 300
    cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    
    stuck_events = db.query(WebhookEvent).filter(
        or_(
            and_(WebhookEvent.processing_status == "PENDING", WebhookEvent.received_at < cutoff_time),
            and_(
                WebhookEvent.processing_status == "FAILED", 
                WebhookEvent.retry_count < MAX_WEBHOOK_RETRIES,
                WebhookEvent.last_attempt_at < cutoff_time
            )
        )
    ).with_for_update(skip_locked=True).all()
    
    for event in stuck_events:
        logger.info(f"Reconciling stuck webhook event {event.event_id} (retry {event.retry_count}/{MAX_WEBHOOK_RETRIES})")
        try:
            # Update last_attempt_at so concurrent reconcilers or next sweeps won't pick it up immediately
            event.last_attempt_at = datetime.utcnow()
            db.commit()
            process_webhook.apply_async(args=[event.event_id], queue="high_priority")
        except Exception as e:
            logger.error(f"Error re-enqueueing webhook event {event.event_id}: {e}")
            db.rollback()
