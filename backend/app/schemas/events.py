import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class RecoveryEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str
    data: Dict[str, Any]

class PaymentFailedData(BaseModel):
    amount: float
    currency: str
    failure_code: str
    failure_reason: Optional[str]

class MLPredictionData(BaseModel):
    probability: float
    features_used: int

class AIRecommendationData(BaseModel):
    diagnosis: str
    recommended_action: str
    confidence: float

class PolicyDecisionData(BaseModel):
    is_allowed: bool
    final_action: str
    reason: str
    hard_limit_enforced: bool

class StateChangeData(BaseModel):
    previous_state: str
    new_state: str
    reason: str

class GatewayResultData(BaseModel):
    action_executed: str
    status: str
    message: str

class RecoveryCompleteData(BaseModel):
    outcome: str
    net_value_recovered: float
