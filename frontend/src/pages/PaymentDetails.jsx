import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getPaymentDetails, getAuditTrail } from '../services/api';
import { ArrowLeft, Loader2, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';

export default function PaymentDetails() {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const [details, setDetails] = useState(null);
  const [auditTrail, setAuditTrail] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [manualRecoveryDone, setManualRecoveryDone] = useState(false);

  useEffect(() => {
    loadData();
  }, [transactionId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [paymentData, auditData] = await Promise.all([
        getPaymentDetails(transactionId),
        getAuditTrail(transactionId).catch(() => []) // Audit might not exist if it didn't fail
      ]);
      setDetails(paymentData);
      setAuditTrail(auditData);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <Loader2 size={32} className="spin" />
        <span>Loading transaction details...</span>
      </div>
    );
  }

  if (error || !details) {
    return (
      <div className="page-error">
        <p>Unable to load details: {error}</p>
        <button className="btn-outline" onClick={() => navigate('/payments')}>Back to Payments</button>
      </div>
    );
  }

  const { recovery } = details;
  const isRecovered = recovery?.outcome_status === 'SUCCESS' || recovery?.outcome_status === 'SUCCEEDED' || recovery?.outcome_status === 'AUTHORIZED';
  const finalStatus = details.original_status === 'success' ? 'SUCCEEDED' : (recovery?.outcome_status || 'FAILED');

  return (
    <div className="detail-page page-enter">
      <button className="back-link" onClick={() => navigate('/payments')}>
        <ArrowLeft size={16} /> Back to Payments
      </button>

      <div className="detail-card">
        {/* Header */}
        <div className="detail-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 className="detail-txn-id">{transactionId}</h1>
            <span className={`status-badge ${finalStatus === 'SUCCEEDED' ? 'badge-success' : finalStatus === 'FAILED' ? 'badge-danger' : 'badge-warning'}`}>
              {finalStatus}
            </span>
          </div>
          
          {/* Action Matrix CTA Block */}
          <div className="detail-actions">
            {finalStatus === 'FAILED' && (
              <button className="btn-primary" onClick={() => navigate('/checkout')}>Try Again</button>
            )}
            {finalStatus === 'AWAITING_CUSTOMER' && (
              <button 
                style={{ padding: '0.4rem 0.8rem', fontSize: '0.875rem', backgroundColor: '#f59e0b', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}
                onClick={async () => {
                  try {
                    const { simulateManualRecovery } = await import('../services/api');
                    await simulateManualRecovery(transactionId);
                    setManualRecoveryDone(true);
                    loadData(); // refresh to show updated status
                  } catch (err) {
                    alert('Manual recovery failed: ' + err.message);
                  }
                }}
              >
                Initiate Recovery
              </button>
            )}
            {finalStatus === 'ESCALATED' && (
              <button className="btn-outline">Check Status</button>
            )}
            {finalStatus === 'SUCCEEDED' && !details.refund_status && (
              <button 
                className="btn-outline" 
                onClick={async () => {
                  try {
                    const { initiateRefund } = await import('../services/api');
                    await initiateRefund(transactionId);
                    loadData(); // refresh to show refund processing
                  } catch (err) {
                    alert('Refund failed: ' + err.message);
                  }
                }}
              >
                Initiate Refund
              </button>
            )}
            {details.refund_status === 'REFUND_REQUESTED' && (
              <button className="btn-outline" disabled>Refund request received</button>
            )}
            {details.refund_status === 'REFUND_PROCESSING' && (
              <button className="btn-outline" disabled>Refund is being processed</button>
            )}
            {details.refund_status === 'REFUNDED' && (
              <button className="btn-success" disabled>
                <CheckCircle2 size={16} style={{ display: 'inline', marginRight: '4px' }} /> Refund successfully completed
              </button>
            )}
            {details.refund_status === 'REFUND_FAILED' && (
              <button className="btn-danger" disabled>
                <XCircle size={16} style={{ display: 'inline', marginRight: '4px' }} /> Refund processing failed
              </button>
            )}
          </div>
        </div>

        {/* Original Payment Details */}
        <div className="detail-section">
          <h3>Original Payment</h3>
          <div className="detail-grid">
            <div className="detail-item">
              <span className="label">Amount</span>
              <span className="value">₹{details.amount.toLocaleString()}</span>
            </div>
            <div className="detail-item">
              <span className="label">Customer</span>
              <span className="value">{details.customer_id}</span>
            </div>
            <div className="detail-item">
              <span className="label">Status</span>
              <span className={`value ${details.original_status === 'success' ? 'text-success' : 'text-danger'}`}>
                {details.original_status.toUpperCase()}
              </span>
            </div>
            <div className="detail-item">
              <span className="label">Date</span>
              <span className="value">{new Date(details.created_at).toLocaleString()}</span>
            </div>
            {details.failure_code && (
              <div className="detail-item full-width">
                <span className="label">Gateway Failure</span>
                <span className="value text-danger">{details.failure_code}: {details.failure_reason}</span>
              </div>
            )}
          </div>
        </div>

        {/* RecoverAI Section */}
        {recovery && (
          <div className="detail-section" style={{ marginTop: '1rem' }}>
            <h3>RecoverAI Recovery</h3>
            <div className="detail-grid">
              <div className="detail-item">
                <span className="label">AI Diagnosis</span>
                <span className="value">{recovery.agent_diagnosis || 'N/A'}</span>
              </div>
              <div className="detail-item">
                <span className="label">Provider Used</span>
                <span className="value" style={{ textTransform: 'capitalize', fontWeight: 600 }}>{recovery.provider_used || 'N/A'}</span>
              </div>
              <div className="detail-item">
                <span className="label">Policy Action</span>
                <span className={`value ${recovery.policy_decision === 'ALLOWED' ? 'text-success' : 'text-danger'}`}>
                  {recovery.policy_decision || 'N/A'}
                </span>
              </div>
              {recovery.policy_reason && (
                <div className="detail-item full-width">
                  <span className="label">Policy Reason</span>
                  <span className="value">{recovery.policy_reason}</span>
                </div>
              )}
              <div className="detail-item full-width">
                <span className="label">Final Outcome</span>
                {(() => {
                  if (recovery.outcome_status === 'WAITING' || recovery.outcome_status === 'EXECUTING') {
                    return (
                      <span className="value flex-align gap-2" style={{ display: 'flex', alignItems: 'center', color: '#3b82f6', fontWeight: 600 }}>
                        Recovery in Progress
                        <Loader2 size={16} className="spin" style={{ color: '#3b82f6' }} />
                      </span>
                    );
                  }
                  if (recovery.outcome_status === 'AWAITING_CUSTOMER') {
                    return (
                      <span className="value flex-align gap-2 text-warning" style={{ display: 'flex', alignItems: 'center', fontWeight: 600 }}>
                        Awaiting Customer
                      </span>
                    );
                  }
                  if (recovery.outcome_status === 'ESCALATED' || recovery.outcome_status === 'STOPPED') {
                    return (
                      <span className="value flex-align gap-2 text-danger" style={{ display: 'flex', alignItems: 'center', fontWeight: 600 }}>
                        Recovery not possible
                        <XCircle size={16} className="text-danger" />
                      </span>
                    );
                  }
                  return (
                    <span className={`value flex-align gap-2 ${isRecovered ? 'text-success' : 'text-danger'}`} style={{ display: 'flex', alignItems: 'center', fontWeight: 600 }}>
                      {recovery.outcome_status} {recovery.executed_action ? `(${recovery.executed_action})` : ''}
                    </span>
                  );
                })()}
              </div>
              {recovery.latency_ms != null && (
                <div className="detail-item full-width" style={{ marginTop: '0.5rem' }}>
                  <span className="label">Recovery Latency</span>
                  <span className="value">{recovery.latency_ms} ms</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Audit Trail */}
        {auditTrail.length > 0 && (
          <div className="detail-section" style={{ marginTop: '1rem' }}>
            <h3>Audit Trail</h3>
            <div className="audit-timeline">
              {auditTrail.map((entry, i) => (
                <div key={entry.id || i} className="audit-entry">
                  <div className="audit-icon">
                    {entry.new_state === 'SUCCEEDED' || entry.new_state === 'DONE'
                      ? <CheckCircle2 size={16} className="text-success" />
                      : entry.new_state === 'STOPPED' || entry.new_state === 'ESCALATED' || entry.new_state === 'FAILED'
                      ? <XCircle size={16} className="text-danger" />
                      : <div className="audit-dot" />
                    }
                    {i < auditTrail.length - 1 && <div className="audit-line" />}
                  </div>
                  <div className="audit-content">
                    <div className="audit-header-row">
                      <span className="audit-event">{entry.event_type}</span>
                      <span className="audit-time">{new Date(entry.timestamp).toLocaleTimeString()}</span>
                    </div>
                    {entry.previous_state && (
                      <span className="audit-state">{entry.previous_state} → {entry.new_state}</span>
                    )}
                    {entry.reasoning && (
                      <p className="audit-reason">{entry.reasoning}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
