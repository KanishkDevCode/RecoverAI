import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure paths are correct when running from scripts directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.db_models import Base, Transaction, RecoveryAttempt, AuditLog, IdempotencyRecord, WebhookEvent
from app.core.logging import logger

def migrate_data():
    sqlite_url = os.getenv("SQLITE_URL", "sqlite:///./recoverai.db")
    postgres_url = os.getenv("POSTGRES_URL")

    if not postgres_url:
        logger.error("POSTGRES_URL environment variable is required.")
        sys.exit(1)

    logger.info(f"Connecting to SQLite: {sqlite_url}")
    sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    SqliteSession = sessionmaker(bind=sqlite_engine)
    
    logger.info(f"Connecting to PostgreSQL: {postgres_url}")
    pg_engine = create_engine(postgres_url)
    PgSession = sessionmaker(bind=pg_engine)

    # Ensure PostgreSQL schema is up to date (this assumes Alembic has run)
    
    with SqliteSession() as sqlite_db, PgSession() as pg_db:
        try:
            logger.info("Beginning migration in a single transaction...")
            
            # 1. Transactions
            transactions = sqlite_db.query(Transaction).all()
            for t in transactions:
                pg_db.merge(t)
            logger.info(f"Migrated {len(transactions)} Transactions")

            # 2. Recovery Attempts
            attempts = sqlite_db.query(RecoveryAttempt).all()
            for a in attempts:
                pg_db.merge(a)
            logger.info(f"Migrated {len(attempts)} Recovery Attempts")
            
            # 3. Idempotency Records
            idempotency_records = sqlite_db.query(IdempotencyRecord).all()
            for r in idempotency_records:
                pg_db.merge(r)
            logger.info(f"Migrated {len(idempotency_records)} Idempotency Records")
            
            # 4. Webhook Events
            webhook_events = sqlite_db.query(WebhookEvent).all()
            for w in webhook_events:
                pg_db.merge(w)
            logger.info(f"Migrated {len(webhook_events)} Webhook Events")

            # 5. Audit Logs
            audit_logs = sqlite_db.query(AuditLog).all()
            for al in audit_logs:
                # Merge explicitly doesn't always handle autoincrement primary keys perfectly if not specified, 
                # but sqlite to postgres merge should copy the ID directly.
                pg_db.merge(al)
            logger.info(f"Migrated {len(audit_logs)} Audit Logs")

            pg_db.commit()
            logger.info("Data migration committed successfully.")

            # Validation
            logger.info("--- Running Post-Migration Validation ---")
            
            # Check row counts
            for model, name in [
                (Transaction, "Transactions"),
                (RecoveryAttempt, "Recovery Attempts"),
                (IdempotencyRecord, "Idempotency Records"),
                (WebhookEvent, "Webhook Events"),
                (AuditLog, "Audit Logs")
            ]:
                sqlite_count = sqlite_db.query(model).count()
                pg_count = pg_db.query(model).count()
                logger.info(f"{name} Count: SQLite={sqlite_count}, PostgreSQL={pg_count}")
                assert sqlite_count == pg_count, f"Count mismatch for {name}"

            # Check monetary sums
            from sqlalchemy.sql import func
            
            sqlite_amt = sqlite_db.query(func.sum(Transaction.amount)).scalar() or 0
            pg_amt = pg_db.query(func.sum(Transaction.amount)).scalar() or 0
            logger.info(f"Total Amount (Minor Units): SQLite={sqlite_amt}, PostgreSQL={pg_amt}")
            assert sqlite_amt == pg_amt, "Total Amount mismatch"
            
            sqlite_refund = sqlite_db.query(func.sum(Transaction.refund_amount)).scalar() or 0
            pg_refund = pg_db.query(func.sum(Transaction.refund_amount)).scalar() or 0
            logger.info(f"Total Refund Amount (Minor Units): SQLite={sqlite_refund}, PostgreSQL={pg_refund}")
            assert sqlite_refund == pg_refund, "Total Refund Amount mismatch"

            logger.info("SUCCESS: Migration and validation completed flawlessly.")

        except Exception as e:
            pg_db.rollback()
            logger.error(f"Migration failed and rolled back. Error: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    migrate_data()
