import React from 'react';
import { useNavigate } from 'react-router-dom';
import { usePayment } from '../context/PaymentContext';
import { XCircle, AlertTriangle } from 'lucide-react';

export default function PaymentFailed() {
  const navigate = useNavigate();
  const { transaction, recoveryEvents, resetPayment, paymentState } = usePayment();

  const amount = transaction?.amount || 0;
  const txId = transaction?.id || 'N/A';
  const method = transaction?.payment_method || 'N/A';

  // Extract the policy reason if available
  const policyEvent = recoveryEvents.find(e => e.event_type === 'POLICY_DECISION');
  const policyReason = policyEvent?.data?.reason || '';
  const wasEscalated = policyEvent?.data?.final_action === 'CREATE_ESCALATION';
  const wasStopped = policyEvent?.data?.final_action === 'STOP_AUTOMATION';
  const wasMessageSent = policyEvent?.data?.final_action === 'SEND_RECOVERY_MESSAGE';
  const wasWaiting = policyEvent?.data?.final_action === 'WAIT_AND_RETRY';
  
  const isUnknown = paymentState === 'unknown';

  const handleRetry = () => {
    resetPayment();
    navigate('/checkout');
  };

  return (
    <div className="result-page">
      <div className="result-card">
        <div className={`result-icon ${isUnknown ? 'unknown text-warning' : (wasMessageSent || wasWaiting) ? 'text-primary' : 'fail'}`}>
          {isUnknown || wasMessageSent || wasWaiting ? <AlertTriangle size={56} /> : <XCircle size={56} />}
        </div>
        <h1 className="result-title">
          {isUnknown ? 'Payment status is being verified' : 
           wasEscalated ? 'Payment requires manual review' :
           wasStopped ? 'Recovery stopped' :
           wasMessageSent ? 'Recovery message sent' :
           wasWaiting ? 'Recovery scheduled' :
           'Payment could not be recovered'}
        </h1>
        <p className="result-amount">₹{amount.toLocaleString()}</p>
        <p className="result-message">
          {isUnknown ? 'We are checking with the bank to confirm if the money moved.' : 
           wasMessageSent ? 'Payment remains pending / awaiting customer action.' :
           wasWaiting ? 'Recovery scheduled / waiting for retry.' :
           'Your payment could not be completed.'}
        </p>

        {wasEscalated && (
          <div className="escalated-badge">
            Escalated to manual review
          </div>
        )}
        {wasStopped && (
          <div className="stopped-badge">
            Automation stopped — policy restriction
          </div>
        )}

        <div className="result-details">
          <div className="result-row"><span>Transaction ID</span><span className="mono">{txId}</span></div>
          <div className="result-row"><span>Amount</span><span>₹{amount.toLocaleString()}</span></div>
          <div className="result-row"><span>Payment Method</span><span>{method.toUpperCase()}</span></div>
          <div className="result-row">
            <span>Gateway Executions</span>
            <span className="mono font-semibold">
              {paymentState === 'failed' ? '1' : 
               (1 + recoveryEvents.filter(e => e.event_type === 'GATEWAY_RESULT').length)}
            </span>
          </div>
          <div className="result-row">
            <span>Final Status</span>
            <span className={isUnknown || wasMessageSent || wasWaiting ? "text-warning" : "text-danger"}>
              {isUnknown ? 'UNKNOWN' : 
               wasEscalated ? 'ESCALATED' : 
               wasMessageSent ? 'AWAITING CUSTOMER' :
               wasWaiting ? 'WAITING' :
               'FAILED'}
            </span>
          </div>
        </div>

        <div className="result-actions">
          <button className="btn-primary" onClick={handleRetry}>Try Again</button>
          <button className="btn-outline" onClick={() => navigate('/payments')}>View Payments</button>
        </div>
      </div>
    </div>
  );
}
