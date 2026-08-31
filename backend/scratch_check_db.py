import psycopg2
conn = psycopg2.connect('postgresql://postgres:recoverai@localhost:5432/recoverai')
cur = conn.cursor()
cur.execute("SELECT id FROM transactions LIMIT 10;")
print(cur.fetchall())
