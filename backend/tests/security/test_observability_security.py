import pytest
import sys
from importlib import import_module
from fastapi.testclient import TestClient

# Must reset modules before test to check clean imports
for m in list(sys.modules.keys()):
    if m.startswith("app.") and m != "app.config":
        del sys.modules[m]

from app.main import app

def test_metrics_does_not_import_execution_logic():
    """
    SECURITY INVARIANT:
    The observability/metrics layer MUST NOT import or invoke the execution guard
    or state machine, to guarantee it is strictly passive and read-only.
    """
    client = TestClient(app)
    
    # Trigger metrics module load
    client.get("/metrics")
    
    # Assert execution guard is not in loaded modules for the metrics context
    assert "app.services.execution_guard" not in sys.modules, "ExecutionGuard was loaded during metrics evaluation!"
    assert "app.services.state_machine" not in sys.modules, "StateMachine was loaded during metrics evaluation!"
    assert "app.services.reconciliation" not in sys.modules, "Reconciliation was loaded during metrics evaluation!"
    assert "app.services.refund_service" not in sys.modules, "RefundService was loaded during metrics evaluation!"
