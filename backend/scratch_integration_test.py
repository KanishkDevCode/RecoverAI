import asyncio
import json
import websockets
import httpx
from datetime import datetime

async def trigger_payment(payment_id):
    api_url = "http://127.0.0.1:8000/api/v1"
    headers = {"X-API-Key": "test_secret_key_123", "Content-Type": "application/json"}
    
    payment_payload = {
        "id": payment_id,
        "customer_id": "cust_123",
        "amount": 900.0,
        "currency": "INR",
        "mode": "test",
        "payment_method": "card",
        "developer_overrides": {
            "failure_code": "bank_timeout",
            "failure_reason": "Timeout",
            "retry_count": 0
        }
    }
    
    print(f"Triggering payment: {payment_payload['id']}")
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{api_url}/payments", json=payment_payload, headers=headers)
        print(f"Payment response: {response.status_code}")
        assert response.status_code == 200

async def test_integration():
    payment_id = f"txn_test_{int(datetime.now().timestamp()*1000)}"
    ws_url = f"ws://127.0.0.1:8000/api/v1/ws/recovery/{payment_id}?api_key=test_secret_key_123"
    
    print(f"Connecting to WebSocket: {ws_url}")
    
    try:
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            print("WebSocket connected. Waiting 2 seconds for Redis subscription...")
            await asyncio.sleep(2)
            
            # Start the payment AFTER connecting to the websocket
            asyncio.create_task(trigger_payment(payment_id))
            
            events_received = 0
            while events_received < 7:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    event = json.loads(msg)
                    print(f"Received Event: {event['event_type']} -> {event['data']}")
                    events_received += 1
                except asyncio.TimeoutError:
                    print(f"Timeout waiting for events. Received {events_received}/7")
                    break
    except Exception as e:
        print(f"WebSocket Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_integration())
