import sys
import os
import sqlite3

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.logging import logger

def migrate_db(db_path: str):
    logger.info(f"Migrating database at: {db_path}")
    
    if not os.path.exists(db_path):
        logger.error("Database not found. Exiting.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add columns to idempotency_records
    columns_to_add = [
        ("request_hash", "TEXT", "idempotency_records"),
        ("response_body", "TEXT", "idempotency_records"),
        ("status_code", "INTEGER", "idempotency_records")
    ]

    for col_name, col_type, table in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            logger.info(f"Added column {col_name} to {table}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info(f"Column {col_name} already exists. Skipping.")
            else:
                logger.error(f"Error adding {col_name}: {e}")

    conn.commit()
    conn.close()
    logger.info("Batch 2 Migration complete!")

if __name__ == "__main__":
    db_path = os.getenv("DATABASE_URL", "sqlite:///./recoverai.db").replace("sqlite:///", "")
    migrate_db(db_path)
