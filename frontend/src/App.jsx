import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { PaymentProvider } from './context/PaymentContext';
import AppLayout from './components/layout/AppLayout';
import Checkout from './pages/Checkout';
import PaymentProcessing from './pages/PaymentProcessing';
import PaymentSuccess from './pages/PaymentSuccess';
import PaymentFailed from './pages/PaymentFailed';
import Payments from './pages/Payments';
import PaymentDetails from './pages/PaymentDetails';
import RecoveryConsole from './pages/RecoveryConsole';
import Settings from './pages/Settings';
import Overview from './pages/Overview';
import Customers from './pages/Customers';
import './index.css';

export default function App() {
  return (
    <BrowserRouter>
      <PaymentProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Overview />} />
            <Route path="/checkout" element={<Checkout />} />
            <Route path="/payment-processing" element={<PaymentProcessing />} />
            <Route path="/payment-success" element={<PaymentSuccess />} />
            <Route path="/payment-failed" element={<PaymentFailed />} />
            <Route path="/payments" element={<Payments />} />
            <Route path="/payments/:transactionId" element={<PaymentDetails />} />
            <Route path="/recovery" element={<RecoveryConsole />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </PaymentProvider>
    </BrowserRouter>
  );
}
