import React from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { CreditCard, LayoutDashboard, Settings, Shield, Activity, Users, ArrowLeft } from 'lucide-react';

export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const isCustomerRoute = ['/checkout', '/payment-processing', '/payment-success', '/payment-failed'].includes(location.pathname);

  return (
    <div className={isCustomerRoute ? "customer-layout" : "app-layout"}>
      {!isCustomerRoute && (
        <nav className="app-nav">
          <div className="nav-brand">
            <Shield size={20} />
            <span>RecoverAI</span>
          </div>
          <div className="nav-links">
            <NavLink to="/" className={({ isActive }) => isActive && location.pathname === '/' ? 'nav-link active' : 'nav-link'}>
              <LayoutDashboard size={16} /> Overview
            </NavLink>
            <NavLink to="/payments" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <Activity size={16} /> Payments
            </NavLink>
            <NavLink to="/recovery" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <Activity size={16} /> Recovery
            </NavLink>
            <NavLink to="/customers" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <Users size={16} /> Customers
            </NavLink>
            <NavLink to="/settings" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <Settings size={16} /> Settings
            </NavLink>
            
            <div style={{ marginTop: '2rem', borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
              <NavLink to="/checkout" className="nav-link">
                <CreditCard size={16} /> Checkout (Demo)
              </NavLink>
            </div>
          </div>
          <div className="nav-env">
            <span className="env-badge" style={{ background: '#dcfce7', color: '#166534' }}>MERCHANT ENV</span>
          </div>
        </nav>
      )}
      
      {isCustomerRoute && (
        <button 
          onClick={() => navigate('/')}
          className="exit-demo-btn"
          style={{
            position: 'absolute',
            top: '1rem',
            left: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            background: 'white',
            border: '1px solid var(--color-border)',
            padding: '0.5rem 1rem',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.85rem',
            fontWeight: '600',
            cursor: 'pointer',
            boxShadow: 'var(--shadow-sm)',
            color: 'var(--color-text)'
          }}
        >
          <ArrowLeft size={16} /> Exit Test Mode
        </button>
      )}

      <main className={isCustomerRoute ? "customer-main" : "app-main"}>
        <Outlet />
      </main>
    </div>
  );
}
