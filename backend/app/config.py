import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./recoverai.db")
        self.CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        
        # Celery Configuration
        self.CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        self.CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
        
        # In development, we can fall back to a default key if not provided. 
        # In production, it MUST be provided via env.
        env_key = os.getenv("MERCHANT_API_KEY")
        if self.ENVIRONMENT == "development" and not env_key:
            self.MERCHANT_API_KEY = "test_secret_key_123"
        else:
            self.MERCHANT_API_KEY = env_key
            
        webhook_secret = os.getenv("WEBHOOK_SECRET")
        if self.ENVIRONMENT == "development" and not webhook_secret:
            self.WEBHOOK_SECRET = "test_webhook_secret_456"
        else:
            self.WEBHOOK_SECRET = webhook_secret
        
        timeout_str = os.getenv("UNKNOWN_RECONCILIATION_TIMEOUT_SECONDS", "60")
        try:
            self.UNKNOWN_RECONCILIATION_TIMEOUT_SECONDS = int(timeout_str)
        except ValueError:
            self.UNKNOWN_RECONCILIATION_TIMEOUT_SECONDS = 60
            
        pending_str = os.getenv("PENDING_ATTEMPT_TIMEOUT_SECONDS", "300")
        try:
            self.PENDING_ATTEMPT_TIMEOUT_SECONDS = int(pending_str)
        except ValueError:
            self.PENDING_ATTEMPT_TIMEOUT_SECONDS = 300

        self.validate()

    def validate(self):
        if self.ENVIRONMENT == "production":
            if not self.DATABASE_URL or self.DATABASE_URL.startswith("sqlite"):
                raise ValueError("SECURITY ERROR: DATABASE_URL must be set to a non-SQLite database in production.")
                
            if not self.MERCHANT_API_KEY:
                raise ValueError("SECURITY ERROR: MERCHANT_API_KEY must be set in production.")
                
            if not self.WEBHOOK_SECRET:
                raise ValueError("SECURITY ERROR: WEBHOOK_SECRET must be set in production.")
            
            if not os.getenv("CELERY_BROKER_URL"):
                raise ValueError("SECURITY ERROR: CELERY_BROKER_URL must be explicitly set in production.")
            
            if self.CELERY_TASK_ALWAYS_EAGER:
                raise ValueError("SECURITY ERROR: CELERY_TASK_ALWAYS_EAGER cannot be True in production.")
            
            # Explicit check against empty/missing in prod
            if not os.getenv("CORS_ALLOWED_ORIGINS"):
                raise ValueError("SECURITY ERROR: CORS_ALLOWED_ORIGINS must be explicitly set in production.")
                
            if self.CORS_ALLOWED_ORIGINS == "*":
                raise ValueError("SECURITY ERROR: CORS_ALLOWED_ORIGINS cannot be '*' in production.")
                
        if self.LLM_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            raise ValueError("CONFIGURATION ERROR: GEMINI_API_KEY must be set when LLM_PROVIDER is gemini.")

settings = Settings()
