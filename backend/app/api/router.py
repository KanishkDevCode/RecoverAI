import logging
import os
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.orchestrator import RecoveryOrchestrator
from app.models.db_models import AuditLog, Transaction, RecoveryAttempt
from sqlalchemy import func

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise HTTPException(status_code=403, detail="API Key header (X-API-Key) missing")
    
    expected_key = os.getenv("MERCHANT_API_KEY", "test_secret_key_123")
    if api_key_header != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key_header

router = APIRouter(prefix="/api/v1")

from app.schemas.transaction import TransactionIncoming

@router.post("/recovery/process")
def process_recovery(
    transaction: TransactionIncoming, 
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Triggers the recovery orchestration loop for a given transaction.
    Requires a valid transaction payload according to TransactionIncoming schema.
    FastAPI will automatically return 422 for invalid payloads.
    """
    try:
        orchestrator = RecoveryOrchestrator(db)
        result = orchestrator.process_transaction(transaction)
        return result
    except Exception as e:
        logger.error(f"Error processing recovery: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during recovery processing")

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

@router.get("/dashboard/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Returns high-level metrics for the frontend dashboard."""
    
    total_txns = db.query(Transaction).count()
    
    # Calculate revenue at risk (sum of all transaction amounts)
    total_risk = db.query(func.sum(Transaction.amount)).scalar() or 0.0
    
    # Calculate recovered revenue (sum of amounts where outcome was SUCCESS)
    recovered_txns = db.query(Transaction).join(
        RecoveryAttempt, Transaction.id == RecoveryAttempt.transaction_id
    ).filter(RecoveryAttempt.outcome_status == "SUCCESS").all()
    
    total_recovered = sum([t.amount for t in recovered_txns])
    
    # Calculate statuses
    success_count = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "SUCCESS").count()
    escalated_count = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "CREATE_ESCALATION").count()
    stopped_count = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "STOP_AUTOMATION").count()
    
    return {
        "total_transactions": total_txns,
        "revenue_at_risk": total_risk,
        "revenue_recovered": total_recovered,
        "recovery_rate": (total_recovered / total_risk * 100) if total_risk > 0 else 0,
        "successful_actions": success_count,
        "escalations": escalated_count,
        "stopped_automations": stopped_count
    }

@router.get("/transactions")
def get_recent_transactions(limit: int = 50, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Returns the most recent transactions with their recovery status."""
    
    recent_attempts = db.query(RecoveryAttempt).order_by(RecoveryAttempt.created_at.desc()).limit(limit).all()
    
    results = []
    for attempt in recent_attempts:
        txn = db.query(Transaction).filter(Transaction.id == attempt.transaction_id).first()
        if txn:
            results.append({
                "transaction_id": txn.id,
                "amount": txn.amount,
                "currency": txn.currency,
                "failure_code": txn.failure_code,
                "agent_diagnosis": attempt.agent_diagnosis,
                "policy_action": attempt.policy_decision,
                "outcome": attempt.outcome_status,
                "timestamp": attempt.created_at
            })
            
    return results
