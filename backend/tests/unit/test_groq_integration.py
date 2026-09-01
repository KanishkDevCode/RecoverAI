import pytest
from unittest.mock import patch, MagicMock
from app.agents.diagnosis_agent import DiagnosisAgent
from app.schemas.transaction import TransactionIncoming
from app.config import settings

@pytest.fixture
def mock_transaction():
    return TransactionIncoming(
        id="txn_test123",
        amount=1000,
        currency="USD",
        payment_status="failed",
        payment_method="card",
        customer_id="cust_456",
        failure_code="insufficient_funds",
        failure_reason="Not enough balance",
        retry_count=0
    )

def test_mock_provider_fallback(mock_transaction):
    """Scenario 1: AI_PROVIDER=mock should return deterministic mock response"""
    with patch("app.config.settings.LLM_PROVIDER", "mock"):
        agent = DiagnosisAgent()
        assert agent.mode == "mock"
        
        response = agent.diagnose_transaction(mock_transaction, 0.4)
        assert response.recommended_action == "SEND_RECOVERY_MESSAGE"
        assert "Mock diagnosis" in response.diagnosis

def test_groq_without_api_key_falls_back(mock_transaction):
    """Scenario 2: AI_PROVIDER=groq with no API key should fall back to mock (via ollama)"""
    with patch("app.config.settings.LLM_PROVIDER", "groq"), \
         patch("app.config.settings.GROQ_API_KEY", ""), \
         patch("urllib.request.urlopen") as mock_urlopen:
        
        # Make Ollama fail too so it falls to mock
        mock_urlopen.side_effect = Exception("Ollama timeout")
        agent = DiagnosisAgent()
        
        response = agent.diagnose_transaction(mock_transaction, 0.4)
        # Should have fallen back to mock inside diagnose_transaction
        assert response.recommended_action == "SEND_RECOVERY_MESSAGE"
        assert "Mock diagnosis" in response.diagnosis

def test_groq_exception_falls_back(mock_transaction):
    """Scenario 3: Groq API raises exception should fall back to mock (via ollama)"""
    with patch("app.config.settings.LLM_PROVIDER", "groq"), \
         patch("app.config.settings.GROQ_API_KEY", "fake_key"):
        agent = DiagnosisAgent()
        assert agent.mode == "groq"
        
        # Mock urllib.request.urlopen to raise URLError
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Network timeout")
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert response.recommended_action == "SEND_RECOVERY_MESSAGE"
            assert "Mock diagnosis" in response.diagnosis

def test_groq_invalid_json_falls_back(mock_transaction):
    """Scenario 4: Groq returns invalid JSON should fall back to mock"""
    with patch("app.config.settings.LLM_PROVIDER", "groq"), \
         patch("app.config.settings.GROQ_API_KEY", "fake_key"):
        agent = DiagnosisAgent()
        
        def mock_urlopen_side_effect(req, *args, **kwargs):
            if "groq.com" in req.full_url:
                mock_response = MagicMock()
                mock_response.read.return_value = b'{"invalid": json'
                mock_response.__enter__.return_value = mock_response
                return mock_response
            else:
                raise Exception("Ollama unavailable")

        with patch("urllib.request.urlopen", side_effect=mock_urlopen_side_effect):
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            assert response.recommended_action == "SEND_RECOVERY_MESSAGE"

def test_groq_unsupported_action_falls_back(mock_transaction):
    """Scenario 5: Groq returns unsupported action should fall back to mock due to Pydantic Validation"""
    with patch("app.config.settings.LLM_PROVIDER", "groq"), \
         patch("app.config.settings.GROQ_API_KEY", "fake_key"):
        agent = DiagnosisAgent()
        
        invalid_action_json = b'''{
            "choices": [{
                "message": {
                    "content": "{\\"diagnosis\\": \\"test\\", \\"confidence\\": 0.9, \\"recommended_action\\": \\"INVALID_ACTION\\", \\"reason\\": \\"test\\"}"
                }
            }]
        }'''
        
        def mock_urlopen_side_effect(req, *args, **kwargs):
            if "groq.com" in req.full_url:
                mock_response = MagicMock()
                mock_response.read.return_value = invalid_action_json
                mock_response.__enter__.return_value = mock_response
                return mock_response
            else:
                raise Exception("Ollama unavailable")
        
        with patch("urllib.request.urlopen", side_effect=mock_urlopen_side_effect):
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            # Pydantic validation fails -> Exception -> falls back to mock
            assert response.recommended_action == "SEND_RECOVERY_MESSAGE"
            assert "Mock diagnosis" in response.diagnosis

def test_groq_valid_response_accepted(mock_transaction):
    """Scenario 6: Groq returns valid structured response"""
    with patch("app.config.settings.LLM_PROVIDER", "groq"), \
         patch("app.config.settings.GROQ_API_KEY", "fake_key"):
        agent = DiagnosisAgent()
        
        valid_json = b'''{
            "choices": [{
                "message": {
                    "content": "{\\"diagnosis\\": \\"Customer has no money\\", \\"confidence\\": 0.95, \\"recommended_action\\": \\"RETRY_PAYMENT\\", \\"reason\\": \\"We will try again\\"}"
                }
            }]
        }'''
        
        def mock_urlopen_side_effect(req, *args, **kwargs):
            if "groq.com" in req.full_url:
                mock_response = MagicMock()
                mock_response.read.return_value = valid_json
                mock_response.__enter__.return_value = mock_response
                return mock_response
            else:
                raise Exception("Ollama unavailable")
                
        with patch("urllib.request.urlopen", side_effect=mock_urlopen_side_effect):
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            assert response.recommended_action == "RETRY_PAYMENT"
            assert response.diagnosis == "Customer has no money"
            assert response.confidence == 0.95
            assert response.estimated_recovery_probability == 0.4
