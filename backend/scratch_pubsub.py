import asyncio
import redis
import redis.asyncio as aioredis
import json

async def test_pubsub():
    async_redis = aioredis.from_url("redis://localhost:6379/0")
    pubsub = async_redis.pubsub()
    await pubsub.subscribe("test_channel")
    
    sync_redis = redis.from_url("redis://localhost:6379/0")
    
    async def reader():
        async for message in pubsub.listen():
            print(f"Received: {message}")
            if message["type"] == "message":
                break
                
    task = asyncio.create_task(reader())
    await asyncio.sleep(1) # wait for subscribe
    
    print("Publishing...")
    sync_redis.publish("test_channel", json.dumps({"hello": "world"}))
    
    await task
    await pubsub.close()
    await async_redis.aclose() if hasattr(async_redis, 'aclose') else await async_redis.close()

if __name__ == "__main__":
    asyncio.run(test_pubsub())
