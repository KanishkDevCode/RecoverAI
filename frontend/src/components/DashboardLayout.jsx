import React from 'react';

const DashboardLayout = ({ children }) => {
  return (
    <div className="dashboard-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-icon"></div>
          RecoverAI
        </div>
        
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ color: 'var(--text-main)', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
            📊 Metrics Dashboard
          </div>
          <div style={{ color: 'var(--text-muted)', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem', cursor: 'not-allowed' }}>
            ⚙️ Policy Engine (Locked)
          </div>
        </nav>
        
        <div style={{ marginTop: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Agent Mode: <strong>Ollama (Local)</strong><br />
          API: <strong>Secured</strong>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <div className="header">
          <h1>Revenue Recovery Command Center</h1>
          <p>Real-time autonomous intervention metrics and audit logs.</p>
        </div>
        
        {children}
      </main>
    </div>
  );
};

export default DashboardLayout;
