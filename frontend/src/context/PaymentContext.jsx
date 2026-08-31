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
  const [transaction, setTransaction] = useState(null);
  const [recoveryEvents, setRecoveryEvents] = useState([]);
  const [recoveryResult, setRecoveryResult] = useState(null);
  const [error, setError] = useState(null);
  const [wsStatus, setWsStatus] = useState('disconnected'); // connecting, connected, reconnecting, error, disconnected

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pollIntervalRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const isTerminalRef = useRef(false);

  // Terminate any active connections and polling
  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    setWsStatus('disconnected');
  }, []);

  const startPolling = useCallback(async (txId) => {
    if (pollIntervalRef.current || isTerminalRef.current) return;
    const { getPaymentDetails } = await import('../services/api');
    
    pollIntervalRef.current = setInterval(async () => {
      if (isTerminalRef.current) {
        clearInterval(pollIntervalRef.current);
        return;
      }
      try {
        const details = await getPaymentDetails(txId);
        const rec = details.recovery;
        if (rec && rec.outcome_status) {
          if (rec.outcome_status === 'SUCCESS' || rec.outcome_status === 'SUCCEEDED') {
            setPaymentState('succeeded_recovered');
            isTerminalRef.current = true;
          } else if (rec.outcome_status === 'UNKNOWN') {
            setPaymentState('unknown');
            isTerminalRef.current = true;
          } else if (['FAILED', 'ESCALATED', 'STOPPED'].includes(rec.outcome_status)) {
            setPaymentState('recovery_failed');
            isTerminalRef.current = true;
          }
        }
        if (isTerminalRef.current) {
          clearInterval(pollIntervalRef.current);
          cleanup();
        }
      } catch (e) {
        // Ignore polling errors
      }
    }, 2000);
  }, [cleanup]);

  const connectWs = useCallback((txId) => {
    return new Promise((resolve) => {
      if (isTerminalRef.current) {
        resolve();
        return;
      }
      setWsStatus(reconnectAttempts.current > 0 ? 'reconnecting' : 'connecting');

      const ws = connectRecoveryStream(txId, {
        onOpen: () => {
          setWsStatus('connected');
          reconnectAttempts.current = 0;
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          resolve();
        },
        onEvent: (event) => {
        setRecoveryEvents((prev) => {
          // Avoid duplicates if reconnecting
          if (prev.some(e => e.event_type === event.event_type && JSON.stringify(e.data) === JSON.stringify(event.data))) return prev;
          return [...prev, event];
        });

        if (event.event_type === 'PAYMENT_FAILED') setPaymentState('failed');
        if (['POLICY_DECISION', 'ML_PREDICTION', 'AI_RECOMMENDATION'].includes(event.event_type)) {
          setPaymentState('recovering');
        }
        if (event.event_type === 'STATE_CHANGE') {
          const terminalStates = ['ESCALATED', 'STOPPED', 'WAITING', 'AWAITING_CUSTOMER'];
          if (terminalStates.includes(event.data.new_state)) {
            setPaymentState('recovery_failed');
            isTerminalRef.current = true;
          }
        }
        if (event.event_type === 'RECOVERY_COMPLETE') {
          setRecoveryResult(event.data);
          isTerminalRef.current = true;
          if (event.data.outcome === 'SUCCEEDED' || event.data.outcome === 'SUCCESS') {
            setPaymentState('succeeded_recovered');
          } else if (event.data.outcome === 'UNKNOWN') {
            setPaymentState('unknown');
          } else {
            setPaymentState('recovery_failed');
          }
        }
        if (event.event_type === 'GATEWAY_RESULT') {
          if (event.data.status === 'SUCCEEDED' || event.data.status === 'SUCCESS') {
            setPaymentState('succeeded_recovered');
            isTerminalRef.current = true;
          } else if (event.data.status === 'UNKNOWN') {
            setPaymentState('unknown');
            isTerminalRef.current = true;
          } else if (event.data.status === 'FAILED') {
            setPaymentState('recovery_failed');
            isTerminalRef.current = true;
          }
        }

        if (isTerminalRef.current) cleanup();
      },
        onError: () => {
          setWsStatus('error');
          resolve(); // Resolve on error so we don't block
        },
        onClose: () => {
          if (!isTerminalRef.current && reconnectAttempts.current < 5) {
            setWsStatus('error');
            const delay = Math.min(1000 * (2 ** reconnectAttempts.current), 10000);
            reconnectAttempts.current += 1;
            reconnectTimeoutRef.current = setTimeout(() => connectWs(txId), delay);
            // Fallback to HTTP polling if WS is down
            startPolling(txId);
          } else if (!isTerminalRef.current) {
            setWsStatus('disconnected');
            startPolling(txId);
          }
          resolve(); // Resolve on close to unblock
        },
      });
      wsRef.current = ws;
    });
  }, [cleanup, startPolling]);

  /* ─── Create and process a payment ─── */
  const processPayment = useCallback(async (payload, mode = 'live', developerOverrides = null) => {
    cleanup();
    isTerminalRef.current = false;
    reconnectAttempts.current = 0;
    
    setPaymentState('processing');
    setRecoveryEvents([]);
    setRecoveryResult(null);
    setError(null);

    const txId = payload.id;
    setTransaction({ ...payload, id: txId });

    try {
      // 1. Open WS before sending POST and wait for connection
      await connectWs(txId);

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

      if (response.status === 'SUCCEEDED' || response.status === 'SUCCESS') {
        setPaymentState('succeeded_normal');
        isTerminalRef.current = true;
        cleanup();
      }
    } catch (e) {
      setError(e.message || 'Failed to connect to payment service');
      setPaymentState('error');
      isTerminalRef.current = true;
      cleanup();
    }
  }, [connectWs, cleanup]);

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
    cleanup();
    isTerminalRef.current = false;
    setPaymentState('idle');
    setTransaction(null);
    setRecoveryEvents([]);
    setRecoveryResult(null);
    setError(null);
  }, [cleanup]);

  // Ensure cleanup on unmount
  React.useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  const value = {
    paymentState,
    transaction,
    recoveryEvents,
    recoveryResult,
    error,
    wsStatus,
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
