import React from 'react';
import { useNavigate } from 'react-router-dom';
import { usePayment } from '../context/PaymentContext';
import { CheckCircle2, Shield } from 'lucide-react';

export default function PaymentSuccess() {
  const navigate = useNavigate();
  const { transaction, recoveryEvents, resetPayment, paymentState } = usePayment();

  const amount = transaction?.amount || 0;
  const txId = transaction?.id || 'N/A';
  const method = transaction?.payment_method || 'N/A';
  const wasRecovered = paymentState === 'succeeded_recovered';

  const handleNewPayment = () => {
    resetPayment();
    navigate('/checkout');
  };

  return (
    <div className="result-page">
      <div className="result-card">
        <div className="result-icon success">
          <CheckCircle2 size={56} />
        </div>
        <h1 className="result-title">
          {wasRecovered ? 'Payment Recovered' : 'Payment Successful'}
        </h1>
        <p className="result-amount">₹{amount.toLocaleString()}</p>
        <p className="result-message">
          {wasRecovered 
            ? 'RecoverAI successfully recovered this failed payment.' 
            : 'Payment completed successfully.'}
        </p>

        {wasRecovered && (
          <div className="recovered-badge">
            <Shield size={16} /> Payment recovered by RecoverAI
          </div>
        )}

        <div className="receipt-details">
          <div className="receipt-row"><span>Amount</span><span className="font-semibold">₹{transaction?.amount.toLocaleString()}</span></div>
          <div className="receipt-row"><span>Transaction ID</span><span className="mono">{transaction?.id}</span></div>
          <div className="receipt-row"><span>Date</span><span>{new Date().toLocaleDateString()}</span></div>
          <div className="receipt-row"><span>Payment Method</span><span className="uppercase">{transaction?.payment_method}</span></div>
          <div className="receipt-row">
            <span>Gateway Executions</span>
            <span className="mono font-semibold">
              {paymentState === 'succeeded_normal' ? '1' : 
               (1 + recoveryEvents.filter(e => e.event_type === 'GATEWAY_RESULT').length)}
            </span>
          </div>
        </div>

        <div className="result-actions">
          <button className="btn-primary" onClick={() => navigate(`/payments`)}>View Payments</button>
          <button className="btn-outline" onClick={handleNewPayment}>New Payment</button>
        </div>
      </div>
    </div>
  );
}
