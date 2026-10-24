import psycopg2
import io
import time
import sys

LOCAL_URI = "postgresql://postgres:postgres@localhost:5432/ner_logistics"
SUPA_HOST = "aws-0-ap-south-1.pooler.supabase.com"
SUPA_USER = "postgres.zobivbtkiqksvxfgepyg"
SUPA_PASS = "NerLogistics2026!"
SUPA_DB = "postgres"

def get_supa():
    return psycopg2.connect(
        dbname=SUPA_DB,
        user=SUPA_USER,
        password=SUPA_PASS,
        host=SUPA_HOST,
        port=5432,
        connect_timeout=20
    )

def main():
    print("Connecting to databases...", flush=True)
    local_conn = psycopg2.connect(LOCAL_URI)
    supa_conn = get_supa()

    with supa_conn.cursor() as sup_cur:
        # Check current max id in Supabase
        sup_cur.execute("SELECT coalesce(max(id), 0) FROM roads;")
        current_max = sup_cur.fetchone()[0]
        print(f"Current max road ID in Supabase: {current_max}", flush=True)

    chunk_size = 5000
    start_id = current_max + 1
    total_max = 226949

    print(f"Starting chunked stream from ID {start_id} to {total_max} (chunk size: {chunk_size})...", flush=True)

    while start_id <= total_max:
        end_id = min(start_id + chunk_size, total_max + 1)
        buf = io.BytesIO()

        # Copy chunk from local
        with local_conn.cursor() as loc_cur:
            query = f"COPY (SELECT * FROM roads WHERE id >= {start_id} AND id < {end_id} ORDER BY id) TO STDOUT (FORMAT binary)"
            loc_cur.copy_expert(query, buf)
        
        row_count = end_id - start_id
        buf_size = buf.tell()
        buf.seek(0)

        # Upload to Supabase with automatic retry
        success = False
        for attempt in range(5):
            try:
                if supa_conn.closed:
                    supa_conn = get_supa()
                with supa_conn.cursor() as sup_cur:
                    sup_cur.copy_expert("COPY roads FROM STDIN (FORMAT binary)", buf)
                supa_conn.commit()
                pct = int((end_id - 1) / total_max * 100)
                print(f"Uploaded roads {start_id}..{end_id - 1} ({pct}% complete, {buf_size//1024} KB)", flush=True)
                success = True
                break
            except Exception as e:
                print(f"  Retry {attempt+1} for {start_id}..{end_id}: {e}", flush=True)
                time.sleep(2)
                try:
                    supa_conn.rollback()
                except Exception:
                    pass
                supa_conn = get_supa()
                buf.seek(0)

        if not success:
            print(f"Failed to upload chunk starting at {start_id} after 5 attempts. Exiting.", flush=True)
            sys.exit(1)

        start_id = end_id

    # Verify final count
    with supa_conn.cursor() as sup_cur:
        sup_cur.execute("SELECT count(*) FROM roads;")
        final_count = sup_cur.fetchone()[0]
        print(f"\nSUCCESS! All {final_count} roads are safely in Supabase!", flush=True)

    local_conn.close()
    supa_conn.close()

if __name__ == "__main__":
    main()
