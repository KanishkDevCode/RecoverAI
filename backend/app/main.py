from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, SessionLocal
from app.api.router import router as api_router
from app.services.reconciliation import reconcile_unknown_attempts, reconcile_orphaned_attempts, reconcile_stuck_refunds
from app.api.middleware import RequestIDMiddleware
from app.config import settings
from app.services.logger import setup_logging
import asyncio
import logging
from contextlib import asynccontextmanager

setup_logging()

async def reconciliation_worker():
    timeout = settings.UNKNOWN_RECONCILIATION_TIMEOUT_SECONDS
    while True:
        try:
            db = SessionLocal()
            try:
                reconcile_orphaned_attempts(db)
                reconcile_unknown_attempts(db)
                reconcile_stuck_refunds(db)
            finally:
                db.close()
        except Exception as e:
            logging.error(f"Reconciliation worker error: {e}")
            
        await asyncio.sleep(timeout)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    worker_task = asyncio.create_task(reconciliation_worker())
    yield
    # Shutdown
    worker_task.cancel()

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