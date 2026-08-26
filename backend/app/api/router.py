import logging
import os
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Security, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
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

from app.schemas.transaction import TransactionIncoming, PaymentCreateRequest
from app.schemas.events import RecoveryEvent, PaymentFailedData
from app.services.event_bus import event_bus

def run_orchestrator_bg(transaction: TransactionIncoming):
    db = SessionLocal()
    try:
        orchestrator = RecoveryOrchestrator(db)
        orchestrator.process_transaction(transaction)
    except Exception as e:
        logger.error(f"Error processing recovery: {e}")
    finally:
        db.close()

@router.post("/payments")
def create_payment(
    request: PaymentCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Simulates an initial payment gateway attempt.
    If it fails, it saves the transaction and triggers RecoverAI in the background.
    """
    # 1. Mock Gateway Attempt
    is_success = False
    failure_code = None
    failure_reason = None
    retry_count = 0
    
    if request.mode == "live":
        # In live mode, we simulate a successful payment to behave like a real app.
        is_success = True
    elif request.mode == "test":
        logger.info(f"REQUEST RECEIVED: mode='{request.mode}', amount={request.amount}, overrides={request.developer_overrides}")
        if request.developer_overrides:
            failure_code = request.developer_overrides.failure_code
            failure_reason = request.developer_overrides.failure_reason
            retry_count = request.developer_overrides.retry_count or 0
        else:
            # Fallback for test mode if no overrides provided
            failure_code = "insufficient_funds"
            failure_reason = "Customer bank declined transaction"
    
    # 2. Save original transaction
    status = "success" if is_success else "failed"
    db_txn = Transaction(
        id=request.id,
        customer_id=request.customer_id,
        amount=request.amount,
        currency=request.currency,
        status=status,
        failure_code=failure_code,
        failure_reason=failure_reason
    )
    db.add(db_txn)
    db.commit()
    
    if is_success:
        return {"transaction_id": request.id, "status": "SUCCEEDED", "message": "Payment completed successfully"}
    
    # 3. If failed, format for orchestrator and start background task
    txn_incoming = TransactionIncoming(
        id=request.id,
        customer_id=request.customer_id,
        amount=request.amount,
        currency=request.currency,
        payment_status="failed",
        payment_method=request.payment_method,
        failure_code=failure_code,
        failure_reason=failure_reason,
        retry_count=retry_count
    )
    
    # We don't emit PAYMENT_FAILED here. The Orchestrator emits it at the start of `process_transaction`.
    background_tasks.add_task(run_orchestrator_bg, txn_incoming)
    
    return {"transaction_id": request.id, "status": "PROCESSING", "message": "Payment failed. Handing off to RecoverAI."}

@router.post("/recovery/process")
def process_recovery(
    transaction: TransactionIncoming, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    """
    Triggers the recovery orchestration loop for a given transaction.
    Requires a valid transaction payload according to TransactionIncoming schema.
    Runs asynchronously in a background thread and returns immediately.
    """
    background_tasks.add_task(run_orchestrator_bg, transaction)
    return {"transaction_id": transaction.id, "status": "PROCESSING"}

@router.websocket("/ws/recovery/{transaction_id}")
async def websocket_recovery(websocket: WebSocket, transaction_id: str):
    await websocket.accept()
    queue = await event_bus.subscribe(transaction_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_text(event.model_dump_json())
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for txn: {transaction_id}")
    finally:
        event_bus.unsubscribe(transaction_id, queue)

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
        "amount": txn.amount,
        "currency": txn.currency,
        "original_status": txn.status,
        "failure_code": txn.failure_code,
        "failure_reason": txn.failure_reason,
        "created_at": txn.created_at,
        "recovery": None if not attempt else {
            "agent_diagnosis": attempt.agent_diagnosis,
            "policy_decision": attempt.policy_decision,
            "policy_reason": attempt.policy_reason,
            "outcome_status": attempt.outcome_status,
            "executed_action": attempt.executed_action,
            "created_at": attempt.created_at
        }
    }

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
    
    # Calculate revenue at risk (sum of all failed transaction amounts)
    failed_txns = db.query(Transaction).filter(Transaction.status == "failed").all()
    total_risk = sum([t.amount for t in failed_txns])
    
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
    """Returns the most recent transactions with their original and recovery status."""
    
    recent_txns = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(limit).all()
    
    results = []
    for txn in recent_txns:
        attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.transaction_id == txn.id).first()
        
        results.append({
            "transaction_id": txn.id,
            "customer_id": txn.customer_id,
            "amount": txn.amount,
            "currency": txn.currency,
            "original_status": txn.status,
            "failure_code": txn.failure_code,
            "failure_reason": txn.failure_reason,
            "agent_diagnosis": attempt.agent_diagnosis if attempt else None,
            "policy_action": attempt.policy_decision if attempt else None,
            "recovery_status": attempt.outcome_status if attempt else None,
            "timestamp": txn.created_at
        })
            
    return results
