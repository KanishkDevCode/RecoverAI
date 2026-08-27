import os
from fastapi import HTTPException, Security, Query
from fastapi.security.api_key import APIKeyHeader
from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise HTTPException(status_code=403, detail="API Key header (X-API-Key) missing")
    
    if api_key_header != settings.MERCHANT_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key_header

async def get_ws_api_key(api_key: str = Query(None)):
    if not api_key:
        raise HTTPException(status_code=403, detail="API Key missing in query")
    
    if api_key != settings.MERCHANT_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key
