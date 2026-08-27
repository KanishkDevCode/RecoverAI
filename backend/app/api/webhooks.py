import logging
import json
import hashlib
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.db_models import WebhookEvent, Transaction, AuditLog
from app.gateways import get_gateway
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/webhooks/gateway")
async def gateway_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature")
):
    """
    Idempotent webhook endpoint for handling asynchronous gateway updates (e.g. refunds).
    Requires a valid HMAC-SHA256 signature.
    """
    if not x_razorpay_signature:
        logger.warning("Webhook rejected: Missing X-Razorpay-Signature")
        raise HTTPException(status_code=401, detail="Missing signature")
        
    payload_bytes = await request.body()
    gateway = get_gateway()
    
    # 1. Signature Verification
    secret = settings.WEBHOOK_SECRET
    is_valid = gateway.verify_webhook_signature(payload_bytes, x_razorpay_signature, secret)
    
    if not is_valid:
        logger.warning("Webhook rejected: Invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    payload_str = payload_bytes.decode('utf-8')
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    event_id = data.get("event_id")
    event_type = data.get("event_type")
    transaction_id = data.get("transaction_id")
    
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Missing event_id or event_type")
        
    # 2. Persist Webhook Event (Idempotency check)
    try:
        webhook_event = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            transaction_id=transaction_id,
            payload_hash=payload_hash,
            payload=payload_str,
            processing_status="PENDING"
        )
        db.add(webhook_event)
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info(f"Webhook {event_id} already received. Returning 200 OK.")
        # Update existing record if it was stuck
        existing_event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
        if existing_event and existing_event.processing_status == "PROCESSED":
            return {"status": "ok", "message": "already processed"}
        
        # If it's still pending/failed, we will re-attempt processing
        webhook_event = existing_event

    # 3. Process the Webhook
    try:
        if event_type == "refund.completed":
            _process_refund_completed(db, transaction_id, webhook_event.event_id)
        elif event_type == "refund.failed":
            _process_refund_failed(db, transaction_id, webhook_event.event_id)
        else:
            logger.info(f"Ignoring unhandled webhook event type: {event_type}")
            
        webhook_event.processing_status = "PROCESSED"
        webhook_event.processed_at = datetime.utcnow()
        db.commit()
        
    except Exception as e:
        logger.error(f"Error processing webhook {event_id}: {e}")
        webhook_event.processing_status = "FAILED"
        webhook_event.processed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=500, detail="Internal server error during processing")
        
    return {"status": "ok"}

def _process_refund_completed(db: Session, transaction_id: str, event_id: str):
    if not transaction_id:
        return
        
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        logger.warning(f"Webhook {event_id} references unknown transaction {transaction_id}")
        return
        
    if txn.refund_status == "REFUNDED":
        return # Already refunded
        
    # P2 Webhook intent validation: Only transition if refund was initiated
    if txn.refund_status not in ["REFUND_REQUESTED", "REFUND_PROCESSING"]:
        logger.warning(f"Webhook {event_id} ignored: Transaction {transaction_id} is in invalid state for refund completion ({txn.refund_status})")
        return
        
    old_status = txn.refund_status
    txn.refund_status = "REFUNDED"
    db.commit()
    
    audit = AuditLog(
        transaction_id=transaction_id,
        event_type="REFUND_STATE_CHANGE",
        previous_state=old_status,
        new_state="REFUNDED",
        reasoning=f"Webhook event: {event_id}"
    )
    db.add(audit)
    db.commit()

def _process_refund_failed(db: Session, transaction_id: str, event_id: str):
    if not transaction_id:
        return
        
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        return
        
    if txn.refund_status in ["REFUNDED", "REFUND_FAILED"]:
        return
        
    # P2 Webhook intent validation: Only transition if refund was initiated
    if txn.refund_status not in ["REFUND_REQUESTED", "REFUND_PROCESSING"]:
        logger.warning(f"Webhook {event_id} ignored: Transaction {transaction_id} is in invalid state for refund failure ({txn.refund_status})")
        return
        
    old_status = txn.refund_status
    txn.refund_status = "REFUND_FAILED"
    db.commit()
    
    audit = AuditLog(
        transaction_id=transaction_id,
        event_type="REFUND_STATE_CHANGE",
        previous_state=old_status,
        new_state="REFUND_FAILED",
        reasoning=f"Webhook event: {event_id}"
    )
    db.add(audit)
    db.commit()
