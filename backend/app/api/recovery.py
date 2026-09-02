from fastapi import APIRouter, Depends
from app.api.dependencies import get_api_key
from app.api.rate_limiter import rate_limit
from app.schemas.transaction import TransactionIncoming
from app.worker.tasks import process_orchestrator
from app.models.db_models import Transaction, RecoveryAttempt, AuditLog
from app.database import get_db
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/recovery/process", dependencies=[Depends(rate_limit)])
def process_recovery(
    transaction: TransactionIncoming, 
    api_key: str = Depends(get_api_key)
):
    """
    Triggers the recovery orchestration loop for a given transaction.
    Requires a valid transaction payload according to TransactionIncoming schema.
    Runs durably via Celery and returns immediately.
    """
    try:
        from app.config import settings
        if settings.CELERY_BROKER_URL:
            process_orchestrator.delay(transaction.id)
        else:
            logger.error("CELERY_BROKER_URL not configured.")
    except Exception as e:
        logger.error(f"Failed to enqueue orchestration task: {e}")
        
        
    return {"transaction_id": transaction.id, "status": "PROCESSING"}

@router.post("/recovery/manual/{transaction_id}")
def manual_recovery(
    transaction_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Simulates a customer manually completing a recovery flow (e.g. via 3D Secure / magic link).
    """
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        return {"error": "not found"}
        
    attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.transaction_id == transaction_id).first()
    
    if txn.recovery_status != "SUCCEEDED":
        txn.recovery_status = "SUCCEEDED"
        if attempt:
            attempt.outcome_status = "SUCCEEDED"
            
        audit = AuditLog(
            transaction_id=transaction_id,
            event_type="STATE_TRANSITION",
            previous_state="AWAITING_CUSTOMER",
            new_state="SUCCEEDED",
            reasoning="Customer manually completed recovery via secure link."
        )
        db.add(audit)
        db.commit()
        
    return {"status": "SUCCESS"}
