from typing import Dict, Any, Optional

def normalize_webhook_payload(payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Normalizes webhook payloads from different providers into a canonical internal format.
    Safely handles nested JSON extraction without crashing.
    """
    
    # Razorpay Event
    if "event" in payload:
        # Standardize headers to lowercase for safe lookup
        headers_lower = {k.lower(): v for k, v in headers.items()}
        event_id = headers_lower.get("x-razorpay-event-id")
        
        event_type = payload.get("event")
        
        payment_entity = (
            payload
            .get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )
        
        refund_entity = (
            payload
            .get("payload", {})
            .get("refund", {})
            .get("entity", {})
        )
        
        gateway_payment_id = payment_entity.get("id") or refund_entity.get("payment_id")
        gateway_refund_id = refund_entity.get("id")
        
        return {
            "event_id": event_id,
            "event_type": event_type,
            "gateway_payment_id": gateway_payment_id,
            "gateway_refund_id": gateway_refund_id,
            "transaction_id": None,  # Razorpay won't have our internal txn_id
            "provider": "razorpay"
        }
        
    # Legacy Mock Event
    return {
        "event_id": payload.get("event_id"),
        "event_type": payload.get("event_type"),
        "gateway_payment_id": payload.get("gateway_payment_id"),
        "gateway_refund_id": payload.get("gateway_refund_id"),
        "transaction_id": payload.get("transaction_id"),
        "provider": "mock"
    }
