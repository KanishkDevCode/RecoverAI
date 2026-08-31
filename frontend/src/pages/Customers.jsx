import React, { useEffect, useState } from 'react';
import { getCustomers } from '../services/api';
import { Loader2, Users } from 'lucide-react';

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const data = await getCustomers();
      setCustomers(data);
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
        <span>Loading customers...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-error">
        <p>Unable to load customers: {error}</p>
        <button className="btn-outline" onClick={loadData}>Retry</button>
      </div>
    );
  }

  return (
    <div className="payments-page page-enter">
      <div className="page-header">
        <h1>Customers</h1>
        <button className="btn-outline" onClick={loadData}>
          <Users size={16} /> Refresh
        </button>
      </div>

      {customers.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state-title">No customers found</p>
          <p className="empty-state-description">Customers will appear here once they process their first payment.</p>
        </div>
      ) : (
        <div className="payments-table-wrap">
          <table className="payments-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Payments</th>
                <th>Revenue</th>
                <th>Recovered</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.customer_id}>
                  <td className="font-semibold">{c.customer_id}</td>
                  <td>{c.payments}</td>
                  <td>₹{c.revenue?.toLocaleString()}</td>
                  <td className={c.recovered > 0 ? "text-success" : ""}>
                    {c.recovered > 0 ? `₹${c.recovered.toLocaleString()}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
