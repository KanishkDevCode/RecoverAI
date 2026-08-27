import logging
import uuid
import contextvars

# Context variable for request ID
request_id_var = contextvars.ContextVar("request_id", default=None)

class RequestIDFilter(logging.Filter):
    def filter(self, record):
        req_id = request_id_var.get()
        record.request_id = req_id if req_id else "system"
        return True

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [req:%(request_id)s] %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDFilter())
    
    logger.addHandler(handler)
