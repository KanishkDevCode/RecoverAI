import os
from celery import Celery
from app.config import settings

celery_app = Celery(
    "recoverai_worker",
    broker=settings.CELERY_BROKER_URL,
    include=["app.worker.tasks"]
)

# Optional result backend is NOT enabled as per architectural requirements.
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    
    # Task Routes
    task_routes={
        "app.worker.tasks.process_orchestrator": {"queue": "high_priority"},
        "app.worker.tasks.process_webhook": {"queue": "high_priority"},
        "app.worker.tasks.reconcile_all_pending": {"queue": "reconciliation"},
    },
    
    # Do not acknowledge tasks until they are finished executing (worker crash safety)
    task_acks_late=True,
    
    # Only deliver task once to worker (prefetch)
    worker_prefetch_multiplier=1,
)

# Celery Beat Schedule
celery_app.conf.beat_schedule = {
    "reconciliation-sweep-every-1-minute": {
        "task": "app.worker.tasks.reconcile_all_pending",
        "schedule": 60.0,
    }
}
