import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
MAX_AUTO_ACTION_AMOUNT = float(os.getenv("MAX_AUTO_ACTION_AMOUNT", "5000.00"))

ACTION_RANK = {
    "STOP_AUTOMATION": 0,
    "CREATE_ESCALATION": 1,
    "SEND_RECOVERY_MESSAGE": 2,
    "WAIT_AND_RETRY": 3,
    "RETRY_PAYMENT": 4
}

def evaluate_policy(
    transaction, 
    agent_action: str, 
    agent_confidence: float = 1.0, 
    current_retry_count: int = 0,
    ml_probability: float = 0.0
) -> Tuple[bool, str, str]:
    """
    Evaluates whether the recommended action is allowed by deterministic risk-tiered rules.
    Returns: (is_allowed, final_action, reason)
    """
    amount = float(transaction.amount)
    failure_code = getattr(transaction, "failure_code", "") or ""
    
    logger.info(f"Evaluating policy for {transaction.id}. Agent: {agent_action}, ML Prob: {ml_probability:.2f}")

    # 1. Determine Risk Tier
    if failure_code in ["fraud_suspected", "limit_exceeded"]:
        risk_tier = "PERMANENT_FRAUD"
    elif ml_probability < 0.10:
        risk_tier = "HIGH_RISK"
    elif ml_probability < 0.50:
        risk_tier = "MEDIUM_RISK"
    else:
        risk_tier = "LOW_RISK"

    # 2. Determine Amount Tier
    if amount <= 1000.0:
        amount_tier = "SMALL"
    elif amount <= MAX_AUTO_ACTION_AMOUNT:
        amount_tier = "MEDIUM"
    else:
        amount_tier = "LARGE"

    # 3. Deterministic Policy Matrix for Max Allowed Action
    max_action = "STOP_AUTOMATION"
    matrix_reason = "Unknown condition."

    if risk_tier == "PERMANENT_FRAUD":
        max_action = "STOP_AUTOMATION"
        matrix_reason = f"Fraud or permanent failure detected ({failure_code})."
    else:
        if amount_tier == "LARGE":
            # Hard safety constraint for high values
            max_action = "CREATE_ESCALATION"
            matrix_reason = f"Amount ${amount:.2f} exceeds hard safety limit of ${MAX_AUTO_ACTION_AMOUNT}."
        elif current_retry_count >= MAX_RETRIES:
            max_action = "CREATE_ESCALATION" if amount_tier == "MEDIUM" else "STOP_AUTOMATION"
            matrix_reason = f"Max retries ({MAX_RETRIES}) reached."
        elif risk_tier == "HIGH_RISK":
            if amount_tier == "SMALL":
                max_action = "SEND_RECOVERY_MESSAGE"
                matrix_reason = "High risk (ML < 0.10) but small amount."
            else: # MEDIUM
                max_action = "CREATE_ESCALATION"
                matrix_reason = "High risk (ML < 0.10) for medium amount."
        elif risk_tier == "MEDIUM_RISK":
            if amount_tier == "SMALL":
                max_action = "WAIT_AND_RETRY"
                matrix_reason = "Medium risk (ML < 0.50) for small amount."
            else: # MEDIUM
                max_action = "SEND_RECOVERY_MESSAGE"
                matrix_reason = "Medium risk (ML < 0.50) for medium amount."
        elif risk_tier == "LOW_RISK":
            if amount_tier == "SMALL":
                max_action = "RETRY_PAYMENT"
                matrix_reason = "Low risk (ML >= 0.50) for small amount. Safe to auto-retry."
            else: # MEDIUM
                max_action = "WAIT_AND_RETRY"
                matrix_reason = "Low risk (ML >= 0.50) for medium amount. Bounded retry required."

    # 4. Enforce Policy Authorization
    # If agent hallucinates or recommends an unknown action, treat it as most aggressive
    agent_rank = ACTION_RANK.get(agent_action, 5) 
    max_rank = ACTION_RANK[max_action]

    if agent_rank > max_rank:
        reason = f"Policy Denied: Agent recommended {agent_action}, but max allowed is {max_action}. Reason: {matrix_reason}"
        logger.warning(reason)
        return False, max_action, reason
    else:
        reason = f"Policy Allowed: {agent_action} is within allowed bound ({max_action}). {matrix_reason}"
        logger.info(reason)
        # If agent_action is unknown but somehow rank <= max_rank, default to max_action just in case
        if agent_action not in ACTION_RANK:
            return False, "STOP_AUTOMATION", "Invalid agent action."
        return True, agent_action, reason
