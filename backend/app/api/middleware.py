import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.logging import request_id_var, correlation_id_var

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID")
        if not req_id:
            req_id = f"req_{uuid.uuid4().hex}"
            
        corr_id = request.headers.get("X-Correlation-ID")
        if not corr_id:
            corr_id = f"corr_{uuid.uuid4().hex}"
        
        # Set context variables
        token_req = request_id_var.set(req_id)
        token_corr = correlation_id_var.set(corr_id)
        
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Correlation-ID"] = corr_id
            return response
        finally:
            request_id_var.reset(token_req)
            correlation_id_var.reset(token_corr)
