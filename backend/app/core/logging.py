import logging
import json
import contextvars
from datetime import datetime, timezone
from typing import Any, Dict
from app.config import settings

# Context variables for tracing
request_id_var = contextvars.ContextVar("request_id", default=None)
correlation_id_var = contextvars.ContextVar("correlation_id", default=None)

# Keys that should never be logged
SENSITIVE_KEYS = {
    "merchant_api_key",
    "webhook_secret",
    "password",
    "token",
    "authorization",
    "razorpay_signature",
    "api_key",
    "x-api-key"
}

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": settings.SERVICE_NAME,
            "environment": settings.ENVIRONMENT,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context vars if present
        req_id = request_id_var.get()
        if req_id:
            log_obj["request_id"] = req_id
            
        corr_id = correlation_id_var.get()
        if corr_id:
            log_obj["correlation_id"] = corr_id

        # Merge extra fields
        if hasattr(record, "extra_context") and isinstance(record.extra_context, dict):
            for k, v in record.extra_context.items():
                if k.lower() in SENSITIVE_KEYS:
                    log_obj[k] = "***REDACTED***"
                else:
                    log_obj[k] = v
                    
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)

def setup_logging():
    logger = logging.getLogger()
    
    # Set level based on config
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    
    # Remove existing handlers to prevent duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    formatter = JSONFormatter()
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Silence extremely noisy third-party loggers if needed
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

# Expose a default logger for convenience, though `logging.getLogger(__name__)` is preferred
logger = logging.getLogger("recoverai")
