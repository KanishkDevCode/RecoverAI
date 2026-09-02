import logging
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.services.audit_logger import AuditLogger
from app.services.ml_service import ml_service
from app.agents.diagnosis_agent import diagnosis_agent
from app.policy.rules import evaluate_policy
from app.services.event_bus import event_bus
from app.services.execution_guard import get_execution_guard
from app.schemas.events import RecoveryEvent

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
        
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="PAYMENT_FAILED",
            data={
                "amount": transaction.amount,
                "currency": transaction.currency.value if hasattr(transaction.currency, "value") else transaction.currency,
                "failure_code": transaction.failure_code,
                "failure_reason": transaction.failure_reason
            }
        ))
        
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
        
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="ML_PREDICTION",
            data={
                "probability": ml_prob,
                "features_used": len(ml_service.features_list)
            }
        ))
        
        # 4. Agent Diagnosis
        diagnosis_response = diagnosis_agent.diagnose_transaction(transaction, ml_prob)
        
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="AI_RECOMMENDATION",
            data={
                "diagnosis": diagnosis_response.diagnosis,
                "recommended_action": diagnosis_response.recommended_action,
                "confidence": diagnosis_response.confidence
            }
        ))
        
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
        attempt.provider_used = getattr(diagnosis_response, 'provider_used', None)
        attempt.latency_ms = getattr(diagnosis_response, 'latency_ms', None)
        self.db.commit()
        
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="POLICY_DECISION",
            data={
                "is_allowed": is_allowed,
                "final_action": final_action,
                "reason": policy_reason,
                "hard_limit_enforced": not is_allowed
            }
        ))
        
        # 6. Execution via State Machine
        external_ref = None
        
        if is_allowed:
            if final_action == "RETRY_PAYMENT":
                transition_recovery_attempt(self.db, attempt_id, "AUTHORIZED", reason="Policy approved")
                
                event_bus.publish(RecoveryEvent(
                    transaction_id=txn_id,
                    event_type="STATE_CHANGE",
                    data={"previous_state": "PENDING", "new_state": "AUTHORIZED", "reason": "Policy approved"}
                ))
                
                idempotency_key = f"idem_{txn_id}_{final_action}_{retry_count}"
                
                guard = get_execution_guard(self.db)
                result_dict = guard.execute(txn_id, attempt_id, final_action, idempotency_key, retry_count)
                
                outcome_status = result_dict.get("status", "FAILED")
                external_ref = result_dict.get("external_reference") or result_dict.get("result_message")
                
                event_bus.publish(RecoveryEvent(
                    transaction_id=txn_id,
                    event_type="GATEWAY_RESULT",
                    data={"action_executed": final_action, "status": outcome_status, "message": external_ref}
                ))
                
                if outcome_status == "SUCCEEDED":
                    # We will update recovery_status below
                    pass
            
            elif final_action == "WAIT_AND_RETRY":
                outcome_status = "WAITING"
                transition_recovery_attempt(self.db, attempt_id, "WAITING", reason="Recovery scheduled")
                
                event_bus.publish(RecoveryEvent(
                    transaction_id=txn_id,
                    event_type="STATE_CHANGE",
                    data={"previous_state": "PENDING", "new_state": "WAITING", "reason": "Recovery scheduled"}
                ))
                
                # Dispatch the retry task
                from app.worker.tasks import process_scheduled_retry, execute_scheduled_retry
                try:
                    logger.info(f"[Recovery] Scheduling retry attempt_id={attempt_id} countdown=30")
                    process_scheduled_retry.apply_async(args=[attempt_id], countdown=30)
                except Exception as e:
                    logger.warning("[Recovery] Celery dispatch unavailable; using controlled synchronous development fallback")
                    execute_scheduled_retry(attempt_id)


            elif final_action == "SEND_RECOVERY_MESSAGE":
                outcome_status = "AWAITING_CUSTOMER"
                transition_recovery_attempt(self.db, attempt_id, "AWAITING_CUSTOMER", reason="Recovery message sent")
                
                event_bus.publish(RecoveryEvent(
                    transaction_id=txn_id,
                    event_type="STATE_CHANGE",
                    data={"previous_state": "PENDING", "new_state": "AWAITING_CUSTOMER", "reason": "Recovery message sent"}
                ))
            else:
                # Should not reach here if is_allowed is true, but handle safely
                outcome_status = "STOPPED"
                transition_recovery_attempt(self.db, attempt_id, "STOPPED", reason=f"Unknown action {final_action}")
        else:
            outcome_status = "ESCALATED" if final_action == "CREATE_ESCALATION" else "STOPPED"
            transition_recovery_attempt(self.db, attempt_id, outcome_status, reason="Policy rejected")
            
            event_bus.publish(RecoveryEvent(
                transaction_id=txn_id,
                event_type="STATE_CHANGE",
                data={"previous_state": "PENDING", "new_state": outcome_status, "reason": "Policy rejected"}
            ))
            
        # ALWAYS sync outcome_status to the transaction record
        txn = self.db.query(Transaction).filter(Transaction.id == txn_id).first()
        if txn:
            txn.recovery_status = outcome_status
            self.db.commit()
            
        result_dict_return = {
            "transaction_id": txn_id,
            "attempt_id": attempt_id,
            "final_action": final_action,
            "outcome": outcome_status,
            "policy_reason": policy_reason,
            "external_reference": external_ref
        }
        
        event_bus.publish(RecoveryEvent(
            transaction_id=txn_id,
            event_type="RECOVERY_COMPLETE",
            data={
                "outcome": outcome_status,
                "net_value_recovered": transaction.amount if outcome_status == "SUCCEEDED" else 0.0
            }
        ))
        
        return result_dict_return
