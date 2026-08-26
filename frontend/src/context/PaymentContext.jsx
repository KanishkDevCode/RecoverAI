import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { createPayment as apiCreatePayment } from '../services/api';
import { connectRecoveryStream } from '../services/websocket';

const PaymentContext = createContext(null);

export function usePayment() {
  const ctx = useContext(PaymentContext);
  if (!ctx) throw new Error('usePayment must be used within PaymentProvider');
  return ctx;
}

/* Event types emitted by the backend orchestrator */
const EVENT_TYPES = [
  'PAYMENT_FAILED',
  'ML_PREDICTION',
  'AI_RECOMMENDATION',
  'POLICY_DECISION',
  'STATE_CHANGE',
  'GATEWAY_RESULT',
  'RECOVERY_COMPLETE',
];

export function PaymentProvider({ children }) {
  /* ─── Payment state ─── */
  const [paymentState, setPaymentState] = useState('idle');
  // idle | processing | failed | recovering | succeeded | recovery_failed | unknown | error

  const [transaction, setTransaction] = useState(null);
  const [recoveryEvents, setRecoveryEvents] = useState([]);
  const [recoveryResult, setRecoveryResult] = useState(null);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);

  /* ─── Create and process a payment ─── */
  const processPayment = useCallback(async (payload, mode = 'live', developerOverrides = null) => {
    setPaymentState('processing');
    setRecoveryEvents([]);
    setRecoveryResult(null);
    setError(null);

    const txId = payload.id;
    setTransaction({ ...payload, id: txId });

    try {
      // 1. Open WS before sending POST so we never miss events
      const ws = connectRecoveryStream(txId, {
        onEvent: (event) => {
          setRecoveryEvents((prev) => [...prev, event]);

          if (event.event_type === 'PAYMENT_FAILED') {
            setPaymentState('failed');
          }
          if (event.event_type === 'POLICY_DECISION' || event.event_type === 'ML_PREDICTION' || event.event_type === 'AI_RECOMMENDATION') {
            setPaymentState('recovering');
          }
          if (event.event_type === 'STATE_CHANGE') {
            const terminalStates = ['ESCALATED', 'STOPPED', 'WAITING', 'AWAITING_CUSTOMER'];
            if (terminalStates.includes(event.data.new_state)) {
              setPaymentState('recovery_failed');
            }
          }
          if (event.event_type === 'RECOVERY_COMPLETE') {
            setRecoveryResult(event.data);
            if (event.data.outcome === 'SUCCEEDED') {
              setPaymentState('succeeded_recovered');
            } else if (event.data.outcome === 'UNKNOWN') {
              setPaymentState('unknown');
            } else {
              setPaymentState('recovery_failed');
            }
          }
          if (event.event_type === 'GATEWAY_RESULT') {
            if (event.data.status === 'SUCCEEDED') {
              setPaymentState('succeeded_recovered');
            } else if (event.data.status === 'UNKNOWN') {
              setPaymentState('unknown');
            } else if (event.data.status === 'FAILED') {
              setPaymentState('recovery_failed');
            }
          }
        },
        onError: () => {
          setError('WebSocket connection lost');
        },
        onClose: () => { /* normal close */ },
      });
      wsRef.current = ws;

      // 2. Trigger backend processing
      const response = await apiCreatePayment({
        id: payload.id,
        customer_id: payload.customer_id,
        amount: payload.amount,
        currency: payload.currency,
        payment_method: payload.payment_method,
        mode: mode,
        ...(developerOverrides ? { developer_overrides: developerOverrides } : {})
      });

      if (response.status === 'SUCCEEDED') {
        setPaymentState('succeeded_normal');
      }
      
    } catch (e) {
      setError(e.message || 'Failed to connect to payment service');
      setPaymentState('error');
    }
  }, []);
  /* ─── Send duplicate (for idempotency demo) ─── */
  const sendDuplicate = useCallback(async (payload) => {
    try {
      await apiCreatePayment(payload);
    } catch {
      /* expected to be blocked or replayed */
    }
  }, []);

  /* ─── Reset everything ─── */
  const resetPayment = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setPaymentState('idle');
    setTransaction(null);
    setRecoveryEvents([]);
    setRecoveryResult(null);
    setError(null);
  }, []);

  const value = {
    paymentState,
    transaction,
    recoveryEvents,
    recoveryResult,
    error,
    processPayment,
    sendDuplicate,
    resetPayment,
    setPaymentState,
  };

  return (
    <PaymentContext.Provider value={value}>
      {children}
    </PaymentContext.Provider>
  );
}
