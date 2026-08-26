import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Tuple
from app.schemas.events import RecoveryEvent

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        # Maps transaction_id -> list of (queue, loop)
        self.subscribers: Dict[str, List[Tuple[asyncio.Queue, asyncio.AbstractEventLoop]]] = defaultdict(list)

    async def subscribe(self, transaction_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        self.subscribers[transaction_id].append((queue, loop))
        logger.info(f"Subscribed to events for txn: {transaction_id}")
        return queue

    def unsubscribe(self, transaction_id: str, queue: asyncio.Queue):
        if transaction_id in self.subscribers:
            self.subscribers[transaction_id] = [
                (q, loop) for (q, loop) in self.subscribers[transaction_id] if q is not queue
            ]
            if not self.subscribers[transaction_id]:
                del self.subscribers[transaction_id]
            logger.info(f"Unsubscribed from events for txn: {transaction_id}")

    def publish(self, event: RecoveryEvent):
        """Called by synchronous orchestrator."""
        logger.info(f"Publishing event {event.event_type} for txn: {event.transaction_id}")
        if event.transaction_id in self.subscribers:
            for queue, loop in self.subscribers[event.transaction_id]:
                try:
                    if loop.is_running():
                        loop.call_soon_threadsafe(queue.put_nowait, event)
                except Exception as e:
                    logger.error(f"Error publishing event {event.event_type} to {event.transaction_id}: {e}")

event_bus = EventBus()
