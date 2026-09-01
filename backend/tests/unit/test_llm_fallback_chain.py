import pytest
from unittest.mock import patch, MagicMock
from app.agents.diagnosis_agent import DiagnosisAgent
from app.schemas.transaction import TransactionIncoming
from app.config import settings
from urllib.error import URLError

@pytest.fixture
def mock_transaction():
    return TransactionIncoming(
        id="txn_fallback_test",
        amount=5000,
        currency="USD",
        payment_status="failed",
        payment_method="card",
        customer_id="cust_789",
        failure_code="insufficient_funds",
        failure_reason="Not enough balance",
        retry_count=0
    )

def create_mock_response(content: bytes):
    mock_resp = MagicMock()
    mock_resp.read.return_value = content
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp

def test_mock_mode_only(mock_transaction):
    """Scenario 1: Mock mode - Groq/Ollama not called"""
    with patch("app.config.settings.LLM_PROVIDER", "mock"), \
         patch("urllib.request.urlopen") as mock_urlopen:
        agent = DiagnosisAgent()
        response = agent.diagnose_transaction(mock_transaction, 0.4)
        assert response.recommended_action == "SEND_RECOVERY_MESSAGE"
        assert "Mock diagnosis" in response.diagnosis
        mock_urlopen.assert_not_called()

def test_groq_success(mock_transaction):
    """Scenario 2: Groq success - Ollama/Mock not called"""
    with patch("app.config.settings.LLM_PROVIDER", "auto"), \
         patch("app.config.settings.GROQ_API_KEY", "valid_key"):
        agent = DiagnosisAgent()
        
        valid_json = b'''{"choices": [{"message": {"content": "{\\"diagnosis\\": \\"Groq works\\", \\"confidence\\": 0.9, \\"recommended_action\\": \\"RETRY_PAYMENT\\", \\"reason\\": \\"test\\"}"}}]}'''
        
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = create_mock_response(valid_json)
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert response.diagnosis == "Groq works"
            assert mock_urlopen.call_count == 1
            # Verify URL called was Groq
            called_req = mock_urlopen.call_args[0][0]
            assert "api.groq.com" in called_req.full_url

def test_groq_failure_ollama_success(mock_transaction):
    """Scenario 3: Groq fails -> Ollama succeeds"""
    with patch("app.config.settings.LLM_PROVIDER", "auto"), \
         patch("app.config.settings.GROQ_API_KEY", "valid_key"):
        agent = DiagnosisAgent()
        
        def mock_urlopen_side_effect(req, *args, **kwargs):
            if "groq.com" in req.full_url:
                raise URLError("Timeout")
            elif "11434" in req.full_url: # Ollama
                ollama_json = b'''{"message": {"content": "{\\"diagnosis\\": \\"Ollama works\\", \\"confidence\\": 0.8, \\"recommended_action\\": \\"WAIT_AND_RETRY\\", \\"reason\\": \\"test\\"}"}}'''
                return create_mock_response(ollama_json)
            raise ValueError("Unexpected URL")

        with patch("urllib.request.urlopen", side_effect=mock_urlopen_side_effect) as mock_urlopen:
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert response.diagnosis == "Ollama works"
            assert mock_urlopen.call_count == 2

def test_groq_failure_ollama_failure_mock_success(mock_transaction):
    """Scenario 4: Groq fails -> Ollama fails -> Mock succeeds"""
    with patch("app.config.settings.LLM_PROVIDER", "auto"), \
         patch("app.config.settings.GROQ_API_KEY", "valid_key"):
        agent = DiagnosisAgent()
        
        with patch("urllib.request.urlopen", side_effect=URLError("Network down")) as mock_urlopen:
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert "Mock diagnosis" in response.diagnosis
            assert mock_urlopen.call_count == 2 # 1 for Groq, 1 for Ollama

