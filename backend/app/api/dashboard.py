from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.dependencies import get_api_key
from app.models.db_models import Transaction, RecoveryAttempt, AuditLog
from app.services.money import to_major_units

router = APIRouter()

@router.get("/dashboard/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Returns high-level metrics for the frontend dashboard."""
    
    total_txns = db.query(Transaction).count()
    
    # Calculate revenue at risk (sum of all failed transaction amounts)
    failed_txns = db.query(Transaction).filter(Transaction.status == "failed").all()
    total_risk = sum([to_major_units(t.amount) for t in failed_txns])
    
    # Calculate recovered revenue (sum of amounts where outcome was SUCCESS)
    recovered_txns = db.query(Transaction).join(
        RecoveryAttempt, Transaction.id == RecoveryAttempt.transaction_id
    ).filter(RecoveryAttempt.outcome_status == "SUCCEEDED").all()
    
    total_recovered = sum([to_major_units(t.amount) for t in recovered_txns])
    
    # Total successful revenue (all original successes + recovered)
    success_txns = db.query(Transaction).filter(Transaction.status == "success").all()
    total_revenue = sum([to_major_units(t.amount) for t in success_txns]) + total_recovered
    
    # Total refunds
    refunded_txns = db.query(Transaction).filter(Transaction.refund_status == "REFUNDED").all()
    total_refunds = sum([to_major_units(t.refund_amount) for t in refunded_txns if t.refund_amount])
    
    # Calculate statuses
    success_count = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "SUCCEEDED").count()
    escalated_count = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "ESCALATED").count()
    stopped_count = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "STOPPED").count()
    
    # ML and Agent statistics
    # This represents transactions that failed initially, where RecoverAI made decisions
    total_recoveries = db.query(RecoveryAttempt).count()
    ml_predictions_count = total_recoveries # We predict on every failure
    ai_recommendations_count = total_recoveries
    policy_allowed = db.query(RecoveryAttempt).filter(RecoveryAttempt.policy_decision == "ALLOWED").count()
    policy_denied = db.query(RecoveryAttempt).filter(RecoveryAttempt.policy_decision == "DENIED").count()
    gateway_executions = db.query(AuditLog).filter(AuditLog.event_type == "GATEWAY_RESULT").count()
    unknown_transactions = db.query(RecoveryAttempt).filter(RecoveryAttempt.outcome_status == "UNKNOWN").count()
    
    # Provider stats
    from sqlalchemy import func
    provider_counts = db.query(
        RecoveryAttempt.provider_used, 
        func.count(RecoveryAttempt.id)
    ).group_by(RecoveryAttempt.provider_used).all()
    
    provider_stats = {
        (p[0] or "unknown"): p[1] for p in provider_counts
    }
    
    return {
        "total_payments_count": total_txns,
        "total_revenue": total_revenue,
        "revenue_at_risk": total_risk,
        "revenue_recovered": total_recovered,
        "total_refunds": total_refunds,
        "recovery_rate": (total_recovered / total_risk * 100) if total_risk > 0 else 0,
        "successful_actions": success_count,
        "escalations": escalated_count,
        "stopped_automations": stopped_count,
        "ml_predictions": ml_predictions_count,
        "ai_recommendations": ai_recommendations_count,
        "policy_allowed": policy_allowed,
        "policy_denied": policy_denied,
        "gateway_executions": gateway_executions,
        "unknown_transactions": unknown_transactions,
        "provider_stats": provider_stats
    }
