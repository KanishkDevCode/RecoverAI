from pydantic import BaseModel, Field
from typing import Literal

class DiagnosisResponse(BaseModel):
    diagnosis: str = Field(..., description="A short explanation of the likely root cause.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the diagnosis and recommendation (0.0 to 1.0).")
    recommended_action: Literal[
        "RETRY_PAYMENT", 
        "WAIT_AND_RETRY", 
        "SEND_RECOVERY_MESSAGE", 
        "CREATE_ESCALATION", 
        "STOP_AUTOMATION", 
        "NO_ACTION"
    ] = Field(..., description="The recommended recovery action from the allowed set.")
    reason: str = Field(..., description="Reasoning for the recommended action based on evidence.")
    estimated_recovery_probability: float = Field(..., ge=0.0, le=1.0, description="The probability of recovery provided by the ML model.")
