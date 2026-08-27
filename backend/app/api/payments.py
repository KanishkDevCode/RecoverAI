import logging
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db, SessionLocal
from app.api.dependencies import get_api_key
from app.api.rate_limiter import rate_limit
from app.models.db_models import Transaction, IdempotencyRecord
from app.schemas.transaction import PaymentCreateRequest, TransactionIncoming
from app.services.money import to_minor_units
from app.services.orchestrator import RecoveryOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

def run_orchestrator_bg(transaction: TransactionIncoming):
    db = SessionLocal()
    try:
        orchestrator = RecoveryOrchestrator(db)
        orchestrator.process_transaction(transaction)
    except Exception as e:
        logger.error(f"Error processing recovery: {e}")
    finally:
        db.close()

@router.post("/payments", dependencies=[Depends(rate_limit)])
def create_payment(
    request: PaymentCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
    idempotency_key: str = Header(None, alias="Idempotency-Key")
):
    """
    Simulates an initial payment gateway attempt.
    If it fails, it saves the transaction and triggers RecoverAI in the background.
    """
    # 0. API Idempotency Check
    scoped_key = None
    idempotency_record = None
    
    if idempotency_key:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:8]
        scoped_key = f"pay_{api_key_hash}_{idempotency_key}"
        
        fingerprint_data = f"{request.amount}_{request.currency}_{request.customer_id}_{request.mode}"
        request_hash = hashlib.sha256(fingerprint_data.encode()).hexdigest()
        
        try:
            idempotency_record = IdempotencyRecord(
                key=scoped_key,
                status="PENDING",
                request_hash=request_hash
            )
            db.add(idempotency_record)
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == scoped_key).first()
            if existing_record:
                if existing_record.request_hash != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency key already used with different parameters")
                if existing_record.status == "PENDING":
                    raise HTTPException(status_code=409, detail="Request already in progress")
                if existing_record.status == "COMPLETED" and existing_record.response_body:
                    headers = {"Idempotent-Replay": "true"}
                    return JSONResponse(
                        content=json.loads(existing_record.response_body),
                        status_code=existing_record.status_code or 200,
                        headers=headers
                    )

    # 1. Mock Gateway Attempt
    is_success = False
    failure_code = None
    failure_reason = None
    retry_count = 0
    
    if request.mode == "live":
        is_success = True
    elif request.mode == "test":
        logger.info(f"REQUEST RECEIVED: mode='{request.mode}', amount={request.amount}, overrides={request.developer_overrides}")
        if request.developer_overrides:
            failure_code = request.developer_overrides.failure_code
            failure_reason = request.developer_overrides.failure_reason
            retry_count = request.developer_overrides.retry_count or 0
        else:
            failure_code = "insufficient_funds"
            failure_reason = "Customer bank declined transaction"
    
    # 2. Save original transaction
    status = "success" if is_success else "failed"
    try:
        db_txn = Transaction(
            id=request.id,
            customer_id=request.customer_id,
            amount=to_minor_units(request.amount),
            currency=request.currency,
            status=status,
            recovery_status="NOT_STARTED",
            failure_code=failure_code,
            failure_reason=failure_reason
        )
        db.add(db_txn)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Transaction {request.id} already exists")
    
    response_data = None
    
    if is_success:
        response_data = {"transaction_id": request.id, "status": "SUCCEEDED", "message": "Payment completed successfully"}
    else:
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
        background_tasks.add_task(run_orchestrator_bg, txn_incoming)
        response_data = {"transaction_id": request.id, "status": "PROCESSING", "message": "Payment failed. Handing off to RecoverAI."}
        
    # 4. Finalize Idempotency Record
    if idempotency_key and scoped_key:
        record_to_update = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == scoped_key).first()
        if record_to_update:
            record_to_update.status = "COMPLETED"
            record_to_update.response_body = json.dumps(response_data)
            record_to_update.status_code = 200
            db.commit()
            
    return JSONResponse(content=response_data, status_code=200)
