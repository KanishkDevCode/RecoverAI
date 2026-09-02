from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.dependencies import get_api_key
from app.models.db_models import Transaction, RecoveryAttempt
from app.services.money import to_major_units

router = APIRouter()

@router.get("/transactions")
def get_recent_transactions(limit: int = 50, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Returns the most recent transactions with their original and recovery status."""
    recent_txns = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(limit).all()
    results = []
    for txn in recent_txns:
        attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.transaction_id == txn.id).first()
        results.append({
            "transaction_id": txn.id,
            "customer_id": txn.customer_id,
            "amount": to_major_units(txn.amount),
            "currency": txn.currency,
            "original_status": txn.status,
            "recovery_status": txn.recovery_status,
            "failure_code": txn.failure_code,
            "failure_reason": txn.failure_reason,
            "agent_diagnosis": attempt.agent_diagnosis if attempt else None,
            "policy_action": attempt.policy_decision if attempt else None,
            "recovery_status_attempt": attempt.outcome_status if attempt else None,
            "refund_status": txn.refund_status,
            "timestamp": txn.created_at
        })
    return results

@router.get("/payments/{transaction_id}")
def get_payment_details(
    transaction_id: str, 
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Retrieves the full details of a payment, including original status and recovery attempt.
    """
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
        
    attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.transaction_id == transaction_id).first()
    
    return {
        "transaction_id": txn.id,
        "customer_id": txn.customer_id,
        "amount": to_major_units(txn.amount),
        "currency": txn.currency,
        "original_status": txn.status,
        "recovery_status": txn.recovery_status,
        "failure_code": txn.failure_code,
        "failure_reason": txn.failure_reason,
        "refund_status": txn.refund_status,
        "refund_amount": to_major_units(txn.refund_amount) if txn.refund_amount else None,
        "created_at": txn.created_at,
        "recovery": None if not attempt else {
            "agent_diagnosis": attempt.agent_diagnosis,
            "policy_decision": attempt.policy_decision,
            "policy_reason": attempt.policy_reason,
            "outcome_status": attempt.outcome_status,
            "executed_action": attempt.executed_action,
            "created_at": attempt.created_at,
            "latency_ms": attempt.latency_ms,
            "provider_used": attempt.provider_used
        }
    }
