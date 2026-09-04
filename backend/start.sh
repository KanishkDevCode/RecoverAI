#!/bin/bash
celery -A app.worker.celery_app worker -Q celery,high_priority,reconciliation --loglevel=info --concurrency=1 &
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port $PORT
