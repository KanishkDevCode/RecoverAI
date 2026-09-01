import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from sqlalchemy import create_engine, text

# Connect to the default 'postgres' database
DATABASE_URL = "postgresql://postgres:recoverai@localhost:5432/postgres"
engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")

try:
    with engine.connect() as conn:
        # Kill all connections to recoverai
        conn.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'recoverai';"))
        
        # Drop and recreate
        conn.execute(text("DROP DATABASE IF EXISTS recoverai;"))
        conn.execute(text("CREATE DATABASE recoverai;"))
    print("Successfully dropped and recreated database.")
except Exception as e:
    print(f"Error: {e}")
