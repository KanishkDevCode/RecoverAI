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
from app.services.webhook_parser import normalize_webhook_payload

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
    secret = settings.RAZORPAY_WEBHOOK_SECRET
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
        
    if not data:
        raise HTTPException(status_code=400, detail="Empty JSON payload")
        
    normalized = normalize_webhook_payload(data, dict(request.headers))
    
    event_id = normalized.get("event_id")
    event_type = normalized.get("event_type")
    
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Missing event_id or event_type")
        
    # 2. Persist Webhook Event (Idempotency check)
    try:
        webhook_event = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            transaction_id=normalized.get("transaction_id"),
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

    # 3. Process the Webhook asynchronously
    try:
        from app.worker.tasks import process_webhook
        process_webhook.apply_async(args=[webhook_event.event_id], queue="high_priority")
    except Exception as e:
        logger.error(f"Error enqueueing webhook task {event_id}: {e}")
        # We do NOT fail the request. The WebhookEvent is persisted in PostgreSQL.
        # Reconciliation will pick it up and re-enqueue it.
        pass
        
    return {"status": "ok"}
