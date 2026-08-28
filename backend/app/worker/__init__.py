from .celery_app import celery_app
from . import tasks

__all__ = ["celery_app"]
