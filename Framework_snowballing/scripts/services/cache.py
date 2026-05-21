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

    title_normalized = title.lower() if title else None
    mode = data.get("mode") if isinstance(data, dict) else None

    # verifica DOI + modo primeiro
    if doi:
        cursor.execute(
            "SELECT id FROM articles WHERE doi = ? AND json_extract(data, '$.mode') = ?",
            (doi, mode)
        )

        if cursor.fetchone():
            print("[CACHE SKIP - DOI JÁ EXISTE]", file=sys.stderr)
            conn.close()
            return

    # verifica título + modo depois
    if title_normalized:
        cursor.execute(
            "SELECT id FROM articles WHERE title = ? AND json_extract(data, '$.mode') = ?",
            (title_normalized, mode)
        )

        if cursor.fetchone():
            print("[CACHE SKIP - TITLE JÁ EXISTE]", file=sys.stderr)
            conn.close()
            return

    # salva apenas se não existir
    cursor.execute("""
        INSERT INTO articles (doi, title, data)
        VALUES (?, ?, ?)
    """, (
        doi,
        title_normalized,
        json.dumps(data)
    ))

    conn.commit()
    conn.close()

    print("[CACHE SAVE]", file=sys.stderr)


def get_cached(doi=None, title=None, mode=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # busca por DOI primeiro
    if doi:
        if mode:
            cursor.execute(
                "SELECT data FROM articles WHERE doi = ? AND json_extract(data, '$.mode') = ?",
                (doi, mode)
            )
        else:
            cursor.execute(
                "SELECT data FROM articles WHERE doi = ?",
                (doi,)
            )

        row = cursor.fetchone()

        if row:
            conn.close()
            print("[CACHE HIT - DOI]", file=sys.stderr)
            return json.loads(row[0])

    # depois busca por título
    if title:
        title_normalized = title.lower()

        if mode:
            cursor.execute(
                "SELECT data FROM articles WHERE title = ? AND json_extract(data, '$.mode') = ?",
                (title_normalized, mode)
            )
        else:
            cursor.execute(
                "SELECT data FROM articles WHERE title = ?",
                (title_normalized,)
            )

        row = cursor.fetchone()

        if row:
            conn.close()
            print("[CACHE HIT - TITLE]", file=sys.stderr)
            return json.loads(row[0])

    conn.close()

    print("[CACHE MISS]", file=sys.stderr)
    return None