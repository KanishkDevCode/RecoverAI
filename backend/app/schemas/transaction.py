from pydantic import BaseModel, Field, constr, confloat, model_validator, ConfigDict
from typing import Optional
from enum import Enum
from datetime import datetime

class CurrencyEnum(str, Enum):
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"

class PaymentStatusEnum(str, Enum):
    FAILED = "failed"
    PENDING = "pending"
    SUCCESS = "success"

class PaymentMethodEnum(str, Enum):
    CARD = "card"
    UPI = "upi"
    NETBANKING = "netbanking"
    WALLET = "wallet"

class TransactionIncoming(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    id: constr(min_length=1, max_length=100) = Field(..., description="Transaction ID")
    customer_id: constr(min_length=1, max_length=100)
    amount: confloat(gt=0) = Field(..., description="Transaction amount (must be strictly positive)")
    currency: CurrencyEnum = Field(default=CurrencyEnum.INR)
    payment_status: PaymentStatusEnum
    payment_method: Optional[PaymentMethodEnum] = None
    failure_code: Optional[constr(max_length=50)] = None
    failure_reason: Optional[constr(max_length=1000)] = Field(None, description="Untrusted failure reason from external gateway")
    retry_count: int = Field(default=0, ge=0, description="Number of times this transaction has been retried")
    timestamp: Optional[datetime] = None

    @model_validator(mode='before')
    @classmethod
    def normalize_id(cls, data: any) -> any:
        if isinstance(data, dict):
            # Normalize transaction_id to id
            if "transaction_id" in data:
                if "id" not in data:
                    data["id"] = data["transaction_id"]
                data.pop("transaction_id")
        return data

class DeveloperOverrides(BaseModel):
    failure_code: Optional[constr(max_length=50)] = None
    failure_reason: Optional[constr(max_length=1000)] = None
    retry_count: Optional[int] = Field(default=0, ge=0)

class PaymentCreateRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')
    
    id: constr(min_length=1, max_length=100) = Field(..., description="Transaction ID")
    customer_id: constr(min_length=1, max_length=100)
    amount: confloat(gt=0) = Field(..., description="Transaction amount")
    currency: CurrencyEnum = Field(default=CurrencyEnum.INR)
    payment_method: PaymentMethodEnum
    mode: str = Field("live", description="live or test mode")
    developer_overrides: Optional[DeveloperOverrides] = None
