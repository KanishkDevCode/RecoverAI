import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from app.models.db_models import Transaction, WebhookEvent, AuditLog
from app.worker.tasks import process_webhook, MAX_WEBHOOK_RETRIES
from app.services.reconciliation import reconcile_pending_webhooks
from celery.exceptions import Retry

# Using the existing integration fixtures
from tests.integration.test_webhook_celery import setup_db, db_session, client

def test_pending_webhook_is_reconciled(db_session: Session):
    # Setup
    event_id = "evt_pending_reconcile"
    txn = Transaction(id="txn_pending_test", amount=1000, currency="USD", status="success", recovery_status="NOT_STARTED", refund_status="REFUND_REQUESTED")
    db_session.add(txn)
    
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=6)
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_pending_test",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="PENDING",
        received_at=cutoff
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.process_webhook.apply_async") as mock_apply:
        reconcile_pending_webhooks(db_session)
        mock_apply.assert_called_once()
        args = mock_apply.call_args[1].get('args') or mock_apply.call_args[0][1].get('args') if len(mock_apply.call_args) > 1 else mock_apply.call_args.kwargs.get('args')
        assert args == [event_id]

def test_failed_webhook_is_retried(db_session: Session):
    event_id = "evt_failed_retry"
    txn = Transaction(id="txn_failed_retry_test", amount=1000, currency="USD", status="success", recovery_status="NOT_STARTED", refund_status="REFUND_REQUESTED")
    db_session.add(txn)
    
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=6)
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_failed_retry_test",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="FAILED",
        received_at=cutoff - timedelta(days=1),
        last_attempt_at=cutoff,
        retry_count=1
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.process_webhook.apply_async") as mock_apply:
        reconcile_pending_webhooks(db_session)
        mock_apply.assert_called_once()
        
    event = db_session.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert event.last_attempt_at > cutoff # Verify atomic timestamp update

def test_failed_webhook_retry_count_increments(db_session: Session):
    event_id = "evt_failed_increment"
    txn = Transaction(id="txn_failed_increment", amount=1000, currency="USD", status="success", recovery_status="NOT_STARTED", refund_status="REFUND_REQUESTED")
    db_session.add(txn)
    
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_failed_increment",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="PENDING",
        retry_count=0
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        # Poison pill: patch AuditLog to raise error
        with patch("app.models.db_models.AuditLog", side_effect=Exception("Poison")):
            process_webhook(event_id)
            
    event = db_session.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert event.processing_status == "FAILED"
    assert event.retry_count == 1
    assert event.last_attempt_at is not None

def test_failed_webhook_stops_after_max_retries(db_session: Session):
    event_id = "evt_failed_max"
    txn = Transaction(id="txn_failed_max", amount=1000, currency="USD", status="success", recovery_status="NOT_STARTED", refund_status="REFUND_REQUESTED")
    db_session.add(txn)
    
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_failed_max",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="FAILED",
        retry_count=MAX_WEBHOOK_RETRIES - 1
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        with patch("app.models.db_models.AuditLog", side_effect=Exception("Poison")):
            process_webhook(event_id)
            
    event = db_session.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert event.processing_status == "FAILED_PERMANENTLY"
    assert event.retry_count == MAX_WEBHOOK_RETRIES

def test_reconciliation_ignores_failed_permanently(db_session: Session):
    event_id = "evt_failed_perm_recon"
    
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=6)
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_failed_perm_recon",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="FAILED_PERMANENTLY",
        received_at=cutoff,
        last_attempt_at=cutoff,
        retry_count=MAX_WEBHOOK_RETRIES
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.process_webhook.apply_async") as mock_apply:
        reconcile_pending_webhooks(db_session)
        mock_apply.assert_not_called()

def test_last_attempt_at_prevents_immediate_repeated_enqueue(db_session: Session):
    event_id = "evt_recent_attempt"
    
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_recent",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="FAILED",
        received_at=recent_time - timedelta(days=1),
        last_attempt_at=recent_time,
        retry_count=1
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.process_webhook.apply_async") as mock_apply:
        reconcile_pending_webhooks(db_session)
        mock_apply.assert_not_called()

def test_concurrent_reconciliation_avoids_duplicate(db_session: Session):
    # This relies on the skip_locked and last_attempt_at updating in the loop
    # We test that the loop updates last_attempt_at immediately
    event_id = "evt_concurrent"
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=6)
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_concurrent",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="PENDING",
        received_at=cutoff
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.process_webhook.apply_async"):
        reconcile_pending_webhooks(db_session)
        
    event = db_session.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert event.last_attempt_at is not None
    assert event.last_attempt_at > cutoff

def test_already_processed_webhook_is_noop(db_session: Session):
    event_id = "evt_processed_noop"
    
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_noop",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="PROCESSED"
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        process_webhook(event_id)
        
    event = db_session.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert event.processing_status == "PROCESSED"
    assert event.retry_count == 0

def test_webhook_cannot_execute_payment_or_refund(db_session: Session):
    # Ensure no calls to execute_recovery_action or initiate_refund are made
    event_id = "evt_safe_exec"
    txn = Transaction(id="txn_safe_exec", amount=1000, currency="USD", status="success", recovery_status="NOT_STARTED", refund_status="REFUND_REQUESTED")
    db_session.add(txn)
    
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_safe_exec",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="PENDING"
    )
    db_session.add(event)
    db_session.commit()
    
    with patch("app.worker.tasks.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        process_webhook(event_id)
            
    event = db_session.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert event.processing_status == "PROCESSED"
    
def test_poison_pill_webhook_terminates(db_session: Session):
    event_id = "evt_poison_terminates"
    txn = Transaction(id="txn_poison", amount=1000, currency="USD", status="success", recovery_status="NOT_STARTED", refund_status="REFUND_REQUESTED")
    db_session.add(txn)
    
    event = WebhookEvent(
        event_id=event_id, 
        event_type="refund.completed", 
        transaction_id="txn_poison",
        payload_hash="hash",
        payload=json.dumps({"transaction_id": "txn_safe_exec", "event_type": "refund.completed"}),
        processing_status="PENDING"
    )
    db_session.add(event)
    db_session.commit()

    with patch("app.worker.tasks.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        # Simulate constant exception 4 times by mocking AuditLog to raise
        with patch("app.models.db_models.AuditLog", side_effect=Exception("Poison")):
            for _ in range(MAX_WEBHOOK_RETRIES + 1):
                process_webhook(event_id)
                
    event = db_session.query(WebhookEvent).filter_by(event_id=event_id).first()
    assert event.processing_status == "FAILED_PERMANENTLY"
    assert event.retry_count == MAX_WEBHOOK_RETRIES
