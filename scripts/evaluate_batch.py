import os
import sys
import pandas as pd
import json
import logging
import uuid
from typing import Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.database import SessionLocal, engine, Base
from app.models.db_models import RecoveryAttempt, IdempotencyRecord
from app.services.orchestrator import RecoveryOrchestrator
from app.services.razorpay_mock import razorpay_service
from app.schemas.transaction import TransactionIncoming
from app.policy.rules import evaluate_policy
from app.services.state_machine import transition_recovery_attempt
from app.models.db_models import Transaction

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

INTERVENTION_COST = 2.0
FALSE_POSITIVE_COST = 5.0

class EvaluationMetrics:
    def __init__(self, name: str):
        self.name = name
        self.transactions_evaluated = 0
        self.transactions_failed = 0
        
        self.gross_revenue_at_risk = 0.0
        self.recovered_revenue = 0.0
        self.unrecovered_revenue = 0.0
        
        # Operations
        self.recovery_attempts = 0
        self.successful_recoveries = 0
        self.failed_recoveries = 0
        self.escalations = 0
        self.policy_blocks = 0
        
        # Economics
        self.unnecessary_intervention_cost = 0.0
        self.recovery_action_cost = 0.0
        
        self.safety_violations = {
            "unauthorized_executions": 0,
            "duplicate_executions": 0,
            "policy_bypasses": 0,
            "invalid_state_transitions": 0
        }

def _get_execution_count(db, attempt_id: str) -> int:
    idems = db.query(IdempotencyRecord).filter(IdempotencyRecord.attempt_id == attempt_id).all()
    return len(idems)

