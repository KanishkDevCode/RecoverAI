import pytest
import sys
from importlib import import_module
from fastapi.testclient import TestClient

# (Dangerous sys.modules loop removed)

from app.main import app

def test_metrics_does_not_import_execution_logic():
    """
    SECURITY INVARIANT:
    The observability/metrics layer MUST NOT import or invoke the execution guard
    or state machine, to guarantee it is strictly passive and read-only.
    """
    import subprocess
    import sys
    import os
    
    script = """
import sys
import app.api.metrics

invalid_modules = [
    "app.services.execution_guard",
    "app.services.state_machine",
    "app.services.reconciliation",
    "app.services.refund_service"
]

failed = False
for mod in invalid_modules:
    if mod in sys.modules:
        print(f"FAILED: {mod} was loaded!")
        failed = True

if failed:
    sys.exit(1)
print("SUCCESS")
sys.exit(0)
"""
    
    # Run the import check in a separate process to avoid polluting the pytest sys.modules
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    result = subprocess.run(
        [sys.executable, "-c", script], 
        capture_output=True, 
        text=True,
        env=env
    )
    
    assert result.returncode == 0, f"Subprocess failed: {result.stdout} {result.stderr}"
    assert "SUCCESS" in result.stdout
