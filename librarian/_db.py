import os
import sys
import time

import pysqlite3 as sqlite3


def _load_extension_path() -> str:
    base = os.environ.get("RESOURCEPATH", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ext = "sqlite_vec.dylib" if sys.platform == "darwin" else "sqlite_vec.dll"
    return os.path.join(base, ext)


def open_db(path: str):
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    ext_path = _load_extension_path()
    if os.path.exists(ext_path):
        conn.load_extension(ext_path)
    else:
        # Fall back: try the sqlite_vec Python package if available
        try:
            import sqlite_vec
            sqlite_vec.load(conn)
        except ImportError:
            pass
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def execute_with_retry(db_conn, query: str, params=(), max_retries: int = 3):
    delays = [0.2, 0.4, 0.6]
    for attempt in range(max_retries):
        try:
            with db_conn:
                return db_conn.execute(query, params).fetchall()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(delays[attempt])
                continue
            raise
