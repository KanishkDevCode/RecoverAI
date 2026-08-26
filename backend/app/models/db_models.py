from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, index=True) # e.g. txn_...
    customer_id = Column(String, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    status = Column(String, default="failed") # e.g. failed, recovered, escalated
    failure_code = Column(String)
    failure_reason = Column(String)
    refund_status = Column(String, nullable=True) # REFUND_REQUESTED, REFUND_PROCESSING, REFUNDED
    refund_amount = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class RecoveryAttempt(Base):
    __tablename__ = "recovery_attempts"

    id = Column(String, primary_key=True, index=True)
    transaction_id = Column(String, ForeignKey("transactions.id"), index=True)
    ml_probability = Column(Float)
    agent_diagnosis = Column(Text)
    agent_confidence = Column(Float)
    agent_action = Column(String)
    policy_decision = Column(String) # ALLOWED, DENIED
    policy_reason = Column(String)
    executed_action = Column(String) # What was actually executed
    outcome_status = Column(String) # SUCCESS, FAILURE, PENDING, NONE
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    transaction_id = Column(String, ForeignKey("transactions.id"), index=True)
    decision_id = Column(String, nullable=True) # Could link to a RecoveryAttempt.id
    event_type = Column(String, index=True) # e.g. DETECTION, DIAGNOSIS, POLICY_GATE, EXECUTION
    previous_state = Column(String, nullable=True)
    new_state = Column(String, nullable=True)
    reasoning = Column(Text, nullable=True) # JSON or Text describing the 'why'

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    
    key = Column(String, primary_key=True, index=True)
    attempt_id = Column(String, nullable=True, index=True)
    status = Column(String, default="PENDING")
    external_reference = Column(String, nullable=True)
    result_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
