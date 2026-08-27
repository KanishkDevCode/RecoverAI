from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.dependencies import get_api_key
from app.models.db_models import AuditLog

router = APIRouter()

@router.get("/audit/{transaction_id}")
def get_audit_trail(
    transaction_id: str, 
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Retrieves the immutable audit trail for a specific transaction.
    """
    logs = db.query(AuditLog).filter(AuditLog.transaction_id == transaction_id).order_by(AuditLog.timestamp.asc()).all()
    
    if not logs:
        raise HTTPException(status_code=404, detail=f"No audit logs found for transaction {transaction_id}")
        
    return [
        {
            "id": log.id,
            "timestamp": log.timestamp,
            "event_type": log.event_type,
            "decision_id": log.decision_id,
            "previous_state": log.previous_state,
            "new_state": log.new_state,
            "reasoning": log.reasoning
        }
        for log in logs
    ]
