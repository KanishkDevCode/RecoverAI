import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import uuid

def generate_synthetic_data(num_records=500):
    np.random.seed(42)
    random.seed(42)
    
    data = []
    
    payment_methods = ['card', 'upi', 'netbanking', 'wallet']
    failure_codes = ['insufficient_funds', 'authentication_failed', 'bank_timeout', 'fraud_suspected', 'limit_exceeded', 'temporary_bank_failure']
    failure_reasons = {
        'insufficient_funds': 'Customer account has insufficient balance.',
        'authentication_failed': 'OTP or 3D secure authentication failed.',
        'bank_timeout': 'Issuing bank did not respond in time.',
        'fraud_suspected': 'Transaction flagged by risk engine.',
        'limit_exceeded': 'Transaction exceeds customer limits.',
        'temporary_bank_failure': 'Bank is experiencing intermittent issues.'
    }
    merchant_segments = ['ecommerce', 'saas', 'edtech', 'travel', 'gaming']
    currencies = ['INR', 'USD']
    
    for _ in range(num_records):
        transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
        customer_id = f"cust_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now() - timedelta(days=random.randint(0, 30), minutes=random.randint(0, 1440))
        
        currency = random.choices(currencies, weights=[0.8, 0.2])[0]
        amount = round(random.uniform(100.0, 50000.0), 2)
        
        payment_method = random.choice(payment_methods)
        failure_code = random.choice(failure_codes)
        failure_reason = failure_reasons[failure_code]
        
        # Risk / Recovery related features
        customer_age_days = random.randint(1, 1000)
        prior_success_count = random.randint(0, 50)
        prior_failure_count = random.randint(0, 5)
        previous_recovery_count = random.randint(0, prior_failure_count)
        average_transaction_value = round(random.uniform(amount * 0.5, amount * 2), 2)
        
        subscription_flag = random.choices([True, False], weights=[0.3, 0.7])[0]
        retry_count = random.randint(0, 3)
        days_since_last_payment = random.randint(0, 30) if prior_success_count > 0 else -1
        
        merchant_segment = random.choice(merchant_segments)
        order_value = round(amount + random.uniform(0, 500), 2)
        checkout_started = True
        checkout_completed = random.choices([True, False], weights=[0.9, 0.1])[0]
        
        # Ground truth logic
        # Some are recoverable, some are not
        if failure_code in ['insufficient_funds', 'fraud_suspected', 'limit_exceeded']:
            ground_truth_recoverable = False
            ground_truth_recovery_action = "STOP_AUTOMATION" if failure_code == 'fraud_suspected' else "SEND_RECOVERY_MESSAGE"
        else:
            ground_truth_recoverable = True
            ground_truth_recovery_action = "WAIT_AND_RETRY" if failure_code in ['bank_timeout', 'temporary_bank_failure'] else "RETRY_PAYMENT"
            
        # Add some randomness to make it realistic
        if random.random() < 0.2:
            ground_truth_recoverable = not ground_truth_recoverable
            
        recovered_amount = amount if ground_truth_recoverable else 0.0
        
        data.append({
            'transaction_id': transaction_id,
            'customer_id': customer_id,
            'timestamp': timestamp,
            'amount': amount,
            'currency': currency,
            'payment_method': payment_method,
            'payment_status': 'failed',
            'failure_code': failure_code,
            'failure_reason': failure_reason,
            'customer_age_days': customer_age_days,
            'prior_success_count': prior_success_count,
            'prior_failure_count': prior_failure_count,
            'previous_recovery_count': previous_recovery_count,
            'average_transaction_value': average_transaction_value,
            'subscription_flag': subscription_flag,
            'retry_count': retry_count,
            'days_since_last_payment': days_since_last_payment,
            'merchant_segment': merchant_segment,
            'order_value': order_value,
            'checkout_started': checkout_started,
            'checkout_completed': checkout_completed,
            'ground_truth_recoverable': ground_truth_recoverable,
            'ground_truth_recovery_action': ground_truth_recovery_action,
            'recovered_amount': recovered_amount
        })
        
    df = pd.DataFrame(data)
    # Re-order columns for clarity
    feature_cols = [
        'transaction_id', 'customer_id', 'timestamp', 'amount', 'currency', 'payment_method',
        'payment_status', 'failure_code', 'failure_reason', 'customer_age_days',
        'prior_success_count', 'prior_failure_count', 'previous_recovery_count',
        'average_transaction_value', 'subscription_flag', 'retry_count',
        'days_since_last_payment', 'merchant_segment', 'order_value',
        'checkout_started', 'checkout_completed'
    ]
    # 'checkout_completed' here strictly means "the user clicked the final pay button before this specific failure occurred". It is known AT prediction time.
    
    label_cols = ['ground_truth_recoverable', 'ground_truth_recovery_action', 'recovered_amount']
    df = df[feature_cols + label_cols]
    
    output_path = 'synthetic_dataset.csv'
    df.to_csv(output_path, index=False)
    print(f"Generated {num_records} synthetic records and saved to '{output_path}'.")

if __name__ == "__main__":
    generate_synthetic_data(5000)
