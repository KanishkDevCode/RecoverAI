from fastapi import APIRouter, Depends, BackgroundTasks
from app.api.dependencies import get_api_key
from app.api.rate_limiter import rate_limit
from app.schemas.transaction import TransactionIncoming
from app.api.payments import run_orchestrator_bg

router = APIRouter()

@router.post("/recovery/process", dependencies=[Depends(rate_limit)])
def process_recovery(
    transaction: TransactionIncoming, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    """
    Triggers the recovery orchestration loop for a given transaction.
    Requires a valid transaction payload according to TransactionIncoming schema.
    Runs asynchronously in a background thread and returns immediately.
    """
    background_tasks.add_task(run_orchestrator_bg, transaction)
    return {"transaction_id": transaction.id, "status": "PROCESSING"}
