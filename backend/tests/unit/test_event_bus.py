import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.event_bus import EventBus
from app.schemas.events import RecoveryEvent

@pytest.fixture
def mock_redis_sync():
    with patch("redis.from_url") as mock_from_url:
        mock_instance = MagicMock()
        mock_from_url.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_aioredis():
    with patch("redis.asyncio.from_url") as mock_aio_from_url:
        mock_instance = AsyncMock()
        mock_pubsub = AsyncMock()
        # pubsub() is a synchronous method that returns the pubsub object
        mock_instance.pubsub = MagicMock(return_value=mock_pubsub)
        mock_aio_from_url.return_value = mock_instance
        yield mock_instance, mock_pubsub

@pytest.mark.anyio
async def test_event_bus_subscribe_unsubscribe(mock_redis_sync, mock_aioredis):
    # Setup
    mock_aio_instance, mock_pubsub = mock_aioredis
    
    # Initialize EventBus
    bus = EventBus()
    
    # Subscribe
    queue = await bus.subscribe("txn_123")
    
    # Assertions
    assert isinstance(queue, asyncio.Queue)
    mock_pubsub.subscribe.assert_called_once_with("recovery_events:txn_123")
    assert hasattr(queue, "_reader_task")
    assert not queue._reader_task.done()
    
    # Unsubscribe
    bus.unsubscribe("txn_123", queue)
    
    # Allow event loop to process cancellation
    await asyncio.sleep(0)
    
    # Task should be cancelled
    assert queue._reader_task.cancelled() or queue._reader_task.done()

def test_event_bus_publish(mock_redis_sync):
    bus = EventBus()
    
    event = RecoveryEvent(
        transaction_id="txn_456",
        event_type="TEST_EVENT",
        data={"foo": "bar"}
    )
    
    bus.publish(event)
    
    mock_redis_sync.publish.assert_called_once()
    args, kwargs = mock_redis_sync.publish.call_args
    assert args[0] == "recovery_events:txn_456"
    assert "TEST_EVENT" in args[1]
    assert "txn_456" in args[1]
