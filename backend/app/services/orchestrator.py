import logging
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.services.audit_logger import AuditLogger
from app.services.ml_service import ml_service
from app.agents.diagnosis_agent import diagnosis_agent
from app.policy.rules import evaluate_policy
from app.services.razorpay_mock import razorpay_service

logger = logging.getLogger(__name__)

class RecoveryOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.audit_logger = AuditLogger(db)

    def process_transaction(self, transaction: 'TransactionIncoming') -> Dict[str, Any]:
        """
        The core recovery loop using the state machine.
        """
        import uuid
        from app.models.db_models import Transaction, RecoveryAttempt
        from app.services.state_machine import transition_recovery_attempt
        from app.schemas.transaction import TransactionIncoming
        
        txn_id = transaction.id
        
        # 1. Log ingestion
        self.audit_logger.log_transaction_ingestion(transaction)
        
        # 2. Initialize Attempt in PENDING state
        attempt_id = f"att_{uuid.uuid4().hex[:12]}"
        attempt = RecoveryAttempt(
            id=attempt_id,
            transaction_id=txn_id,
            outcome_status="PENDING"
        )
        self.db.add(attempt)
        self.db.commit()
        
        # 3. ML Probability
        ml_prob = ml_service.predict_recovery_probability(transaction)
        
        # 4. Agent Diagnosis
        diagnosis_response = diagnosis_agent.diagnose_transaction(transaction, ml_prob)
        
        # 5. Policy Gate
        retry_count = transaction.retry_count
        
        is_allowed, final_action, policy_reason = evaluate_policy(
            transaction=transaction,
            agent_action=diagnosis_response.recommended_action,
            agent_confidence=diagnosis_response.confidence,
            current_retry_count=retry_count,
            ml_probability=ml_prob
        )
        
        # Update attempt details
        attempt.ml_probability = ml_prob
        attempt.agent_diagnosis = diagnosis_response.diagnosis
        attempt.agent_confidence = diagnosis_response.confidence
        attempt.agent_action = diagnosis_response.recommended_action
        attempt.policy_decision = "ALLOWED" if is_allowed else "DENIED"
        attempt.policy_reason = policy_reason
        attempt.executed_action = final_action if is_allowed else "NONE"
        self.db.commit()
        
        # 6. Execution via State Machine
        external_ref = None
        
        if is_allowed and final_action in ["RETRY_PAYMENT", "WAIT_AND_RETRY", "SEND_RECOVERY_MESSAGE"]:
            transition_recovery_attempt(self.db, attempt_id, "AUTHORIZED", reason="Policy approved")
            
            idempotency_key = f"idem_{txn_id}_{final_action}_{retry_count}"
            result_dict = razorpay_service.execute_recovery_action(self.db, txn_id, final_action, idempotency_key, attempt_id)
            
            outcome_status = result_dict.get("status", "FAILED")
            external_ref = result_dict.get("external_reference") or result_dict.get("result_message")
            
            if outcome_status == "SUCCEEDED":
                txn = self.db.query(Transaction).filter(Transaction.id == txn_id).first()
                if txn:
                    txn.status = "recovered"
                    self.db.commit()
        else:
            new_state = "ESCALATED" if final_action == "CREATE_ESCALATION" else "STOPPED"
            transition_recovery_attempt(self.db, attempt_id, new_state, reason=f"Policy denied: {policy_reason}")
            outcome_status = new_state
            
        return {
            "transaction_id": txn_id,
            "attempt_id": attempt_id,
            "final_action": final_action,
            "outcome": outcome_status,
            "policy_reason": policy_reason,
            "external_reference": external_ref
        }