def test_missing_groq_key_ollama_success(mock_transaction):
    """Scenario 5: Missing Groq API key -> skip Groq -> Ollama succeeds"""
    with patch("app.config.settings.LLM_PROVIDER", "auto"), \
         patch("app.config.settings.GROQ_API_KEY", ""):
        agent = DiagnosisAgent()
        
        ollama_json = b'''{"message": {"content": "{\\"diagnosis\\": \\"Ollama only\\", \\"confidence\\": 0.8, \\"recommended_action\\": \\"WAIT_AND_RETRY\\", \\"reason\\": \\"test\\"}"}}'''
        
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = create_mock_response(ollama_json)
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert response.diagnosis == "Ollama only"
            assert mock_urlopen.call_count == 1
            assert "11434" in mock_urlopen.call_args[0][0].full_url # Verify it only called Ollama

def test_missing_groq_key_ollama_failure(mock_transaction):
    """Scenario 6: Missing Groq API key -> Ollama fails -> Mock succeeds"""
    with patch("app.config.settings.LLM_PROVIDER", "auto"), \
         patch("app.config.settings.GROQ_API_KEY", ""):
        agent = DiagnosisAgent()
        
        with patch("urllib.request.urlopen", side_effect=URLError("Ollama dead")) as mock_urlopen:
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert "Mock diagnosis" in response.diagnosis
            assert mock_urlopen.call_count == 1 # Only Ollama attempted

def test_ollama_mode_only_success(mock_transaction):
    """Scenario 7: LLM_PROVIDER=ollama -> Ollama succeeds, Groq not called"""
    with patch("app.config.settings.LLM_PROVIDER", "ollama"), \
         patch("app.config.settings.GROQ_API_KEY", "valid_key"):
        agent = DiagnosisAgent()
        
        ollama_json = b'''{"message": {"content": "{\\"diagnosis\\": \\"Ollama explicitly\\", \\"confidence\\": 0.8, \\"recommended_action\\": \\"WAIT_AND_RETRY\\", \\"reason\\": \\"test\\"}"}}'''
        
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = create_mock_response(ollama_json)
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert response.diagnosis == "Ollama explicitly"
            assert mock_urlopen.call_count == 1
            assert "11434" in mock_urlopen.call_args[0][0].full_url

def test_ollama_mode_only_failure(mock_transaction):
    """Scenario 8: LLM_PROVIDER=ollama -> Ollama fails -> Mock succeeds"""
    with patch("app.config.settings.LLM_PROVIDER", "ollama"):
        agent = DiagnosisAgent()
        
        with patch("urllib.request.urlopen", side_effect=URLError("Dead")) as mock_urlopen:
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert "Mock diagnosis" in response.diagnosis
            assert mock_urlopen.call_count == 1

def test_groq_mode_configured_fallback(mock_transaction):
    """Scenario 9: LLM_PROVIDER=groq -> Groq fails -> Ollama fails -> Mock"""
    with patch("app.config.settings.LLM_PROVIDER", "groq"), \
         patch("app.config.settings.GROQ_API_KEY", "valid_key"):
        agent = DiagnosisAgent()
        
        with patch("urllib.request.urlopen", side_effect=URLError("Dead")) as mock_urlopen:
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert "Mock diagnosis" in response.diagnosis
            assert mock_urlopen.call_count == 2 # Attempted both providers

def test_invalid_provider_response(mock_transaction):
    """Scenario 10: Groq returns invalid json -> Ollama fails -> Mock"""
    with patch("app.config.settings.LLM_PROVIDER", "auto"), \
         patch("app.config.settings.GROQ_API_KEY", "valid_key"):
        agent = DiagnosisAgent()
        
        def mock_urlopen_side_effect(req, *args, **kwargs):
            if "groq.com" in req.full_url:
                # Return bad JSON
                return create_mock_response(b'{"bad json')
            elif "11434" in req.full_url:
                raise URLError("Ollama dead")
            
        with patch("urllib.request.urlopen", side_effect=mock_urlopen_side_effect) as mock_urlopen:
            response = agent.diagnose_transaction(mock_transaction, 0.4)
            
            assert "Mock diagnosis" in response.diagnosis
            assert mock_urlopen.call_count == 2
