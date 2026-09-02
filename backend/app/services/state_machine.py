import logging
from sqlalchemy.orm import Session
from app.models.db_models import RecoveryAttempt, AuditLog

logger = logging.getLogger(__name__)

# The 11 canonical financial states
VALID_TRANSITIONS = {
    "PENDING": ["AUTHORIZED", "STOPPED", "ESCALATED", "WAITING", "AWAITING_CUSTOMER", "UNKNOWN"],
    "AUTHORIZED": ["EXECUTING", "UNKNOWN", "STOPPED"],
    "EXECUTING": ["SUCCEEDED", "FAILED", "UNKNOWN"],
    "UNKNOWN": ["VERIFYING"],
    "VERIFYING": ["SUCCEEDED", "FAILED", "UNKNOWN", "ESCALATED"],
    "SUCCEEDED": [],
    "FAILED": [],
    "STOPPED": [],
    "ESCALATED": [],
    "WAITING": ["AUTHORIZED", "STOPPED", "ESCALATED"],
    "AWAITING_CUSTOMER": []
}

class ConcurrencyError(Exception):
    pass

def transition_recovery_attempt(
    db: Session, 
    attempt_id: str, 
    new_state: str, 
    reason: str
) -> RecoveryAttempt:
    """
    Safely transitions a RecoveryAttempt to a new state.
    Enforces legal state transitions and creates an AuditLog event.
    Uses optimistic concurrency control to prevent race conditions.
    """
    attempt = db.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).first()
    if not attempt:
        raise ValueError(f"RecoveryAttempt {attempt_id} not found")
        
    current_state = attempt.outcome_status
    current_version = attempt.version
    
    if new_state not in VALID_TRANSITIONS.get(current_state, []):
        raise ValueError(f"Invalid state transition from {current_state} to {new_state}")
        
    logger.info(f"Transitioning {attempt_id} from {current_state} to {new_state}. Reason: {reason}")
    
    # Optimistic Concurrency Update
    updated_rows = db.query(RecoveryAttempt).filter(
        RecoveryAttempt.id == attempt_id,
        RecoveryAttempt.version == current_version
    ).update({
        "outcome_status": new_state,
        "version": current_version + 1
    })
    
    if updated_rows == 0:
        db.rollback()
        raise ConcurrencyError(f"Concurrency error: Attempt {attempt_id} was modified by another transaction.")
    
    audit = AuditLog(
        transaction_id=attempt.transaction_id,
        decision_id=attempt.id,
        event_type="STATE_TRANSITION",
        previous_state=current_state,
        new_state=new_state,
        reasoning=reason
    )
    db.add(audit)
    db.commit()
    
    # Need to fetch again because update() bypassed session tracking
    return db.query(RecoveryAttempt).filter(RecoveryAttempt.id == attempt_id).first()
