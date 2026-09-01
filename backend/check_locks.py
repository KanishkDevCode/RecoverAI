import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT pid, query, state FROM pg_stat_activity WHERE datname = 'recoverai' AND pid != pg_backend_pid();"))
        rows = res.fetchall()
        print("Active Connections:", rows)
        
        res = conn.execute(text("SELECT relation::regclass, mode, granted FROM pg_locks WHERE NOT granted;"))
        rows = res.fetchall()
        print("Un-granted Locks:", rows)
except Exception as e:
    print(e)
