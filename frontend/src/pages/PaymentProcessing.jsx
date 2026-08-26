import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePayment } from '../context/PaymentContext';
import { Loader2, CheckCircle2, XCircle, AlertTriangle, Shield, Clock } from 'lucide-react';

/* Map backend event types to human-friendly pipeline steps */
const PIPELINE_STEPS = [
  { key: 'ML_PREDICTION', label: 'Recovery Analysis', icon: 'analysis' },
  { key: 'AI_RECOMMENDATION', label: 'AI Recommendation', icon: 'ai' },
  { key: 'POLICY_DECISION', label: 'Safety Check', icon: 'policy' },
  { key: 'STATE_CHANGE', label: 'State Transition', icon: 'state' },
  { key: 'GATEWAY_RESULT', label: 'Payment Gateway', icon: 'gateway' },
  { key: 'RECOVERY_COMPLETE', label: 'Final Result', icon: 'result' },
];

function getStepIcon(step, completed) {
  if (completed) return <CheckCircle2 size={18} className="step-icon completed" />;
  return <div className="step-icon pending" />;
}

export default function PaymentProcessing() {
  const navigate = useNavigate();
  const { paymentState, transaction, recoveryEvents, recoveryResult, error } = usePayment();

  // Build a set of completed event types
  const completedTypes = new Set(recoveryEvents.map(e => e.event_type));

  // Get data for specific events
  const getEventData = (type) => {
    const evt = recoveryEvents.find(e => e.event_type === type);
    return evt ? evt.data : null;
  };

  // Navigate to result pages when terminal state is reached
  useEffect(() => {
    if (paymentState === 'succeeded_normal' || paymentState === 'succeeded_recovered') {
      const timer = setTimeout(() => navigate('/payment-success'), 1500);
      return () => clearTimeout(timer);
    }
    if (paymentState === 'recovery_failed') {
      const timer = setTimeout(() => navigate('/payment-failed'), 1500);
      return () => clearTimeout(timer);
    }
  }, [paymentState, navigate]);

  const mlData = getEventData('ML_PREDICTION');
  const aiData = getEventData('AI_RECOMMENDATION');
  const policyData = getEventData('POLICY_DECISION');
  const gatewayData = getEventData('GATEWAY_RESULT');
  const failData = getEventData('PAYMENT_FAILED');

  return (
    <div className="processing-page">
      <div className="processing-card">
        {/* Header */}
        <div className="processing-header">
          {paymentState === 'processing' && (
            <>
              <Loader2 size={40} className="spin" />
              <h2>Processing your payment</h2>
              <p className="processing-sub">Please do not refresh or press back</p>
            </>
          )}
          {paymentState === 'failed' && (
            <>
              <XCircle size={40} className="icon-fail" />
              <h2>Payment couldn't be completed</h2>
              <p className="processing-sub">RecoverAI is checking whether this payment can be recovered.</p>
            </>
          )}
          {paymentState === 'recovering' && (
            <>
              <Shield size={40} className="icon-recovering" />
              <h2>Recovery in progress</h2>
              <p className="processing-sub">RecoverAI is analyzing and attempting recovery.</p>
            </>
          )}
          {paymentState === 'succeeded_normal' && (
            <>
              <CheckCircle2 size={40} className="icon-success" />
              <h2>Payment successful</h2>
            </>
          )}
          {paymentState === 'succeeded_recovered' && (
            <>
              <CheckCircle2 size={40} className="icon-success" />
              <h2>Payment recovered</h2>
            </>
          )}
          {paymentState === 'recovery_failed' && (
            <>
              <XCircle size={40} className="icon-fail" />
              <h2>Recovery was not possible</h2>
            </>
          )}
          {paymentState === 'unknown' && (
            <>
              <AlertTriangle size={40} className="icon-unknown" />
              <h2>Payment verification in progress</h2>
              <p className="processing-sub">We're checking whether your payment was completed successfully. Please don't retry yet.</p>
            </>
          )}
          {paymentState === 'error' && (
            <>
              <XCircle size={40} className="icon-fail" />
              <h2>Unable to connect to payment service</h2>
              <p className="processing-sub">{error}</p>
            </>
          )}
        </div>

        {/* Transaction Info */}
        {transaction && (
          <div className="processing-txn-info">
            <div className="txn-row"><span className="txn-label">Transaction</span><span className="txn-value mono">{transaction.id}</span></div>
            <div className="txn-row"><span className="txn-label">Amount</span><span className="txn-value">₹{transaction.amount.toLocaleString()}</span></div>
            
            {/* Display Gateway Executions as evidence of safety */}
            <div className="txn-row">
              <span className="txn-label">Gateway Executions</span>
              <span className="txn-value mono font-semibold">
                {paymentState === 'processing' ? '0' : (
                  (paymentState === 'failed' || paymentState === 'recovering' || paymentState === 'recovery_failed' || paymentState === 'succeeded_recovered' || paymentState === 'unknown' || failData) ? 
                    (1 + recoveryEvents.filter(e => e.event_type === 'GATEWAY_RESULT').length) : 
                  (paymentState === 'succeeded_normal' ? '1' : '0')
                )}
              </span>
            </div>
          </div>
        )}

        {/* Timeline */}
        <div className="pipeline-timeline">
          <h3 className="pipeline-title">Payment Timeline</h3>
          
          {/* Initial Payment Attempt Steps */}
          <div className="pipeline-step completed">
            <CheckCircle2 size={18} className="step-icon completed" />
            <div className="step-content">
              <span className="step-label">Payment initiated</span>
            </div>
          </div>
          
          {(paymentState === 'failed' || paymentState === 'recovering' || paymentState === 'recovery_failed' || paymentState === 'succeeded_recovered' || paymentState === 'unknown' || failData) && (
             <>
               <div className="pipeline-step completed">
                 <CheckCircle2 size={18} className="step-icon completed" />
                 <div className="step-content">
                   <span className="step-label">Payment gateway</span>
                 </div>
               </div>
               <div className="pipeline-step completed">
                 <XCircle size={18} className="step-icon text-danger" />
                 <div className="step-content">
                   <span className="step-label">Payment failed</span>
                   {failData && <span className="step-data text-danger">Initial attempt: {failData.failure_code.toUpperCase()}</span>}
                 </div>
               </div>
             </>
          )}

          {/* Recovery Pipeline Timeline */}
          {recoveryEvents.length > 0 && PIPELINE_STEPS.map((step) => {
            const isCompleted = completedTypes.has(step.key);
            if (!isCompleted && step.key !== 'RECOVERY_COMPLETE') {
              // Only show steps that have happened or are next
              const allKeys = PIPELINE_STEPS.map(s => s.key);
              const lastCompletedIdx = Math.max(...recoveryEvents.map(e => allKeys.indexOf(e.event_type)));
              const thisIdx = allKeys.indexOf(step.key);
              if (thisIdx > lastCompletedIdx + 1) return null;
            }

            return (
              <div key={step.key} className={`pipeline-step ${isCompleted ? 'completed' : 'pending'}`}>
                {getStepIcon(step, isCompleted)}
                <div className="step-content">
                  <span className="step-label">{step.label}</span>
                  {/* Inline data for each step */}
                  {step.key === 'ML_PREDICTION' && mlData && (
                    <span className="step-data">{(mlData.probability * 100).toFixed(0)}% recovery probability</span>
                  )}
                  {step.key === 'AI_RECOMMENDATION' && aiData && (
                    <span className="step-data">{aiData.recommended_action}</span>
                  )}
                  {step.key === 'POLICY_DECISION' && policyData && (
                    <span className={`step-data ${policyData.is_allowed ? 'text-success' : 'text-danger'}`}>
                      {policyData.is_allowed ? 'APPROVED' : 'DENIED'} — {policyData.final_action}
                    </span>
                  )}
                  {step.key === 'GATEWAY_RESULT' && gatewayData && (
                    <span className={`step-data ${gatewayData.status === 'SUCCEEDED' ? 'text-success' : 'text-danger'}`}>
                      {gatewayData.status}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Actions */}
        {(paymentState === 'error' || paymentState === 'unknown') && (
          <div className="processing-actions">
            <button className="btn-outline" onClick={() => navigate('/checkout')}>Back to Checkout</button>
          </div>
        )}
      </div>
    </div>
  );
}
