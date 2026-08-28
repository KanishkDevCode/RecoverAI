from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, SessionLocal
from app.api.router import router as api_router
from app.api.middleware import RequestIDMiddleware
from app.config import settings
from app.services.logger import setup_logging
import logging
from contextlib import asynccontextmanager

setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup (Reconciliation is now handled by Celery Beat)
    yield
    # Shutdown

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RecoverAI API",
    description="Autonomous Revenue Recovery Agent",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
origins = [origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)

app.include_router(api_router)

@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "message": "RecoverAI backend is running."}