from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.services.ml_service import ml_service
from app.agents.diagnosis_agent import diagnosis_agent
from app.schemas.agent_schema import DiagnosisResponse
from app.database import engine, Base
from app.models import db_models
from app.api.router import router as api_router

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RecoverAI API",
    description="Autonomous Revenue Recovery Agent",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "message": "RecoverAI backend is running."}

@app.get("/api/transactions")
def get_transactions():
    """Mock endpoint to return transactions."""
    return {"data": []}
    
@app.post("/api/diagnose", response_model=DiagnosisResponse)
def diagnose_transaction(transaction: dict):
    """
    Given a transaction dictionary, predict recovery probability 
    and get an AI diagnosis & recommended action.
    """
    # 1. Get ML probability
    prob = ml_service.predict_recovery_probability(transaction)
    
    # 2. Get Agent diagnosis
    diagnosis = diagnosis_agent.diagnose_transaction(transaction, prob)
    
    return diagnosis