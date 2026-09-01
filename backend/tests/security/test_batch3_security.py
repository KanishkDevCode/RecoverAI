import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_missing_api_key_rejected():
    response = client.post("/api/v1/payments", json={})
    assert response.status_code == 403
    assert "missing" in response.json()["detail"].lower()

def test_invalid_api_key_rejected():
    response = client.post("/api/v1/payments", json={}, headers={"X-API-Key": "wrong_key"})
    assert response.status_code == 403
    assert "invalid api key" in response.json()["detail"].lower()

def test_valid_api_key_accepted():
    # It might return 422 because of missing body fields, but auth succeeded.
    response = client.post("/api/v1/payments", json={}, headers={"X-API-Key": settings.MERCHANT_API_KEY})
    assert response.status_code == 422 # Validation error for PaymentCreateRequest

def test_legacy_endpoint_removed():
    response = client.get("/api/transactions")
    assert response.status_code == 404

    response = client.post("/api/diagnose", json={})
    assert response.status_code == 404

def test_request_id_generation():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert "x-request-id" in response.headers

def test_request_id_propagation():
    custom_id = "req_custom_12345"
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id

def test_rate_limiting(monkeypatch):
    import app.api.rate_limiter
    monkeypatch.setattr(app.api.rate_limiter, "MAX_REQUESTS_PER_WINDOW", 10)
    
    from app.api.rate_limiter import RATE_LIMITS
    RATE_LIMITS.clear()
    
    # Make multiple requests to trigger rate limit (10 allowed)
    for i in range(12):
        resp = client.post("/api/v1/payments", json={}, headers={"X-API-Key": settings.MERCHANT_API_KEY})
        if resp.status_code == 429:
            assert i >= 10
            break
    else:
        RATE_LIMITS.clear()
        pytest.fail("Rate limit was not triggered")
    
    RATE_LIMITS.clear()

def test_system_reconcile_restricted_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    response = client.post("/api/v1/system/reconcile", headers={"X-API-Key": settings.MERCHANT_API_KEY})
    assert response.status_code == 403
    assert "disabled in production" in response.json()["detail"].lower()
    
def test_production_missing_secret_fails_closed():
    from app.config import Settings
    
    os.environ["ENVIRONMENT"] = "production"
    
    # Needs a mock DATABASE_URL to pass the database check so we can test the other secrets
    # The new rule requires a non-sqlite database URL in production
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
        
    with pytest.raises(ValueError) as excinfo:
        Settings()
    assert "DATABASE_URL must be set to a non-SQLite database in production" in str(excinfo.value)
    
    os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
    
    if "MERCHANT_API_KEY" in os.environ:
        del os.environ["MERCHANT_API_KEY"]
    if "WEBHOOK_SECRET" in os.environ:
        del os.environ["WEBHOOK_SECRET"]
    if "CORS_ALLOWED_ORIGINS" in os.environ:
        del os.environ["CORS_ALLOWED_ORIGINS"]
    if "OBSERVABILITY_API_KEY" in os.environ:
        del os.environ["OBSERVABILITY_API_KEY"]
    if "CELERY_BROKER_URL" in os.environ:
        del os.environ["CELERY_BROKER_URL"]
        
    with pytest.raises(ValueError) as excinfo:
        Settings()
    
    assert "MERCHANT_API_KEY must be set in production" in str(excinfo.value)
    
    os.environ["MERCHANT_API_KEY"] = "prod_key"
    with pytest.raises(ValueError) as excinfo:
        Settings()
    assert "WEBHOOK_SECRET must be set in production" in str(excinfo.value)
    
    os.environ["WEBHOOK_SECRET"] = "prod_webhook_key"
    with pytest.raises(ValueError) as excinfo:
        Settings()
    assert "OBSERVABILITY_API_KEY must be set in production" in str(excinfo.value)
    
    os.environ["OBSERVABILITY_API_KEY"] = "prod_obs_key"
    with pytest.raises(ValueError) as excinfo:
        Settings()
    assert "CELERY_BROKER_URL must be explicitly set" in str(excinfo.value)

    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
    with pytest.raises(ValueError) as excinfo:
        Settings()
    assert "CORS_ALLOWED_ORIGINS must be explicitly set" in str(excinfo.value)
    
    os.environ["CORS_ALLOWED_ORIGINS"] = "*"
    with pytest.raises(ValueError) as excinfo:
        Settings()
    assert "cannot be '*'" in str(excinfo.value)
    
    os.environ["CORS_ALLOWED_ORIGINS"] = "https://example.com"
    # Now it should succeed
    s = Settings()
    assert s.ENVIRONMENT == "production"
    
    # Restore defaults so other tests don't break
    os.environ["ENVIRONMENT"] = "development"
    os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:5173"
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
