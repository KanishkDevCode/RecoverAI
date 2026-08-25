import os
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import uuid

def generate_synthetic_data_v2(num_records=5000):
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
    
    segments = [
        {'name': 'smb_saas', 'weight': 0.35, 'min_amount': 10, 'max_amount': 1000},
        {'name': 'ecommerce', 'weight': 0.30, 'min_amount': 20, 'max_amount': 3000},
        {'name': 'mid_market', 'weight': 0.20, 'min_amount': 100, 'max_amount': 10000},
        {'name': 'enterprise', 'weight': 0.10, 'min_amount': 1000, 'max_amount': 25000},
        {'name': 'high_value', 'weight': 0.05, 'min_amount': 5000, 'max_amount': 50000},
    ]
    segment_names = [s['name'] for s in segments]
    segment_weights = [s['weight'] for s in segments]
    
    currencies = ['INR', 'USD']
    
    for _ in range(num_records):
        transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
        customer_id = f"cust_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now() - timedelta(days=random.randint(0, 30), minutes=random.randint(0, 1440))
        
        currency = random.choices(currencies, weights=[0.8, 0.2])[0]
        
        # Select Segment and Amount
        segment_name = random.choices(segment_names, weights=segment_weights)[0]
        segment_config = next(s for s in segments if s['name'] == segment_name)
        
        # Skew distribution towards lower amounts within segment for realism
        amount = round(random.uniform(segment_config['min_amount'], segment_config['max_amount']) * random.uniform(0.1, 1.0), 2)
        amount = max(amount, segment_config['min_amount'])
        
        payment_method = random.choice(payment_methods)
        
        # Failure code probabilities
        failure_code = random.choices(
            failure_codes, 
            weights=[0.4, 0.2, 0.15, 0.05, 0.1, 0.1]
        )[0]
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
        
        order_value = round(amount + random.uniform(0, 100), 2)
        checkout_started = True
        checkout_completed = random.choices([True, False], weights=[0.9, 0.1])[0]
        
        # Probabilistic Ground Truth Label Generation
        base_probs = {
            'bank_timeout': 0.85,
            'temporary_bank_failure': 0.80,
            'authentication_failed': 0.50,
            'insufficient_funds': 0.35,
            'limit_exceeded': 0.15,
            'fraud_suspected': 0.02
        }
        
        prob = base_probs[failure_code]
        
        # Modifiers based on features
        if amount > 10000:
            prob -= 0.15
        elif amount < 500:
            prob += 0.10
            
        if retry_count > 1:
            prob -= 0.10
            
        if prior_success_count > 10:
            prob += 0.10
            
        if prior_failure_count > 2:
            prob -= 0.15
            
        if subscription_flag:
            prob += 0.10
            
        # Bound probability between 0.01 and 0.99
        prob = max(0.01, min(0.99, prob))
        
        ground_truth_recoverable = random.random() < prob
        
        # Action selection (heuristic for what SHOULD happen ideally)
        if not ground_truth_recoverable:
            ground_truth_recovery_action = "STOP_AUTOMATION" if failure_code == 'fraud_suspected' else "CREATE_ESCALATION"
        else:
            if failure_code in ['bank_timeout', 'temporary_bank_failure']:
                ground_truth_recovery_action = "WAIT_AND_RETRY"
            elif failure_code == 'insufficient_funds':
                ground_truth_recovery_action = "SEND_RECOVERY_MESSAGE"
            else:
                ground_truth_recovery_action = "RETRY_PAYMENT"
                
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
            'merchant_segment': segment_name,
            'order_value': order_value,
            'checkout_started': checkout_started,
            'checkout_completed': checkout_completed,
            'ground_truth_recoverable': ground_truth_recoverable,
            'ground_truth_recovery_action': ground_truth_recovery_action,
            'recovered_amount': recovered_amount
        })
        
    df = pd.DataFrame(data)
    
    # Standardize column order
    feature_cols = [
        'transaction_id', 'customer_id', 'timestamp', 'amount', 'currency', 'payment_method',
        'payment_status', 'failure_code', 'failure_reason', 'customer_age_days',
        'prior_success_count', 'prior_failure_count', 'previous_recovery_count',
        'average_transaction_value', 'subscription_flag', 'retry_count',
        'days_since_last_payment', 'merchant_segment', 'order_value',
        'checkout_started', 'checkout_completed'
    ]
    label_cols = ['ground_truth_recoverable', 'ground_truth_recovery_action', 'recovered_amount']
    df = df[feature_cols + label_cols]
    
    # Ensure V2 directory exists
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data/v2'))
    os.makedirs(data_dir, exist_ok=True)
    
    # Train / Val / Test split
    from sklearn.model_selection import train_test_split
    df_train_temp, df_test = train_test_split(df, test_size=1000, random_state=42)
    df_train, df_val = train_test_split(df_train_temp, test_size=500, random_state=42)
    
    df.to_csv(os.path.join(data_dir, 'synthetic_dataset.csv'), index=False)
    df_train.to_csv(os.path.join(data_dir, 'synthetic_train.csv'), index=False)
    df_val.to_csv(os.path.join(data_dir, 'synthetic_val.csv'), index=False)
    df_test.to_csv(os.path.join(data_dir, 'synthetic_test.csv'), index=False)
    
    print(f"Generated {num_records} V2 synthetic records in data/v2/ directory.")
    
if __name__ == "__main__":
    generate_synthetic_data_v2(5000)
