import decimal
import logging
from typing import Union

logger = logging.getLogger(__name__)

# Configure local context for safe decimal operations
decimal.getcontext().prec = 28

def to_minor_units(amount: Union[float, str, decimal.Decimal]) -> int:
    """
    Converts a major currency unit (e.g., Rupees, Dollars) to its minor unit (e.g., Paise, Cents).
    Uses Decimal to avoid floating point precision errors.
    """
    if amount is None:
        raise ValueError("Amount cannot be None")
        
    try:
        # Convert float to string first to avoid floating point rounding anomalies during decimal construction
        amount_str = str(amount) if not isinstance(amount, decimal.Decimal) else amount
        dec_val = decimal.Decimal(amount_str)
        
        # Multiply by 100 to get minor units
        minor = dec_val * decimal.Decimal('100')
        
        # Ensure it resolves to an integer cleanly
        if minor % 1 != 0:
            logger.warning(f"Precision loss warning: {amount} results in fractional minor units ({minor}).")
            
        return int(minor)
    except Exception as e:
        logger.error(f"Failed to convert {amount} to minor units: {e}")
        raise ValueError(f"Invalid monetary amount: {amount}")

def to_major_units(minor_amount: int) -> float:
    """
    Converts a minor currency unit (e.g., Paise) back to a major unit (e.g., Rupees).
    Returns a float to maintain backward compatibility with external API responses.
    """
    if minor_amount is None:
        return 0.0
    
    try:
        dec_val = decimal.Decimal(minor_amount) / decimal.Decimal('100')
        return float(dec_val)
    except Exception as e:
        logger.error(f"Failed to convert minor units {minor_amount} to major units: {e}")
        raise ValueError(f"Invalid minor monetary amount: {minor_amount}")
