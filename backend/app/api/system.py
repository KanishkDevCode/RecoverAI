import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.dependencies import get_api_key
from app.api.rate_limiter import rate_limit
from app.services.reconciliation import reconcile_unknown_attempts, reconcile_orphaned_attempts
from app.config import settings

router = APIRouter()

@router.post("/system/reconcile", dependencies=[Depends(rate_limit)])
def trigger_manual_reconciliation(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Manually triggers the reconciliation worker.
    Restricted to non-production environments.
    """
    if settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="Manual reconciliation disabled in production")
        
    reconcile_orphaned_attempts(db)
    reconcile_unknown_attempts(db)
    
    return {"status": "success", "message": "Reconciliation completed"}
