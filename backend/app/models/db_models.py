from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, index=True) # e.g. txn_...
    customer_id = Column(String, index=True)
    amount = Column(Integer, nullable=False) # stored in minor units (e.g. paise)
    currency = Column(String, default="INR")
    status = Column(String, default="failed") # original payment status (e.g. failed, success)
    recovery_status = Column(String, default="NOT_STARTED") # e.g. NOT_STARTED, SUCCEEDED, FAILED
    failure_code = Column(String)
    failure_reason = Column(String)
    refund_status = Column(String, nullable=True) # REFUND_REQUESTED, REFUND_PROCESSING, REFUNDED
    refund_amount = Column(Integer, nullable=True) # stored in minor units (e.g. paise)
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
    provider_used = Column(String, nullable=True) # groq, ollama, mock, etc.
    latency_ms = Column(Integer, nullable=True) # end-to-end fallback chain latency
    version = Column(Integer, default=1, nullable=False) # For optimistic concurrency
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
    request_hash = Column(String, nullable=True)
    response_body = Column(Text, nullable=True)
    status_code = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    
    event_id = Column(String, primary_key=True, index=True)
    event_type = Column(String, index=True)
    transaction_id = Column(String, ForeignKey("transactions.id"), index=True, nullable=True)
    refund_id = Column(String, nullable=True)
    payload_hash = Column(String, index=True)
    payload = Column(Text)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processing_status = Column(String, default="PENDING") # PENDING, PROCESSED, FAILED, DUPLICATE, FAILED_PERMANENTLY
    retry_count = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
