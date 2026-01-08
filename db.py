from dotenv import load_dotenv
import os
from mysql.connector import pooling

# Load .env variables
load_dotenv()
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_DATABASE")
}

# Init db
pool = pooling.MySQLConnectionPool(pool_name="pool", pool_size=5, **DB_CONFIG)
def get_conn():
    return pool.get_connection()

# DB-Helper
def db_read(sql, params=None, single=False):
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())

        if single:
            # liefert EIN Dict oder None
            row = cur.fetchone()
            print("db_read(single=True) ->", row)   # DEBUG
            return row
        else:
            # liefert Liste von Dicts (evtl. [])
            rows = cur.fetchall()
            print("db_read(single=False) ->", rows)  # DEBUG
            return rows

    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()


def db_write(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        print("db_write OK:", sql, params)  # DEBUG
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()
        # -------------------------
# Ball Bingo: Queries/Helper
# -------------------------

def get_random_players(limit=16):
    sql = """
        SELECT id, name, nationality, position
        FROM players
        ORDER BY RAND()
        LIMIT %s
    """
    return db_read(sql, (limit,))

def get_player_by_id(player_id):
    sql = """
        SELECT id, name, nationality, position
        FROM players
        WHERE id = %s
    """
    return db_read(sql, (player_id,), single=True)

def get_player_facts(player_id):
    facts = []

    row = db_read(
        "SELECT nationality, position FROM players WHERE id=%s",
        (player_id,),
        single=True
    )

    if row:
        if row.get("nationality"):
            facts.append(f"Nationality: {row['nationality']}")
        if row.get("position"):
            facts.append(f"Position: {row['position']}")

    # OPTIONAL: nur wenn ihr diese Tabellen habt!
    # clubs
    club_rows = db_read("""
        SELECT c.name AS club_name
        FROM player_clubs pc
        JOIN clubs c ON c.id = pc.club_id
        WHERE pc.player_id = %s
        LIMIT 5
    """, (player_id,))
    for r in club_rows:
        facts.append(f"Played for: {r['club_name']}")

    # titles
    title_rows = db_read("""
        SELECT t.name AS title_name
        FROM player_titles pt
        JOIN titles t ON t.id = pt.title_id
        WHERE pt.player_id = %s
        LIMIT 5
    """, (player_id,))
    for r in title_rows:
        facts.append(f"Won: {r['title_name']}")

    return facts
