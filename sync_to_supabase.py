import psycopg2
from psycopg2.extras import execute_batch
import time

LOCAL_URI = "postgresql://postgres:postgres@localhost:5432/ner_logistics"
SUPA_HOST = "aws-0-ap-south-1.pooler.supabase.com"
SUPA_USER = "postgres.zobivbtkiqksvxfgepyg"
SUPA_PASS = "NerLogistics2026!"
SUPA_DB = "postgres"

def get_supa_conn():
    return psycopg2.connect(
        dbname=SUPA_DB,
        user=SUPA_USER,
        password=SUPA_PASS,
        host=SUPA_HOST,
        port=5432,
        connect_timeout=15
    )

def sync_table(table_name, pkey="id", batch_size=2000):
    print(f"\n--- Syncing table: {table_name} ---")
    local_conn = psycopg2.connect(LOCAL_URI)
    local_cur = local_conn.cursor()
    
    # Get column names
    local_cur.execute(f"SELECT * FROM {table_name} LIMIT 0;")
    colnames = [desc[0] for desc in local_cur.description]
    cols_str = ", ".join([f'"{c}"' for c in colnames])
    placeholders = ", ".join(["%s"] * len(colnames))
    
    # Count local rows
    local_cur.execute(f"SELECT count(*) FROM {table_name};")
    total_rows = local_cur.fetchone()[0]
    print(f"Total rows in local {table_name}: {total_rows}")
    
    # Check supa rows
    supa_conn = get_supa_conn()
    supa_cur = supa_conn.cursor()
    try:
        supa_cur.execute(f"SELECT count(*) FROM {table_name};")
        supa_count = supa_cur.fetchone()[0]
    except Exception:
        supa_conn.rollback()
        supa_count = 0
    
    if supa_count >= total_rows and total_rows > 0:
        print(f"Table {table_name} already fully populated ({supa_count} rows). Skipping.")
        local_conn.close()
        supa_conn.close()
        return

    # Stream from local
    local_cur.execute(f"SELECT {cols_str} FROM {table_name} ORDER BY {pkey};")
    
    insert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT ({pkey}) DO NOTHING;"
    
    inserted = 0
    batch = []
    while True:
        rows = local_cur.fetchmany(batch_size)
        if not rows:
            break
        
        # Insert into Supabase with retry
        for attempt in range(5):
            try:
                if supa_conn.closed:
                    supa_conn = get_supa_conn()
                    supa_cur = supa_conn.cursor()
                execute_batch(supa_cur, insert_sql, rows, page_size=1000)
                supa_conn.commit()
                inserted += len(rows)
                print(f"  {table_name}: {inserted}/{total_rows} ({int(inserted/total_rows*100)}%)")
                break
            except Exception as e:
                print(f"  Retry {attempt+1} on {table_name} due to: {e}")
                time.sleep(2)
                try:
                    supa_conn.rollback()
                except Exception:
                    pass
                supa_conn = get_supa_conn()
                supa_cur = supa_conn.cursor()
    
    local_conn.close()
    supa_conn.close()
    print(f"Done syncing {table_name}!")

if __name__ == "__main__":
    tables = [
        ("states", "id"),
        ("districts", "id"),
        ("users", "id"),
        ("incidents", "id"),
        ("routes", "id"),
        ("route_roads", "id"),
        ("vehicles", "id"),
        ("alerts", "id"),
        ("roads", "id"),
    ]
    for tbl, pk in tables:
        sync_table(tbl, pk, batch_size=5000 if tbl == "roads" else 1000)
    print("\nALL TABLES SYNCED SUCCESSFULLY TO SUPABASE!")
