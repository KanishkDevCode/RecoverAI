# RecoverAI Machine Learning Model (V2)

## Overview
RecoverAI utilizes a Random Forest Classifier to predict the probability that a failed payment can be successfully recovered upon a retry attempt. This probability is a core signal used by both the Diagnosis Agent and the Policy Engine.

## Dataset Generation & V2 Improvements
The model is trained on a synthetically generated dataset of payment failures (`scripts/generate_synthetic_data.py`).
- **V1 Problems**: The initial V1 dataset suffered from extreme target leakage because the `failure_code` was a 100% deterministic predictor of recovery, causing the model to memorize the rules rather than learn patterns.
- **V2 Improvements**: The V2 dataset introduces probabilistic recovery outcomes. The `failure_code` establishes a baseline probability (e.g., `bank_timeout` = 85%, `insufficient_funds` = 35%), which is then modified dynamically by features like transaction amount, retry count, customer age, and merchant segment.

## Features
The model consumes a wide array of numeric, categorical, and boolean features:
- **Numeric**: `amount`, `customer_age_days`, `prior_success_count`, `prior_failure_count`, `previous_recovery_count`, `average_transaction_value`, `retry_count`, `days_since_last_payment`, `order_value`
- **Categorical**: `currency`, `payment_method`, `merchant_segment`, `failure_code`
- **Boolean**: `subscription_flag`, `checkout_completed`

*No direct target leakage features are included.*

## Data Splits & Locked Test Set
The dataset is split into:
- **Training Set**: Used to fit the Random Forest model.
- **Validation Set**: Used to evaluate the threshold that maximizes Expected Value (EV).
- **Held-out Test Set (1,000 transactions)**: Strictly sequestered during model selection and threshold tuning. The test set is exclusively used by the final evaluation script (`scripts/evaluate_batch.py`) to measure simulated real-world performance.

## Threshold Selection & Expected Value
Rather than relying purely on F1-Score or ROC-AUC, the threshold is optimized for **Expected Value (EV)**.
- **Intervention Cost**: $2.00
- **False Positive Cost**: $5.00 penalty
- The threshold that maximized EV on the validation set was selected and locked (Threshold = 0.10 in the final V2 iteration).

## Limitations
- The current model relies on a statically generated synthetic dataset.
- Real-world deployment would require integration with a live feature store and continuous retraining to handle concept drift.
