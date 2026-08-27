import time
from fastapi import Request, HTTPException

import os

# Simple in-memory token bucket / window for development
# Keyed by IP or API Key
RATE_LIMITS = {}
WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = int(os.getenv("RATE_LIMIT", "10000")) # High for test suite by default

async def rate_limit(request: Request):
    """
    Lightweight rate limiting dependency.
    Fails closed (HTTP 429) if exceeded.
    Does not interfere with idempotency because 429 happens before idempotency logic.
    """
    client_ip = request.client.host if request.client else "unknown"
    api_key = request.headers.get("X-API-Key", "none")
    
    # We use a combined key to limit per-client-per-apikey
    key = f"{client_ip}_{api_key}"
    
    current_time = time.time()
    
    if key not in RATE_LIMITS:
        RATE_LIMITS[key] = {"count": 1, "start_time": current_time}
        return
        
    record = RATE_LIMITS[key]
    if current_time - record["start_time"] > WINDOW_SECONDS:
        # Reset window
        record["count"] = 1
        record["start_time"] = current_time
    else:
        record["count"] += 1
        if record["count"] > MAX_REQUESTS_PER_WINDOW:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
