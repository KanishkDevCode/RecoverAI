from fastapi import APIRouter
from app.api import payments, recovery, refunds, transactions, dashboard, customers, audit, websocket, system, webhooks, health, metrics

router = APIRouter(prefix="/api/v1")

router.include_router(health.router, prefix="/health")
router.include_router(metrics.router, prefix="/metrics")

router.include_router(system.router, tags=["System"])
router.include_router(payments.router, tags=["Payments"])
router.include_router(recovery.router, tags=["Recovery"])
router.include_router(refunds.router, tags=["Refunds"])
router.include_router(transactions.router, tags=["Transactions"])
router.include_router(dashboard.router, tags=["Dashboard"])
router.include_router(customers.router, tags=["Customers"])
router.include_router(audit.router, tags=["Audit"])
router.include_router(websocket.router, tags=["Websocket"])
router.include_router(webhooks.router, tags=["Webhooks"])
