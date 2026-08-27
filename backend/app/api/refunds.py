from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.dependencies import get_api_key
from app.api.rate_limiter import rate_limit
from app.services.refund_service import get_refund_service

router = APIRouter()

@router.post("/payments/{transaction_id}/refund", dependencies=[Depends(rate_limit)])
def initiate_refund(
    transaction_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Initiate a refund for a successful or recovered payment.
    Delegates to RefundService for state and idempotency enforcement.
    """
    idempotency_key = f"refund_{transaction_id}"
    
    refund_service = get_refund_service(db)
    result = refund_service.initiate_refund(transaction_id, idempotency_key)
    
    if result["status"] == "FAILED" or result["status"] == "REFUND_FAILED":
        raise HTTPException(status_code=400, detail=result.get("result_message", "Refund failed"))
        
    return result
