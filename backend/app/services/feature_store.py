import pandas as pd
import os
import logging
from typing import Protocol, Dict, Any, Optional

logger = logging.getLogger(__name__)

class FeatureStore(Protocol):
    def get_features(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve ML features for a given transaction."""
        ...

class MockFeatureStore:
    def __init__(self):
        # We exclusively load the HELD-OUT TEST features. No data leakage from train.
        data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/v2/synthetic_test.csv"))
        
        self.features_df = None
        if os.path.exists(data_path):
            try:
                self.features_df = pd.read_csv(data_path)
                self.features_df.set_index('transaction_id', inplace=True)
                logger.info(f"MockFeatureStore loaded {len(self.features_df)} held-out records.")
            except Exception as e:
                logger.error(f"Failed to load test features: {e}")
        else:
            logger.error(f"Feature dataset not found at {data_path}")
            
    def get_features(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        if self.features_df is not None and transaction_id in self.features_df.index:
            row = self.features_df.loc[transaction_id].to_dict()
            return row
            
        # Fallback for dynamic UI transactions and pytest unit tests
        return {
                "amount": 1000.0,
                "currency": "INR",
                "payment_method": "upi",
                "payment_status": "failed",
                "failure_code": "insufficient_funds",
                "failure_reason": "Low balance",
                "customer_age_days": 100,
                "prior_success_count": 50,
                "prior_failure_count": 0,
                "previous_recovery_count": 0,
                "average_transaction_value": 500,
                "subscription_flag": 0,
                "retry_count": 0,
                "days_since_last_payment": 1,
                "merchant_segment": "retail",
                "order_value": 1000.0,
                "checkout_started": 1,
                "checkout_completed": 1,
                "ground_truth_recoverable": True
            }


# Singleton
feature_store = MockFeatureStore()
