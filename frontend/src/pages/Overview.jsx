import React, { useEffect, useState } from 'react';
import { getDashboardMetrics, getPayments } from '../services/api';
import { Loader2, DollarSign, RefreshCcw, Activity, ArrowRightLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Overview() {
  const [metrics, setMetrics] = useState(null);
  const [recentPayments, setRecentPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [m, t] = await Promise.all([getDashboardMetrics(), getPayments(10)]);
      setMetrics(m);
      setRecentPayments(t);
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
        <span>Loading dashboard...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-error">
        <p>Unable to load dashboard: {error}</p>
        <button className="btn-outline" onClick={loadData}>Retry</button>
      </div>
    );
  }

  const getUnifiedStatus = (txn) => {
    if (txn.recovery_status === 'SUCCESS' || txn.original_status === 'recovered') return 'Recovered';
    if (txn.original_status === 'success') return 'Succeeded';
    return txn.original_status === 'failed' ? 'Failed' : txn.original_status;
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'Recovered': return 'badge-success';
      case 'Succeeded': return 'badge-success';
      case 'Failed': return 'badge-danger';
      default: return 'badge-neutral';
    }
  };

  return (
    <div className="overview-page" style={{ maxWidth: '1000px' }}>
      <div className="page-header">
        <h1>Overview</h1>
        <button className="btn-outline" onClick={loadData}>
          <RefreshCcw size={16} /> Refresh
        </button>
      </div>

      {metrics && (
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-icon"><Activity size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Payments</span>
              <span className="metric-value">{metrics.total_payments_count || 0}</span>
            </div>
          </div>
          <div className="metric-card success">
            <div className="metric-icon"><DollarSign size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Revenue</span>
              <span className="metric-value">₹{metrics.total_revenue?.toLocaleString() || '0'}</span>
            </div>
          </div>
          <div className="metric-card success">
            <div className="metric-icon"><RefreshCcw size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Recovered</span>
              <span className="metric-value">₹{metrics.revenue_recovered?.toLocaleString() || '0'}</span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><ArrowRightLeft size={20} /></div>
            <div className="metric-body">
              <span className="metric-label">Refunds</span>
              <span className="metric-value">₹{metrics.total_refunds?.toLocaleString() || '0'}</span>
            </div>
          </div>
        </div>
      )}

      <div className="recent-section">
        <h2>Recent Payments</h2>
        {recentPayments.length === 0 ? (
          <div className="empty-state"><p>No payments yet.</p></div>
        ) : (
          <div className="payments-table-wrap">
            <table className="payments-table">
              <thead>
                <tr>
                  <th>TXN</th>
                  <th>Customer</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recentPayments.map((txn) => {
                  const unifiedStatus = getUnifiedStatus(txn);
                  return (
                    <tr 
                      key={txn.transaction_id} 
                      className="clickable-row" 
                      onClick={() => navigate(`/payments/${txn.transaction_id}`)}
                    >
                      <td className="mono" style={{ width: '120px' }}>
                        {txn.transaction_id.substring(0, 12)}...
                      </td>
                      <td>{txn.customer_id}</td>
                      <td>₹{txn.amount?.toLocaleString()}</td>
                      <td>
                        <span className={`status-badge ${getStatusBadge(unifiedStatus)}`}>
                          {unifiedStatus}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
