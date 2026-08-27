import os
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_db():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../recoverai.db"))
    if not os.path.exists(db_path):
        logger.info("No recoverai.db found. No migration needed.")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if version exists in recovery_attempts
        cursor.execute("PRAGMA table_info(recovery_attempts)")
        columns = [col[1] for col in cursor.fetchall()]
        if "version" not in columns:
            logger.info("Adding version column to recovery_attempts...")
            cursor.execute("ALTER TABLE recovery_attempts ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
            
        # Check if recovery_status exists in transactions
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in cursor.fetchall()]
        if "recovery_status" not in columns:
            logger.info("Adding recovery_status column to transactions...")
            cursor.execute("ALTER TABLE transactions ADD COLUMN recovery_status VARCHAR DEFAULT 'NOT_STARTED'")
            
            # Migrate existing "recovered" statuses to recovery_status="SUCCEEDED"
            logger.info("Migrating recovered status...")
            cursor.execute("UPDATE transactions SET recovery_status = 'SUCCEEDED', status = 'failed' WHERE status = 'recovered'")
            
            # Since amount was Float, we'll convert it to minor units (Integer paise/cents)
            logger.info("Converting transaction amounts to minor units (integer)...")
            cursor.execute("UPDATE transactions SET amount = CAST(ROUND(amount * 100) AS INTEGER)")
            
            # Check if refund_amount exists in transactions (might be missing in old DBs)
            if "refund_amount" not in columns:
                logger.info("Adding refund_amount column to transactions...")
                cursor.execute("ALTER TABLE transactions ADD COLUMN refund_amount INTEGER")
            else:
                logger.info("Converting refund amounts to minor units (integer)...")
                cursor.execute("UPDATE transactions SET refund_amount = CAST(ROUND(refund_amount * 100) AS INTEGER) WHERE refund_amount IS NOT NULL")
                
            if "refund_status" not in columns:
                logger.info("Adding refund_status column to transactions...")
                cursor.execute("ALTER TABLE transactions ADD COLUMN refund_status VARCHAR")
            
        conn.commit()
        logger.info("Migration successful!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_db()
