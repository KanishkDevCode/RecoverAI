import React from 'react';

const TransactionTable = ({ transactions }) => {
  if (!transactions || transactions.length === 0) {
    return <div style={{ color: 'var(--text-muted)' }}>No transactions found.</div>;
  }

  const getBadgeClass = (outcome) => {
    switch(outcome) {
      case 'SUCCESS': return 'badge success';
      case 'CREATE_ESCALATION': return 'badge escalated';
      case 'STOP_AUTOMATION': return 'badge stopped';
      default: return 'badge retry';
    }
  };

  return (
    <div className="glass-card" style={{ padding: '1rem' }}>
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Transaction ID</th>
              <th>Amount</th>
              <th>AI Diagnosis</th>
              <th>Policy Action</th>
              <th>Final Outcome</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((txn, index) => (
              <tr key={txn.transaction_id + index} className="row">
                <td className="font-mono">{txn.transaction_id.substring(0, 15)}...</td>
                <td style={{ fontWeight: 600 }}>${txn.amount.toFixed(2)}</td>
                <td style={{ maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {txn.agent_diagnosis}
                </td>
                <td>{txn.policy_action}</td>
                <td>
                  <span className={getBadgeClass(txn.outcome)}>
                    {txn.outcome}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TransactionTable;
