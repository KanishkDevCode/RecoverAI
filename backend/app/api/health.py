from fastapi import APIRouter, Response, status
from sqlalchemy.orm import Session
from fastapi import Depends
import redis
from app.database import get_db
from app.config import settings
from app.core.logging import logger

router = APIRouter()

@router.get("/live", tags=["Health"])
def liveness_check():
    """
    Returns 200 OK if the FastAPI process is running.
    Does not check dependencies (DB/Redis).
    """
    return {"status": "alive"}

@router.get("/ready", tags=["Health"])
def readiness_check(response: Response, db: Session = Depends(get_db)):
    """
    Returns 200 OK if the service and its dependencies (DB, Redis) are healthy.
    Otherwise returns 503 Service Unavailable.
    """
    health_status = {
        "status": "ready",
        "database": "unknown",
        "redis": "unknown"
    }
    
    is_ready = True
    
    # Check Database
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        health_status["database"] = "healthy"
    except Exception as e:
        logger.error(f"Readiness check failed - Database error: {e}")
        health_status["database"] = "unhealthy"
        is_ready = False
        
    # Check Redis
    if settings.CELERY_BROKER_URL:
        try:
            r = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=1)
            r.ping()
            health_status["redis"] = "healthy"
        except Exception as e:
            logger.error(f"Readiness check failed - Redis error: {e}")
            health_status["redis"] = "unhealthy"
            is_ready = False
            
    if not is_ready:
        health_status["status"] = "not_ready"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return health_status
