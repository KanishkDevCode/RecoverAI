import os
import hmac
import hashlib
import json
import urllib.request
from dotenv import load_dotenv

# Load the secret from .env, or use the default development one
load_dotenv(dotenv_path="backend/.env")
webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_456")

# The public URL provided by localhost.run
WEBHOOK_URL = "http://127.0.0.1:8000/api/v1/webhooks/gateway"

# 1. Create a fake Razorpay payment.failed payload
payload = {
    "entity": "event",
    "account_id": "acc_1234567890",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_TEST12345",
                "entity": "payment",
                "amount": 10000,
                "currency": "INR",
                "status": "failed",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Payment failed due to simulated bank timeout",
                "error_source": "bank",
                "error_step": "payment_authorization",
                "error_reason": "payment_failed",
                "contact": "+919999999999",
                "email": "test@example.com"
            }
        }
    },
    "created_at": 1700000000
}

payload_body = json.dumps(payload, separators=(',', ':'))

# 2. Cryptographically sign it using HMAC SHA256
signature = hmac.new(
    webhook_secret.encode('utf-8'),
    payload_body.encode('utf-8'),
    hashlib.sha256
).hexdigest()

print("Simulating Razorpay Webhook...")
print("URL: " + WEBHOOK_URL)
print("Signature: " + signature)

# 3. Fire it through the internet tunnel
req = urllib.request.Request(
    WEBHOOK_URL,
    data=payload_body.encode('utf-8'),
    headers={
        'Content-Type': 'application/json',
        'X-Razorpay-Signature': signature,
        'X-Razorpay-Event-Id': 'evt_TEST123456789'
    },
    method='POST'
)

try:
    with urllib.request.urlopen(req) as response:
        print("Success! FastAPI responded with: " + str(response.getcode()))
        print("Switch to VS Code and watch Terminal 1 (uvicorn) and Terminal 2 (celery)!")
except urllib.error.HTTPError as e:
    print("Failed! FastAPI rejected it with: " + str(e.code) + " - " + e.reason)
except Exception as e:
    print("Failed to connect: " + str(e))
