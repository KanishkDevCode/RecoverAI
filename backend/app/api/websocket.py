import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.api.dependencies import get_ws_api_key
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/ws/recovery/{transaction_id}")
async def websocket_recovery(
    websocket: WebSocket, 
    transaction_id: str,
    api_key: str = Depends(get_ws_api_key)
):
    await websocket.accept()
    queue = await event_bus.subscribe(transaction_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_text(event.model_dump_json())
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for txn: {transaction_id}")
    finally:
        event_bus.unsubscribe(transaction_id, queue)
