import pytest
from fastapi.testclient import TestClient
import uuid
import os
import redis
from unittest.mock import patch, MagicMock

# Ensure required env vars are set for testing
os.environ["ENVIRONMENT"] = "production"
os.environ["OBSERVABILITY_API_KEY"] = "test-obs-key"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test" # Just for test import success
os.environ["MERCHANT_API_KEY"] = "test-key"
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["CELERY_BROKER_URL"] = "memory://"

from app.main import app

client = TestClient(app)

def test_request_id_generation():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert "x-correlation-id" in response.headers
    assert response.headers["x-request-id"].startswith("req_")
    assert response.headers["x-correlation-id"].startswith("corr_")

def test_request_id_reuse():
    test_req_id = f"req_{uuid.uuid4().hex}"
    test_corr_id = f"corr_{uuid.uuid4().hex}"
    
    response = client.get("/api/v1/health/live", headers={
        "X-Request-ID": test_req_id,
        "X-Correlation-ID": test_corr_id
    })
    
    assert response.status_code == 200
    assert response.headers["x-request-id"] == test_req_id
    assert response.headers["x-correlation-id"] == test_corr_id

def test_liveness_probe():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}

@patch("app.api.health.redis.Redis.from_url")
def test_readiness_probe_healthy(mock_redis):
    # Mock redis ping success
    mock_r = MagicMock()
    mock_redis.return_value = mock_r
    
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "healthy"
    assert data["redis"] == "healthy"

@patch("app.api.health.redis.Redis.from_url")
def test_readiness_probe_redis_down(mock_redis):
    # Mock redis ping failure
    mock_redis.side_effect = redis.ConnectionError("Connection refused")
    
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["database"] == "healthy"
    assert data["redis"] == "unhealthy"

def test_metrics_protected():
    response = client.get("/api/v1/metrics")
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid Observability API Key"

def test_metrics_with_valid_key():
    from app.config import settings
    response = client.get("/api/v1/metrics", headers={"X-Observability-API-Key": settings.OBSERVABILITY_API_KEY})
    assert response.status_code == 200
    data = response.json()
    assert "recovery_attempts_unknown" in data
    assert "recovery_attempts_escalated" in data
    assert "webhook_events_failed_permanently" in data
    assert "recovery_attempts_stuck_executing" in data

def test_global_exception_handler():
    # Force a 500 error by causing a routing exception or we can just mock an endpoint
    from fastapi import APIRouter
    test_router = APIRouter()
    @test_router.get("/trigger_500")
    def trigger_500():
        raise RuntimeError("Simulated internal crash")
    
    app.include_router(test_router)
    
    fresh_client = TestClient(app, raise_server_exceptions=False)
    response = fresh_client.get("/trigger_500")
    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "Internal server error"
    assert "request_id" in data
    assert "Simulated internal crash" not in response.text
