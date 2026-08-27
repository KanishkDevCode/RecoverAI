import sqlite3
import os
import sys

def run_migration():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'recoverai.db')
    print(f"Migrating database at: {db_path}")

    if not os.path.exists(db_path):
        print("Database not found. Exiting.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add columns to idempotency_records
    columns_to_add = [
        ("request_hash", "TEXT"),
        ("response_body", "TEXT"),
        ("status_code", "INTEGER")
    ]

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE idempotency_records ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name} to idempotency_records")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column {col_name} already exists. Skipping.")
            else:
                print(f"Error adding {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Batch 2 Migration complete!")

if __name__ == "__main__":
    run_migration()
