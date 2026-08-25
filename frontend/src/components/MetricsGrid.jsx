import React from 'react';

const MetricsGrid = ({ metrics }) => {
  if (!metrics) return null;

  return (
    <div className="metrics-grid">
      <div className="glass-card metric-card">
        <div className="metric-title">Revenue At Risk</div>
        <div className="metric-value">
          ${metrics.revenue_at_risk.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>
      
      <div className="glass-card metric-card metric-recovered">
        <div className="metric-title">Total Recovered</div>
        <div className="metric-value">
          ${metrics.revenue_recovered.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>

      <div className="glass-card metric-card">
        <div className="metric-title">Recovery Rate</div>
        <div className="metric-value" style={{ color: 'var(--accent-blue)' }}>
          {metrics.recovery_rate.toFixed(2)}%
        </div>
      </div>

      <div className="glass-card metric-card">
        <div className="metric-title">Total Processed</div>
        <div className="metric-value" style={{ fontSize: '2rem' }}>
          {metrics.total_transactions.toLocaleString()}
          <span style={{ fontSize: '1rem', color: 'var(--text-muted)', marginLeft: '10px' }}>
            ({metrics.successful_actions} successes)
          </span>
        </div>
      </div>
    </div>
  );
};

export default MetricsGrid;
