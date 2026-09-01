from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from app.database import get_db
from app.config import settings
from app.core.logging import logger

router = APIRouter()

api_key_header = APIKeyHeader(name="X-Observability-API-Key", auto_error=False)

def verify_observability_key(api_key_header: str = Security(api_key_header)):
    if not settings.OBSERVABILITY_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Observability API key not configured"
        )
    if api_key_header != settings.OBSERVABILITY_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Observability API Key"
        )
    return api_key_header

@router.get("", tags=["Metrics"])
def get_metrics(db: Session = Depends(get_db), _: str = Depends(verify_observability_key)):
    """
    Returns aggregate operational and safety metrics.
    Protected by Observability API Key.
    """
    try:
        metrics = {}
        
        # 1. Recovery Attempts in UNKNOWN state
        unknown_attempts = db.execute(
            text("SELECT COUNT(*) FROM recovery_attempts WHERE outcome_status = 'UNKNOWN'")
        ).scalar()
        metrics["recovery_attempts_unknown"] = unknown_attempts
        
        # 2. Recovery Attempts in ESCALATED state
        escalated_attempts = db.execute(
            text("SELECT COUNT(*) FROM recovery_attempts WHERE outcome_status = 'ESCALATED'")
        ).scalar()
        metrics["recovery_attempts_escalated"] = escalated_attempts
        
        # 3. Webhook Events FAILED_PERMANENTLY
        failed_webhooks = db.execute(
            text("SELECT COUNT(*) FROM webhook_events WHERE processing_status = 'FAILED_PERMANENTLY'")
        ).scalar()
        metrics["webhook_events_failed_permanently"] = failed_webhooks
        
        # 4. Stuck EXECUTING attempts
        stuck_threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.STUCK_EXECUTION_THRESHOLD_SECONDS)
        # Assuming attempts have a an updated_at or created_at column
        # Since we might not have a reliable updated_at on recovery_attempts right now, we use created_at
        # A more robust system would track state transition times.
        stuck_attempts = db.execute(
            text("SELECT COUNT(*) FROM recovery_attempts WHERE outcome_status = 'EXECUTING' AND created_at < :threshold"),
            {"threshold": stuck_threshold}
        ).scalar()
        metrics["recovery_attempts_stuck_executing"] = stuck_attempts
        
        return metrics

    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate metrics"
        )
