from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.dependencies import get_api_key
from app.models.db_models import Transaction
from app.services.money import to_major_units

router = APIRouter()

@router.get("/customers")
def get_customers(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Returns derived customers from transactions."""
    txns = db.query(Transaction).all()
    customers = {}
    
    for txn in txns:
        cid = txn.customer_id
        if cid not in customers:
            customers[cid] = {
                "customer_id": cid,
                "payments": 0,
                "revenue": 0.0,
                "recovered": 0.0
            }
        
        customers[cid]["payments"] += 1
        if txn.status == "success":
            customers[cid]["revenue"] += to_major_units(txn.amount)
        elif txn.recovery_status == "SUCCEEDED":
            customers[cid]["revenue"] += to_major_units(txn.amount)
            customers[cid]["recovered"] += to_major_units(txn.amount)
            
    return list(customers.values())
