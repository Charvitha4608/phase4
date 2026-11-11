"""Database access: PyMySQL connections and small helpers. No ORM."""
import os
from contextlib import contextmanager

import pymysql


def get_db_config():
    """Connection settings, taken from environment variables."""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASS", ""),
        "database": os.environ.get("DB_NAME", "wife_carrying_db"),
        "charset": "utf8mb4",
    }


def get_connection():
    return pymysql.connect(
        **get_db_config(),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def fetch_all(sql, params=()):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def fetch_one(sql, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


@contextmanager
def transaction():
    """Yield a cursor. Commits at the end, rolls everything back on any error."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
