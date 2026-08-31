import React, { useEffect, useState } from 'react';
import { getHealthCheck } from '../services/api';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';

export default function Settings() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkHealth();
  }, []);

  const checkHealth = async () => {
    try {
      setLoading(true);
      const data = await getHealthCheck();
      setHealth(data);
    } catch {
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-page page-enter">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-grid">
        {/* Environment */}
        <div className="settings-card">
          <h3>Environment</h3>
          <div className="settings-row">
            <span>Mode</span>
            <span className="status-badge badge-warning">TEST</span>
          </div>
          <div className="settings-row">
            <span>API Base URL</span>
            <span className="mono">{import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'}</span>
          </div>
        </div>

        {/* System Status */}
        <div className="settings-card">
          <h3>System Status</h3>
          <div className="settings-row">
            <span>API Server</span>
            {loading ? (
              <Loader2 size={16} className="spin" />
            ) : health ? (
              <span className={`connection-status ${health.status === 'ready' ? 'online' : 'offline'}`}>
                {health.status === 'ready' ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {health.status === 'ready' ? 'Healthy' : 'Unavailable'}
              </span>
            ) : (
              <span className="connection-status offline"><XCircle size={14} /> Offline</span>
            )}
          </div>
          
          <div className="settings-row">
            <span>Database (PostgreSQL)</span>
            {loading ? (
              <Loader2 size={16} className="spin" />
            ) : health ? (
              <span className={`connection-status ${health.database === 'healthy' ? 'online' : 'offline'}`}>
                {health.database === 'healthy' ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {health.database === 'healthy' ? 'Connected' : 'Error'}
              </span>
            ) : (
              <span className="connection-status offline"><XCircle size={14} /> Offline</span>
            )}
          </div>

          <div className="settings-row">
            <span>Redis & Workers</span>
            {loading ? (
              <Loader2 size={16} className="spin" />
            ) : health ? (
              <span className={`connection-status ${health.redis === 'healthy' ? 'online' : 'offline'}`}>
                {health.redis === 'healthy' ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {health.redis === 'healthy' ? 'Connected' : 'Error'}
              </span>
            ) : (
              <span className="connection-status offline"><XCircle size={14} /> Offline</span>
            )}
          </div>
          <button className="btn-outline btn-sm" onClick={checkHealth}>Refresh Status</button>
        </div>

        {/* Recovery Policy */}
        <div className="settings-card">
          <h3>Recovery Policy</h3>
          <div className="settings-row">
            <span>Recovery Engine</span>
            <span>Enabled</span>
          </div>
          <div className="settings-row">
            <span>Policy Version</span>
            <span className="mono">v2-deterministic</span>
          </div>
          <div className="settings-row">
            <span>Max Auto Amount</span>
            <span>₹5,000</span>
          </div>
          <div className="settings-row">
            <span>Max Retries</span>
            <span>2</span>
          </div>
        </div>

        {/* AI Configuration */}
        <div className="settings-card">
          <h3>AI Configuration</h3>
          <div className="settings-row">
            <span>LLM Provider</span>
            <span>Mock (No API key configured)</span>
          </div>
          <div className="settings-row">
            <span>ML Model</span>
            <span className="mono">GradientBoosting v2</span>
          </div>
        </div>
      </div>
    </div>
  );
}
