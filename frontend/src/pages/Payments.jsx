import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPayments } from '../services/api';
import { Search, Filter, Loader2 } from 'lucide-react';

const STATUS_COLORS = {
  SUCCESS: 'badge-success',
  CREATE_ESCALATION: 'badge-warning',
  STOP_AUTOMATION: 'badge-danger',
  FAILURE: 'badge-danger',
};

export default function Payments() {
  const navigate = useNavigate();
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  useEffect(() => {
    loadPayments();
  }, []);

  const loadPayments = async () => {
    try {
      setLoading(true);
      const data = await getPayments();
      setPayments(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const filtered = payments.filter(p => {
    const matchesSearch = !searchTerm || p.transaction_id.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || p.original_status === statusFilter || p.recovery_status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  if (loading) {
    return (
      <div className="page-loading">
        <Loader2 size={32} className="spin" />
        <span>Loading payments...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-error">
        <p>Unable to load payments: {error}</p>
        <button className="btn-outline" onClick={loadPayments}>Retry</button>
      </div>
    );
  }

  return (
    <div className="payments-page page-enter">
      <div className="page-header">
        <h1>Payments</h1>
        <button className="btn-primary" onClick={() => navigate('/checkout')}>New Payment</button>
      </div>

      {/* Filters */}
      <div className="payments-filters">
        <div className="search-box">
          <Search size={16} />
          <input placeholder="Search by transaction ID..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
        </div>
        <div className="filter-group">
          <Filter size={16} />
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="all">All Statuses</option>
            <option value="success">Normal Success</option>
            <option value="SUCCESS">Recovered</option>
            <option value="CREATE_ESCALATION">Escalated</option>
            <option value="STOP_AUTOMATION">Stopped</option>
          </select>
        </div>
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state-title">No payments found</p>
          <p className="empty-state-description">Process a payment from the checkout page or adjust your search filters.</p>
        </div>
      ) : (
        <div className="payments-table-wrap">
          <table className="payments-table">
            <thead>
              <tr>
                <th>Transaction</th>
                <th>Amount</th>
                <th>Original Status</th>
                <th>Recovery Status</th>
                <th>Final Date</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.transaction_id} onClick={() => navigate(`/payments/${p.transaction_id}`)} className="clickable-row">
                  <td className="mono">{p.transaction_id.substring(0, 16)}...</td>
                  <td>₹{p.amount?.toLocaleString()}</td>
                  <td>
                    <span className={`status-badge ${p.original_status === 'success' ? 'badge-success' : 'badge-danger'}`}>
                      {p.original_status?.toUpperCase()}
                    </span>
                  </td>
                  <td>
                    {p.recovery_status ? (
                      <span className={`status-badge ${STATUS_COLORS[p.recovery_status] || 'badge-neutral'}`}>
                        {p.recovery_status === 'SUCCESS' ? 'RECOVERED' : p.recovery_status === 'CREATE_ESCALATION' ? 'ESCALATED' : p.recovery_status}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{p.timestamp ? new Date(p.timestamp).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
