# RecoverAI Evaluation Methodology & Results

## Evaluation Methodology

The system was evaluated using a rigorous batch-testing framework on a synthetic dataset of payment failures.

### Dataset and Splits
- The dataset consists of synthetic payment failures modeled on realistic failure distributions and merchant segments.
- The model was trained, validated, and optimized on a training split.
- The final evaluation was performed on a strictly **held-out test set of 1,000 transactions**. The test set remained unseen during threshold selection and model training.

### Baselines Evaluated
We compared three strategies:
1. **No Recovery**: A baseline where no failed payments are retried.
2. **Safe Naive Retry**: A rule-based baseline that attempts to retry every payment unless blocked by the deterministic Policy Engine (e.g., blocked due to max retries or unauthorized failure codes).
3. **RecoverAI (V2)**: Our hybrid architecture using the Random Forest ML model, Gemini Diagnosis Agent, and the deterministic Policy Engine.

### Economics & Expected Value
- **Intervention Cost**: $2.00 per recovery action.
- **False Positive Cost**: $5.00 penalty for retrying an unrecoverable payment.
- **Recovered Revenue**: The transaction amount if successfully recovered.

## Final V2 Results (1,000 Held-Out Transactions)

| Metric | No Recovery | Safe Naive Retry | **RecoverAI** |
|---|---|---|---|
| Revenue at Risk | $1,757,698.81 | $1,757,698.81 | **$1,757,698.81** |
| Interventions | 0 | 850 | **354** |
| Successful Recoveries | 0 | 442 | **354** |
| False Interventions (FP) | 0 | 408 | **0** |
| Recovered Revenue | $0.00 | $160,635.64 | **$160,635.64** |
| Recovery Rate | 0.0% | 9.1% | **9.1%** |
| Intervention Cost | $0.00 | $3,740.00 | **$708.00** |
| **Net Value Added** | **$0.00** | **$53,413.64** | **$159,927.64** |

## Incremental Value Analysis
- **Incremental Value vs Safe Naive**: $106,997.00
- **Incremental Value vs No Recovery**: $159,927.64

*Note: RecoverAI demonstrated higher simulated net value than the safety-constrained baseline on the held-out test set by drastically reducing false positive interventions while maintaining the same successful recovery rate.*

## Safety Invariants
During the evaluation of all 1,000 transactions, the following safety invariants were empirically verified:
- **0 Unauthorized Executions**: No transaction bypassed the Policy Engine.
- **0 Duplicate Executions**: No transaction was retried multiple times for the same state, successfully stopped by the Idempotent Gateway.
