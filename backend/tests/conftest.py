import os

# Ensure tests can use the feature store fallback
os.environ["PYTEST_RUNNING"] = "1"
