import uuid
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.db_models import Transaction, RecoveryAttempt, AuditLog

class AuditLogger:
    def __init__(self, db: Session):
        self.db = db

    def log_transaction_ingestion(self, transaction: 'TransactionIncoming'):
        """Logs the initial arrival/detection of a failed transaction."""
        txn_id = transaction.id
        
        # Upsert transaction
        existing_txn = self.db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not existing_txn:
            db_txn = Transaction(
                id=txn_id,
                customer_id=transaction.customer_id,
                amount=transaction.amount,
                currency=transaction.currency.value if hasattr(transaction.currency, "value") else transaction.currency,
                status=transaction.payment_status.value if hasattr(transaction.payment_status, "value") else transaction.payment_status,
                failure_code=transaction.failure_code,
                failure_reason=transaction.failure_reason
            )
            self.db.add(db_txn)
            self.db.commit()

        # Add an audit event
        audit = AuditLog(
            transaction_id=txn_id,
            event_type="DETECTION",
            new_state="failed",
            reasoning="Transaction failure detected."
        )
        self.db.add(audit)
        self.db.commit()

    def log_recovery_decision(
        self,
        transaction_id: str,
        ml_prob: float,
        agent_diagnosis: str,
        agent_confidence: float,
        agent_action: str,
        policy_allowed: bool,
        policy_action: str,
        policy_reason: str,
        executed_action: str,
        outcome_status: str
    ) -> str:
        """
        Logs the full context of a recovery decision.
        Returns the attempt ID.
        """
        attempt_id = f"att_{uuid.uuid4().hex[:12]}"
        
        attempt = RecoveryAttempt(
            id=attempt_id,
            transaction_id=transaction_id,
            ml_probability=ml_prob,
            agent_diagnosis=agent_diagnosis,
            agent_confidence=agent_confidence,
            agent_action=agent_action,
            policy_decision="ALLOWED" if policy_allowed else "DENIED",
            policy_reason=policy_reason,
            executed_action=executed_action,
            outcome_status=outcome_status
        )
        self.db.add(attempt)
        
        # Add corresponding audit log
        audit = AuditLog(
            transaction_id=transaction_id,
            decision_id=attempt_id,
            event_type="EXECUTION" if outcome_status else "POLICY_GATE",
            previous_state="failed",
            new_state=outcome_status or "escalated",
            reasoning=f"Agent: {agent_action} ({ml_prob:.2f}). Policy: {policy_action}. Reason: {policy_reason}"
        )
        self.db.add(audit)
        
        # Update transaction status if it recovered
        if outcome_status == "SUCCESS":
            txn = self.db.query(Transaction).filter(Transaction.id == transaction_id).first()
            if txn:
                txn.status = "recovered"
                
        self.db.commit()
        return attempt_id

