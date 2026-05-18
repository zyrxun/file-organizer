import os
import sys
import time

import numpy as np

import config
from librarian._db import open_db, execute_with_retry
from librarian._embedder import embed


def build_index(root_path: str, on_progress=None) -> None:
    db = open_db(config.LIBRARIAN_DB_PATH)
    _ensure_schema(db)
    _sync(db, root_path, on_progress)
    db.close()


def _sync(db, root_path: str, on_progress=None) -> None:
    existing = {
        row[0]: row[1]
        for row in db.execute("SELECT full_path, mtime FROM files_metadata").fetchall()
    }
    on_disk = {}
    for dirpath, _, filenames in os.walk(root_path):
        for name in filenames:
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            try:
                on_disk[full] = os.path.getmtime(full)
            except OSError:
                pass

    dead = set(existing) - set(on_disk)
    for path in dead:
        row = db.execute("SELECT rowid FROM files_metadata WHERE full_path=?", (path,)).fetchone()
        if row:
            execute_with_retry(db, "DELETE FROM vec_files WHERE rowid=?", (row[0],))
            execute_with_retry(db, "DELETE FROM files_metadata WHERE rowid=?", (row[0],))

    to_index = [p for p, mt in on_disk.items() if existing.get(p) != mt]
    total = len(to_index)
    for i, path in enumerate(to_index):
        _index_file(db, path, on_disk[path])
        if on_progress:
            on_progress(i + 1, total)


def _index_file(db, full_path: str, mtime: float) -> None:
    filename = os.path.basename(full_path)
    text = filename
    vec = embed(text)

    existing = db.execute(
        "SELECT rowid FROM files_metadata WHERE full_path=?", (full_path,)
    ).fetchone()

    if existing:
        row_id = existing[0]
        execute_with_retry(
            db,
            "UPDATE files_metadata SET filename=?, mtime=? WHERE rowid=?",
            (filename, mtime, row_id),
        )
        execute_with_retry(
            db,
            "INSERT OR REPLACE INTO vec_files (rowid, embedding) VALUES (?, ?)",
            (row_id, memoryview(vec.tobytes())),
        )
    else:
        cur = db.execute(
            "INSERT INTO files_metadata (filename, full_path, mtime) VALUES (?, ?, ?)",
            (filename, full_path, mtime),
        )
        row_id = cur.lastrowid
        db.commit()
        execute_with_retry(
            db,
            "INSERT INTO vec_files (rowid, embedding) VALUES (?, ?)",
            (row_id, memoryview(vec.tobytes())),
        )
    db.commit()


def _ensure_schema(db) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS files_metadata (
            rowid INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            full_path TEXT NOT NULL UNIQUE,
            mtime REAL
        )
    """)
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_files USING vec0(
            embedding float[384]
        )
    """)
    db.commit()


class WatchdogWorker:
    def __init__(self, root_path: str):
        self.root_path = root_path
        self._db = open_db(config.LIBRARIAN_DB_PATH)
        _ensure_schema(self._db)

    def on_created(self, path: str) -> None:
        if os.path.isfile(path) and not os.path.basename(path).startswith("."):
            try:
                _index_file(self._db, path, os.path.getmtime(path))
            except Exception:
                pass

    def on_modified(self, path: str) -> None:
        self.on_created(path)

    def on_deleted(self, path: str) -> None:
        row = self._db.execute(
            "SELECT rowid FROM files_metadata WHERE full_path=?", (path,)
        ).fetchone()
        if row:
            execute_with_retry(self._db, "DELETE FROM vec_files WHERE rowid=?", (row[0],))
            execute_with_retry(
                self._db, "DELETE FROM files_metadata WHERE rowid=?", (row[0],)
            )

    def on_moved(self, src: str, dst: str) -> None:
        self.on_deleted(src)
        self.on_created(dst)

    def close(self) -> None:
        self._db.close()
