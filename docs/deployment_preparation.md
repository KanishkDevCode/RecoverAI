# Phase 6.2-A: Deployment Preparation

## 1. Backend Build Command
When deploying to Render (or similar PaaS), use the following build command:
```bash
pip install -r requirements.txt
```

## 2. Backend Start Command
To start the FastAPI web service, use `uvicorn` directly (which binds to the environment's assigned `$PORT`):
```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## 3. Celery Worker Command
For the background worker process (Render Background Worker), use:
```bash
celery -A app.worker.celery_app worker -Q celery,high_priority,reconciliation --loglevel=info
```

## 4. Frontend Build Command
When deploying the React frontend to Vercel or Netlify, the standard Vite build command applies:
```bash
npm install && npm run build
```

## 5. Required Environment Variables

### Backend (Render)
- `ENVIRONMENT=production`
- `DATABASE_URL=postgresql://...` (Provided by Render PostgreSQL)
- `CELERY_BROKER_URL=redis://...` (Provided by Render Redis)
- `CELERY_RESULT_BACKEND=redis://...`
- `PAYMENT_PROVIDER=razorpay`
- `RAZORPAY_KEY_ID=...`
- `RAZORPAY_KEY_SECRET=...`
- `RAZORPAY_WEBHOOK_SECRET=...` (A strong custom string)
- `LLM_PROVIDER=groq`
- `GROQ_API_KEY=...`
- `CORS_ALLOWED_ORIGINS=https://your-frontend-url.vercel.app`
- `OBSERVABILITY_API_KEY=...`

### Frontend (Vercel)
- `VITE_API_URL=https://your-backend-url.onrender.com/api/v1`
- `VITE_WS_URL=wss://your-backend-url.onrender.com/api/v1`

## 6. Deployment Order
To prevent race conditions, deploy in this strict sequence:
1. **Database:** Deploy PostgreSQL database on Render.
2. **Redis:** Deploy Redis instance on Render.
3. **Backend API:** Deploy the FastAPI web service (this runs migrations).
4. **Celery Worker:** Deploy the Background Worker.
5. **Frontend:** Deploy React app to Vercel (using the backend URL).
6. **CORS:** Update the backend's `CORS_ALLOWED_ORIGINS` with the final frontend URL.
7. **Razorpay Dashboard:** Add the backend URL to the Webhooks page.
