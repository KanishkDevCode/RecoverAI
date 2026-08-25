import pandas as pd
import numpy as np
import os
import joblib
import json
import logging
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

INTERVENTION_COST = 2.0
FALSE_POSITIVE_COST = 5.0

def evaluate_thresholds(y_true, probas, amounts):
    thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    best_ev = -float('inf')
    best_t = 0.5
    best_metrics = {}
    
    print("\n--- Threshold Analysis on Validation Set ---")
    for t in thresholds:
        y_pred = (probas >= t).astype(int)
        
        # Calculate EV
        ev = 0.0
        for i in range(len(y_pred)):
            if y_pred[i] == 1:
                ev -= INTERVENTION_COST
                if y_true.iloc[i] == 1:
                    ev += amounts.iloc[i]
                else:
                    ev -= FALSE_POSITIVE_COST
                    
        p = precision_score(y_true, y_pred, zero_division=0)
        r = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        
        print(f"Threshold: {t:.2f} | Precision: {p*100:.1f}% | Recall: {r*100:.1f}% | F1: {f1*100:.1f}% | EV: ${ev:,.2f}")
        
        if ev > best_ev:
            best_ev = ev
            best_t = t
            best_metrics = {'precision': p, 'recall': r, 'f1': f1, 'ev': ev}
            
    return best_t, best_metrics

def train_model():
    base_dir = os.path.dirname(__file__)
    data_dir = os.path.abspath(os.path.join(base_dir, "../data/v2"))
    
    train_path = os.path.join(data_dir, "synthetic_train.csv")
    val_path = os.path.join(data_dir, "synthetic_val.csv")
    
    if not os.path.exists(train_path):
        logger.error(f"Training data not found at {train_path}")
        return
        
    df_train = pd.read_csv(train_path)
    df_val = pd.read_csv(val_path)
    
    # Feature Definition
    numeric_features = [
        'amount', 'customer_age_days', 'prior_success_count', 
        'prior_failure_count', 'previous_recovery_count', 
        'average_transaction_value', 'retry_count', 
        'days_since_last_payment', 'order_value'
    ]
    categorical_features = [
        'currency', 'payment_method', 'merchant_segment', 'failure_code'
    ]
    boolean_features = ['subscription_flag', 'checkout_completed']
    
    all_features = numeric_features + categorical_features + boolean_features
    target = 'ground_truth_recoverable'
    
    X_train = df_train[all_features]
    y_train = df_train[target].astype(int)
    
    X_val = df_val[all_features]
    y_val = df_val[target].astype(int)
    amounts_val = df_val['amount']
    
    # Preprocessing
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_features),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_features),
            ('bool', 'passthrough', boolean_features)
        ])
        
    # Model
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )
    
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', model)
    ])
    
    logger.info("Training V2 model...")
    pipeline.fit(X_train, y_train)
    
    # Evaluate on Train
    train_probas = pipeline.predict_proba(X_train)[:, 1]
    train_preds = (train_probas >= 0.5).astype(int)
    logger.info("--- Train Metrics (Threshold 0.5) ---")
    logger.info(f"Precision: {precision_score(y_train, train_preds)*100:.1f}%")
    logger.info(f"Recall: {recall_score(y_train, train_preds)*100:.1f}%")
    logger.info(f"ROC-AUC: {roc_auc_score(y_train, train_probas)*100:.1f}%")
    
    # Evaluate on Validation
    val_probas = pipeline.predict_proba(X_val)[:, 1]
    roc_auc_val = roc_auc_score(y_val, val_probas)
    logger.info(f"\nValidation ROC-AUC: {roc_auc_val*100:.1f}%")
    
    # Threshold Selection
    best_t, best_metrics = evaluate_thresholds(y_val, val_probas, amounts_val)
    
    logger.info(f"\nSelected Threshold: {best_t:.2f} (Max EV: ${best_metrics['ev']:,.2f})")
    
    # Feature Importance
    # Get feature names after one-hot encoding
    cat_encoder = pipeline.named_steps['preprocessor'].named_transformers_['cat']
    cat_feature_names = cat_encoder.get_feature_names_out(categorical_features)
    feature_names = numeric_features + list(cat_feature_names) + boolean_features
    
    importances = model.feature_importances_
    feat_imp = pd.DataFrame({'feature': feature_names, 'importance': importances})
    feat_imp = feat_imp.sort_values('importance', ascending=False)
    
    print("\n--- Top 10 Features ---")
    print(feat_imp.head(10).to_string(index=False))
    
    # Save Model and Config
    model_path = os.path.join(base_dir, '../models/recovery_model_v2.pkl')
    config_path = os.path.join(base_dir, '../models/model_config_v2.json')
    
    joblib.dump(pipeline, model_path)
    
    config = {
        "features": all_features,
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "boolean_features": boolean_features,
        "threshold": best_t,
        "version": "v2",
        "metrics": {
            "val_precision": float(best_metrics['precision']),
            "val_recall": float(best_metrics['recall']),
            "val_f1": float(best_metrics['f1']),
            "val_roc_auc": float(roc_auc_val)
        }
    }
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
        
    logger.info(f"\nModel saved to {model_path}")
    logger.info(f"Config saved to {config_path}")
    
    # Save Feature Importance for reporting
    feat_imp.to_csv(os.path.join(base_dir, '../models/feature_importance_v2.csv'), index=False)

if __name__ == "__main__":
    train_model()