def run_evaluation():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    orchestrator = RecoveryOrchestrator(db)
    
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/v2/synthetic_test.csv"))
    if not os.path.exists(data_path):
        logger.error(f"Test data not found at {data_path}")
        sys.exit(1)
        
    df = pd.read_csv(data_path)
    logger.info(f"Loaded {len(df)} V2 HELD-OUT TEST transactions for evaluation.")
    
    metrics_a = EvaluationMetrics("No Recovery")
    metrics_b = EvaluationMetrics("Safe Naive Retry")
    metrics_c = EvaluationMetrics("RecoverAI")
    
    total_records = len(df)
    
    # Track paired outcomes
    paired_results = []
    
    for idx, row in df.iterrows():
        txn_id = str(row["transaction_id"])
        amount = float(row["amount"])
        is_recoverable = bool(row["ground_truth_recoverable"])
        failure_code = str(row["failure_code"]) if pd.notna(row["failure_code"]) else ""
        retry_count = int(row["retry_count"])
        
        # Shared input preparation
        txn_dict = {
            "id": txn_id,
            "customer_id": str(row["customer_id"]),
            "amount": amount,
            "currency": str(row["currency"]),
            "payment_status": str(row["payment_status"]),
            "payment_method": str(row["payment_method"]) if pd.notna(row["payment_method"]) else None,
            "failure_code": failure_code,
            "failure_reason": str(row["failure_reason"]) if pd.notna(row["failure_reason"]) else None,
            "retry_count": retry_count
        }
        
        try:
            txn = TransactionIncoming(**txn_dict)
        except Exception as e:
            logger.error(f"Input validation failed for {txn_id}: {e}")
            continue
            
        # Register base transaction in DB for state machine to find
        db_txn = db.query(Transaction).filter(Transaction.id == txn.id).first()
        if not db_txn:
            db_txn = Transaction(
                id=txn.id,
                customer_id=txn.customer_id,
                amount=txn.amount,
                currency=txn.currency,
                status=txn.payment_status,
                failure_code=txn.failure_code
            )
            db.add(db_txn)
            db.commit()
            
        for m in [metrics_a, metrics_b, metrics_c]:
            m.transactions_evaluated += 1
            m.transactions_failed += 1
            m.gross_revenue_at_risk += amount

        # ====================================================
        # STRATEGY A: NO RECOVERY
        # ====================================================
        metrics_a.unrecovered_revenue += amount
        net_value_a = 0.0
        
        # ====================================================
        # STRATEGY B: SAFE NAIVE RETRY
        # ====================================================
        # Create a fresh attempt ID for isolation
        b_attempt_id = f"att_b_{uuid.uuid4().hex[:12]}"
        b_attempt = RecoveryAttempt(id=b_attempt_id, transaction_id=txn.id, outcome_status="PENDING")
        db.add(b_attempt)
        db.commit()
        
        # Max aggressive naive values
        naive_action = "RETRY_PAYMENT"
        naive_ml_prob = 1.0
        
        # Evaluate exact same policy
        is_allowed_b, final_action_b, reason_b = evaluate_policy(
            transaction=txn,
            agent_action=naive_action,
            agent_confidence=1.0,
            current_retry_count=txn.retry_count,
            ml_probability=naive_ml_prob
        )
        
        net_value_b = 0.0
        if is_allowed_b and final_action_b in ["RETRY_PAYMENT", "WAIT_AND_RETRY"]:
            transition_recovery_attempt(db, b_attempt_id, "AUTHORIZED", reason="Policy approved")
            idem_key_b = f"idem_{txn.id}_B_{final_action_b}_{txn.retry_count}"
            result_b = razorpay_service.execute_recovery_action(db, txn.id, final_action_b, idem_key_b, b_attempt_id)
            
            executions_b = _get_execution_count(db, b_attempt_id)
            if executions_b > 1:
                metrics_b.safety_violations["duplicate_executions"] += (executions_b - 1)
            
            metrics_b.recovery_attempts += 1
            metrics_b.recovery_action_cost += INTERVENTION_COST
            
            if result_b.get("status") == "SUCCEEDED":
                metrics_b.successful_recoveries += 1
                metrics_b.recovered_revenue += amount
                net_value_b = amount - INTERVENTION_COST
            else:
                metrics_b.failed_recoveries += 1
                metrics_b.unrecovered_revenue += amount
                metrics_b.unnecessary_intervention_cost += FALSE_POSITIVE_COST
                net_value_b = -(INTERVENTION_COST + FALSE_POSITIVE_COST)
        else:
            new_state = "ESCALATED" if final_action_b == "CREATE_ESCALATION" else "STOPPED"
            transition_recovery_attempt(db, b_attempt_id, new_state, reason=f"Policy denied: {reason_b}")
            metrics_b.unrecovered_revenue += amount
            if new_state == "ESCALATED":
                metrics_b.escalations += 1
            else:
                metrics_b.policy_blocks += 1
                
            executions_b = _get_execution_count(db, b_attempt_id)
            if executions_b > 0:
                metrics_b.safety_violations["unauthorized_executions"] += executions_b

        # ====================================================
        # STRATEGY C: RECOVERAI (Using existing Orchestrator)
        # ====================================================
        # Note: We must ensure orchestrator creates a unique attempt_id for strategy C 
        # (It already does inside process_transaction)
        
        result_c = orchestrator.process_transaction(txn)
        outcome_c = result_c["outcome"]
        c_attempt_id = result_c["attempt_id"]
        
        executions_c = _get_execution_count(db, c_attempt_id)
        net_value_c = 0.0
        
        if outcome_c in ["SUCCEEDED", "FAILED", "UNKNOWN"]:
            if executions_c > 1:
                metrics_c.safety_violations["duplicate_executions"] += (executions_c - 1)
            if executions_c == 0:
                metrics_c.safety_violations["policy_bypasses"] += 1
                
            metrics_c.recovery_attempts += 1
            metrics_c.recovery_action_cost += INTERVENTION_COST
            
            if outcome_c == "SUCCEEDED":
                metrics_c.successful_recoveries += 1
                metrics_c.recovered_revenue += amount
                net_value_c = amount - INTERVENTION_COST
            else:
                metrics_c.failed_recoveries += 1
                metrics_c.unrecovered_revenue += amount
                metrics_c.unnecessary_intervention_cost += FALSE_POSITIVE_COST
                net_value_c = -(INTERVENTION_COST + FALSE_POSITIVE_COST)
        else:
            if executions_c > 0:
                metrics_c.safety_violations["unauthorized_executions"] += executions_c
                
            metrics_c.unrecovered_revenue += amount
            if outcome_c == "ESCALATED":
                metrics_c.escalations += 1
            else:
                metrics_c.policy_blocks += 1
                
        # Paired comparison tracking
        paired_results.append({
            "transaction_id": txn.id,
            "amount": amount,
            "failure_code": failure_code,
            "ground_truth_recoverable": is_recoverable,
            "safe_naive_net_value": net_value_b,
            "recoverai_net_value": net_value_c,
            "incremental_value": net_value_c - net_value_b
        })
                
        if (idx + 1) % 100 == 0:
            logger.info(f"Processed {idx + 1} / {total_records} test transactions...")
            
    # Compute Derived Metrics
    def calc_derived(m: EvaluationMetrics):
        m.recovery_rate = (m.recovered_revenue / m.gross_revenue_at_risk) if m.gross_revenue_at_risk > 0 else 0
        m.net_revenue = m.recovered_revenue - m.recovery_action_cost - m.unnecessary_intervention_cost

    calc_derived(metrics_a)
    calc_derived(metrics_b)
    calc_derived(metrics_c)
    
    # Assert Safety Invariants
    for m in [metrics_a, metrics_b, metrics_c]:
        for key, val in m.safety_violations.items():
            if val > 0:
                logger.error(f"CRITICAL SAFETY FAILURE in {m.name}: {key} > 0")
                sys.exit(1)
                
    # Compile Results
    results_json = {
        "dataset_size": total_records,
        "strategies": {
            "no_recovery": vars(metrics_a),
            "safe_naive": vars(metrics_b),
            "recoverai": vars(metrics_c)
        },
        "paired_incremental_value": sum(r["incremental_value"] for r in paired_results)
    }
    
    base_dir = os.path.dirname(__file__)
    with open(os.path.join(base_dir, "../data/v2/evaluation_results_v2.json"), "w") as f:
        json.dump(results_json, f, indent=2)
        
    report_md = f"""# RecoverAI V2 - Final Test Evaluation Report (Phase D/E)

**Evaluation Size**: {total_records} Held-Out Synthetic Transactions
**Safety Invariants**: PASSED (0 Unauthorized/Duplicate Executions for all strategies)

## Business Comparison

| Metric | No Recovery | Safe Naive Retry | **RecoverAI** |
|---|---|---|---|
| Revenue at Risk | ${metrics_a.gross_revenue_at_risk:,.2f} | ${metrics_b.gross_revenue_at_risk:,.2f} | **${metrics_c.gross_revenue_at_risk:,.2f}** |
| Interventions | 0 | {metrics_b.recovery_attempts} | **{metrics_c.recovery_attempts}** |
| Successful Recoveries | 0 | {metrics_b.successful_recoveries} | **{metrics_c.successful_recoveries}** |
| False Interventions (FP) | 0 | {metrics_b.failed_recoveries} | **{metrics_c.failed_recoveries}** |
| Recovered Revenue | $0.00 | ${metrics_b.recovered_revenue:,.2f} | **${metrics_c.recovered_revenue:,.2f}** |
| Recovery Rate | 0.0% | {metrics_b.recovery_rate*100:.1f}% | **{metrics_c.recovery_rate*100:.1f}%** |
| Intervention Cost | $0.00 | ${metrics_b.unnecessary_intervention_cost + metrics_b.recovery_action_cost:,.2f} | **${metrics_c.unnecessary_intervention_cost + metrics_c.recovery_action_cost:,.2f}** |
| **Net Value Added** | **$0.00** | **${metrics_b.net_revenue:,.2f}** | **${metrics_c.net_revenue:,.2f}** |

## Incremental Value
- **Incremental Value vs No Recovery**: ${metrics_c.net_revenue - metrics_a.net_revenue:,.2f}
- **Incremental Value vs Safe Naive**: ${sum(r['incremental_value'] for r in paired_results):,.2f}

## RecoverAI Operations & Safety
- **Policy Blocks (STOPPED)**: {metrics_c.policy_blocks}
- **Escalations to Human**: {metrics_c.escalations}
- **Unauthorized Executions**: 0
- **Duplicate Executions**: 0
"""

    with open(os.path.join(base_dir, "../docs/evaluation.md"), "w") as f:
        f.write(report_md)
        
    print(report_md)
    logger.info("Evaluation Complete. Results saved to data/v2/evaluation_results_v2.json and docs/evaluation.md")

if __name__ == "__main__":
    run_evaluation()
