import joblib
import pandas as pd
import os
import json
import logging
from app.services.feature_store import feature_store

logger = logging.getLogger(__name__)

class MLService:
    def __init__(self):
        self.model = None
        self.threshold = 0.5
        self.features_list = []
        model_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_path = os.path.abspath(os.path.join(model_dir, "../../../models/recovery_model_v2.pkl"))
        self.config_path = os.path.abspath(os.path.join(model_dir, "../../../models/model_config_v2.json"))
        self.load_model()

    def load_model(self):
        if os.path.exists(self.model_path) and os.path.exists(self.config_path):
            try:
                self.model = joblib.load(self.model_path)
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    self.threshold = config.get("threshold", 0.5)
                    self.features_list = config.get("features", [])
                logger.info(f"Recovery ML model loaded. Threshold: {self.threshold}")
            except Exception as e:
                logger.error(f"Failed to load ML model or config: {e}")
        else:
            logger.warning(f"ML model/config not found. Train the model first.")

    def predict_recovery_probability(self, transaction: 'TransactionIncoming') -> float:
        """
        Predict the probability of recovery for a given transaction using hydrated features.
        """
        if not self.model:
            raise RuntimeError("Model not loaded. Cannot evaluate transaction.")
            
        features = feature_store.get_features(transaction.id)
        if not features:
            logger.error(f"Missing features for transaction {transaction.id}. Failing closed.")
            raise ValueError(f"Missing features for transaction {transaction.id}")
            
        # Also need to map transaction data that is passed in
        # The feature store already has amount, currency, payment_method, etc., since we dumped everything.
        # But for absolute safety, we use the values from the transaction object for core fields.
        features['amount'] = float(transaction.amount)
        features['currency'] = transaction.currency.value if hasattr(transaction.currency, 'value') else transaction.currency
        if transaction.payment_method:
            features['payment_method'] = transaction.payment_method.value if hasattr(transaction.payment_method, 'value') else transaction.payment_method
        features['retry_count'] = transaction.retry_count
        
        # Build the exact dataframe the model expects
        try:
            df = pd.DataFrame([features])
            
            # Predict probability of class 1 (recoverable)
            proba = self.model.predict_proba(df)[0][1]
            
            # Use our locked threshold to return a binary or just return proba?
            # Orchestrator uses proba. Diagnosis Agent uses proba. 
            # We will return the proba, but wait, if it's evaluated against threshold somewhere?
            # Actually, diagnosis_agent uses it directly (<0.20 rule).
            # The prompt says: "Select threshold using validation data only. Then LOCK the threshold. Then evaluate once."
            # In our setup, the MLService will just return the raw probability. The threshold is mainly for the evaluation metrics (Precision/Recall).
            # But let's attach the threshold to the service so evaluate_batch can use it.
            return float(proba)
        except Exception as e:
            logger.error(f"Error predicting recovery probability: {e}")
            raise RuntimeError(f"Error predicting probability: {e}")

# Singleton instance
ml_service = MLService()
