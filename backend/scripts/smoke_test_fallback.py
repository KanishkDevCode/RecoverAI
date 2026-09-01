import os
import sys

# Ensure backend dir is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.diagnosis_agent import DiagnosisAgent
from app.schemas.transaction import TransactionIncoming
from app.config import settings

def run_test_scenario(scenario_name: str, test_mode: str, remove_groq_key: bool, remove_ollama_url: bool):
    print(f"\n{'='*50}")
    print(f"Running: {scenario_name}")
    print(f"{'='*50}")
    
    os.environ["LLM_PROVIDER"] = test_mode
    
    # Reload settings dynamically for the test (or just patch agent directly)
    original_mode = settings.LLM_PROVIDER
    original_groq = settings.GROQ_API_KEY
    original_ollama_url = os.environ.get("OLLAMA_BASE_URL")
    
    try:
        settings.LLM_PROVIDER = test_mode
        if remove_groq_key:
            settings.GROQ_API_KEY = ""
        
        if remove_ollama_url:
            os.environ["OLLAMA_BASE_URL"] = "http://invalid-url-to-force-failure:11434"
        
        agent = DiagnosisAgent()
        
        transaction = TransactionIncoming(
            id="txn_smoke_123",
            amount=5000,
            currency="USD",
            payment_status="failed",
            payment_method="card",
            customer_id="cust_001",
            failure_code="insufficient_funds",
            failure_reason="Not enough balance",
            retry_count=0
        )
        
        print(f"Mode Configured: {agent.mode}")
        print(f"Groq Key Present: {bool(agent.groq_api_key)}")
        print(f"Ollama URL: {agent.ollama_url}")
        
        print("\n--- Executing diagnose_transaction ---")
        response = agent.diagnose_transaction(transaction, 0.4)
        
        print("\n--- Result ---")
        print(f"Diagnosis: {response.diagnosis}")
        print(f"Action: {response.recommended_action}")
        print(f"Confidence: {response.confidence}")
        
    except Exception as e:
        print(f"Test failed with exception: {e}")
    finally:
        # Restore environment
        settings.LLM_PROVIDER = original_mode
        settings.GROQ_API_KEY = original_groq
        if original_ollama_url:
            os.environ["OLLAMA_BASE_URL"] = original_ollama_url
        else:
            os.environ.pop("OLLAMA_BASE_URL", None)


if __name__ == "__main__":
    print("Starting LLM Fallback Smoke Tests...")
    
    # Scenario A: Groq (if key exists, else Ollama, else Mock)
    # Testing auto mode without breaking things intentionally
    run_test_scenario(
        scenario_name="Scenario A: LLM_PROVIDER=auto (Should use Groq if key valid, else fallback)",
        test_mode="auto",
        remove_groq_key=False,
        remove_ollama_url=False
    )
    
    # Scenario B: Ollama fallback
    # Force Groq to fail by removing key
    run_test_scenario(
        scenario_name="Scenario B: Groq Key Missing -> Fallback to Ollama (or Mock if Ollama down)",
        test_mode="auto",
        remove_groq_key=True,
        remove_ollama_url=False
    )
    
    # Scenario C: Mock fallback
    # Force Groq to fail by removing key AND Ollama to fail by breaking URL
    run_test_scenario(
        scenario_name="Scenario C: Groq Missing AND Ollama Down -> Fallback to Mock",
        test_mode="auto",
        remove_groq_key=True,
        remove_ollama_url=True
    )
