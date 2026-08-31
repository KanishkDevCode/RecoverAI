import asyncio
import logging
import json
import redis
import redis.asyncio as aioredis
from typing import Dict, List, Tuple
from app.schemas.events import RecoveryEvent
from app.config import settings

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        # Synchronous client for Celery to publish
        self.sync_redis = None
        if settings.CELERY_BROKER_URL:
            # We assume CELERY_BROKER_URL is a Redis URL
            self.sync_redis = redis.from_url(settings.CELERY_BROKER_URL)
            
        # Asynchronous client for FastAPI to subscribe
        self._async_redis = None

    async def get_async_redis(self):
        if not self._async_redis:
            self._async_redis = aioredis.from_url(settings.CELERY_BROKER_URL)
        return self._async_redis

    async def subscribe(self, transaction_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        redis_conn = await self.get_async_redis()
        pubsub = redis_conn.pubsub()
        channel_name = f"recovery_events:{transaction_id}"
        await pubsub.subscribe(channel_name)
        
        logger.info(f"Subscribed to Redis channel: {channel_name}")
        
        async def reader_task():
            try:
                logger.info(f"Reader task started for {channel_name}")
                async for message in pubsub.listen():
                    logger.info(f"Redis message received: {message}")
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            event = RecoveryEvent(**data)
                            await queue.put(event)
                        except Exception as e:
                            logger.error(f"Error parsing event from Redis: {e}")
            except asyncio.CancelledError:
                await pubsub.unsubscribe(channel_name)
                await pubsub.close()
                logger.info(f"Unsubscribed from Redis channel: {channel_name}")
                
        # Store the task so we can cancel it on unsubscribe
        task = asyncio.create_task(reader_task())
        
        # Attach the task and pubsub to the queue object as a hacky way to keep track of it
        # without changing the return signature
        queue._reader_task = task
        queue._pubsub = pubsub
        return queue

    def unsubscribe(self, transaction_id: str, queue: asyncio.Queue):
        if hasattr(queue, '_reader_task'):
            queue._reader_task.cancel()
        logger.info(f"Unsubscription initiated for txn: {transaction_id}")

    def publish(self, event: RecoveryEvent):
        """Called by synchronous orchestrator."""
        logger.info(f"Publishing event {event.event_type} for txn: {event.transaction_id}")
        if self.sync_redis:
            channel_name = f"recovery_events:{event.transaction_id}"
            try:
                self.sync_redis.publish(channel_name, event.model_dump_json())
            except Exception as e:
                logger.error(f"Error publishing to Redis channel {channel_name}: {e}")
        else:
            logger.error(f"Cannot publish event {event.event_type}: Redis not configured")

event_bus = EventBus()

