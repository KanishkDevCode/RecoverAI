import React, { useEffect, useState } from 'react';
import { getDashboardMetrics, getPayments } from '../services/api';
import { Loader2, TrendingUp, ShieldCheck, AlertTriangle, XCircle, Activity } from 'lucide-react';

export default function RecoveryConsole() {
  const [metrics, setMetrics] = useState(null);
  const [recentAttempts, setRecentAttempts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [m, t] = await Promise.all([getDashboardMetrics(), getPayments(20)]);
      setMetrics(m);
      setRecentAttempts(t);
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
        <span>Loading recovery metrics...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-error">
        <p>Unable to load recovery data: {error}</p>
        <button className="btn-outline" onClick={loadData}>Retry</button>
      </div>
    );
  }

  return (
    <div className="recovery-page page-enter">
      <div className="page-header">
        <h1>Recovery Console</h1>
        <button className="btn-outline" onClick={loadData}>
          <Activity size={16} /> Refresh
        </button>
      </div>

      {/* Metrics Cards */}
      {metrics && (
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-icon"><Activity size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">ML Predictions</span>
              <span className="metric-value">{metrics.ml_predictions || 0}</span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><Activity size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">AI Recommendations</span>
              <span className="metric-value">{metrics.ai_recommendations || 0}</span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><Activity size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Gateway Executions</span>
              <span className="metric-value">{metrics.gateway_executions || 0}</span>
            </div>
          </div>
          <div className="metric-card success">
            <div className="metric-icon"><ShieldCheck size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Policy Allowed</span>
              <span className="metric-value">{metrics.policy_allowed || 0}</span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><AlertTriangle size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Policy Denied</span>
              <span className="metric-value">{metrics.policy_denied || 0}</span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><AlertTriangle size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Escalations</span>
              <span className="metric-value">{metrics.escalations || 0}</span>
            </div>
          </div>
        </div>
      )}

      {/* Recent Attempts */}
      <div className="recent-section">
        <h2>Recent Recovery Attempts</h2>
        {recentAttempts.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No recovery attempts yet</p>
            <p className="empty-state-description">Failed payments that pass ML analysis will appear here.</p>
          </div>
        ) : (
          <div className="payments-table-wrap">
            <table className="payments-table">
              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Amount</th>
                  <th>AI Diagnosis</th>
                  <th>Policy</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {recentAttempts.map((a) => (
                  <tr key={a.transaction_id}>
                    <td className="mono">{a.transaction_id?.substring(0, 16)}...</td>
                    <td>₹{a.amount?.toLocaleString()}</td>
                    <td className="truncate" title={a.agent_diagnosis || 'N/A'}>{a.agent_diagnosis || '—'}</td>
                    <td>
                      <span className={a.policy_action === 'ALLOWED' ? 'text-success' : a.policy_action === 'DENIED' ? 'text-danger' : ''}>
                        {a.policy_action || '—'}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${
                        a.recovery_status_attempt === 'SUCCESS' || a.recovery_status_attempt === 'SUCCEEDED' ? 'badge-success' : 
                        a.recovery_status_attempt ? 'badge-danger' : 'badge-neutral'
                      }`}>
                        {a.recovery_status_attempt === 'SUCCESS' || a.recovery_status_attempt === 'SUCCEEDED' ? 'Recovered' : (a.recovery_status_attempt || 'Pending')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
