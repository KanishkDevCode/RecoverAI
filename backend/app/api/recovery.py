from fastapi import APIRouter, Depends
from app.api.dependencies import get_api_key
from app.api.rate_limiter import rate_limit
from app.schemas.transaction import TransactionIncoming
from app.worker.tasks import process_orchestrator
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
