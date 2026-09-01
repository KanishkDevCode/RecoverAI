import os
import sys

# Force LLM provider to groq
os.environ["LLM_PROVIDER"] = "groq"

# Add project root to path so 'app' is resolvable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.diagnosis_agent import DiagnosisAgent
from app.schemas.transaction import TransactionIncoming

def run_smoke_test():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("REAL_GROQ_SMOKE_TEST: FAILED")
        print("Reason: GROQ_API_KEY environment variable is not set.")
        sys.exit(1)
        
    print("Starting REAL_GROQ_SMOKE_TEST...")
    
    agent = DiagnosisAgent()
    if agent.mode != "groq":
        print("REAL_GROQ_SMOKE_TEST: FAILED")
        print(f"Reason: Agent initialized with mode '{agent.mode}' instead of 'groq'.")
        sys.exit(1)
        
    transaction = TransactionIncoming(
        id="txn_smoke_123",
        amount=1500,
        currency="USD",
        payment_status="failed",
        payment_method="card",
        customer_id="cust_smoke_456",
        failure_code="insufficient_funds",
        failure_reason="Customer has insufficient funds in their account",
        retry_count=0
    )
    
    try:
        response = agent.diagnose_transaction(transaction, ml_probability=0.85)
        
        # Verify it wasn't a mock response
        if "Mock diagnosis" in response.diagnosis:
            print("REAL_GROQ_SMOKE_TEST: FAILED")
            print("Reason: Agent silently fell back to mock diagnosis.")
            sys.exit(1)
            
        print("REAL_GROQ_SMOKE_TEST: PASSED")
        print(f"Provider: {agent.mode}")
        print(f"Recommended Action: {response.recommended_action}")
        print(f"Confidence: {response.confidence:.2f}")
        
    except Exception as e:
        print("REAL_GROQ_SMOKE_TEST: FAILED")
        print(f"Reason: Exception occurred during inference - {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run_smoke_test()
