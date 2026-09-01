import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        for _ in range(3):
            conn.execute(text("SELECT pg_cancel_backend(pid), pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'recoverai' AND pid != pg_backend_pid();"))
            conn.commit()
            time.sleep(1)
            
        res = conn.execute(text("SELECT pid, query, state FROM pg_stat_activity WHERE datname = 'recoverai' AND pid != pg_backend_pid();"))
        rows = res.fetchall()
        print("Active Connections:", rows)
except Exception as e:
    print(e)
