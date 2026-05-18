import os

import numpy as np

import config
from librarian._db import open_db
from librarian._embedder import embed


def search(query: str, root_path: str, top_k: int = 10) -> list[dict]:
    db = open_db(config.LIBRARIAN_DB_PATH)
    try:
        results = _vector_search(db, query, top_k)
        if not results:
            results = _like_search(db, query, top_k)
        return [r for r in results if os.path.exists(r["path"])]
    finally:
        db.close()


def _vector_search(db, query: str, top_k: int) -> list[dict]:
    try:
        vec = embed(query)
        query_blob = memoryview(vec.tobytes())
        rows = db.execute("""
            SELECT m.filename, m.full_path, v.distance
            FROM vec_files v
            JOIN files_metadata m ON v.rowid = m.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
        """, (query_blob, top_k)).fetchall()
        return [{"filename": r[0], "path": r[1], "score": 1.0 / (1.0 + r[2])} for r in rows]
    except Exception:
        return []


def _like_search(db, query: str, top_k: int) -> list[dict]:
    pattern = f"%{query}%"
    rows = db.execute(
        "SELECT filename, full_path FROM files_metadata WHERE filename LIKE ? LIMIT ?",
        (pattern, top_k),
    ).fetchall()
    return [{"filename": r[0], "path": r[1], "score": 0.5} for r in rows]
