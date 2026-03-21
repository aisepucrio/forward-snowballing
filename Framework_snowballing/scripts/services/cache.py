import sqlite3
from pathlib import Path
import json
import sys
# caminho FIXO do banco
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

DB_PATH = CACHE_DIR / "snowballing_cache.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT,
            title TEXT,
            data TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_to_cache(doi, title, data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO articles (doi, title, data)
        VALUES (?, ?, ?)
    """, (doi, title.lower() if title else None, json.dumps(data)))

    conn.commit()
    conn.close()


def get_cached(doi=None, title=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # busca por DOI primeiro
    if doi:
        cursor.execute("SELECT data FROM articles WHERE doi = ?", (doi,))
        row = cursor.fetchone()
        if row:
            conn.close()
            print("[CACHE HIT - DOI]", file=sys.stderr)
            return json.loads(row[0])

    # depois por título
    if title:
        cursor.execute("SELECT data FROM articles WHERE title = ?", (title.lower(),))
        row = cursor.fetchone()
        if row:
            conn.close()
            print("[CACHE HIT - TITLE]", file=sys.stderr)
            return json.loads(row[0])

    conn.close()
    return None