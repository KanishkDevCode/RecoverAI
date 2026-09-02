const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
const API_KEY = 'test_secret_key_123';

const headers = {
  'Content-Type': 'application/json',
  'X-API-Key': API_KEY,
};

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, { headers, ...options });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

export function createPayment(transaction) {
  return request('/payments', {
    method: 'POST',
    body: JSON.stringify(transaction),
  });
}

export function getPaymentDetails(id) {
  return request(`/payments/${id}`);
}

export function initiateRefund(id) {
  return request(`/payments/${id}/refund`, { method: 'POST' });
}

export function simulateManualRecovery(id) {
  return request(`/recovery/manual/${id}`, { method: 'POST' });
}

export function getPayments(limit = 50) {
  return request(`/transactions?limit=${limit}`);
}

export function getAuditTrail(transactionId) {
  return request(`/audit/${transactionId}`);
}

export function getDashboardMetrics() {
  return request('/dashboard/metrics');
}

export function getCustomers() {
  return request('/customers');
}

export function getHealthCheck() {
  return fetch(`${API_BASE}/health/ready`).then(async (r) => {
    // Treat 503 as a valid response format for health checks
    if (!r.ok && r.status !== 503) {
      throw new Error('Health check failed');
    }
    return r.json();
  });
}
