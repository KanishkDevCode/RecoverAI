import React from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { CreditCard, LayoutDashboard, Settings, Shield, Activity } from 'lucide-react';

export default function AppLayout() {
  const location = useLocation();
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
            <NavLink to="/checkout" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <CreditCard size={16} /> Checkout (Demo)
            </NavLink>
            <NavLink to="/payments" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <Activity size={16} /> Payments
            </NavLink>
            <NavLink to="/recovery" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <LayoutDashboard size={16} /> Recovery
            </NavLink>
            <NavLink to="/settings" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <Settings size={16} /> Settings
            </NavLink>
          </div>
          <div className="nav-env">
            <span className="env-badge">TEST MODE</span>
          </div>
        </nav>
      )}
      <main className={isCustomerRoute ? "customer-main" : "app-main"}>
        <Outlet />
      </main>
    </div>
  );
}
