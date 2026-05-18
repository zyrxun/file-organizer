import hashlib
import os
import shutil
import sqlite3

import config


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            checksum TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING_DELETE'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_moves_status ON moves(status)")
    conn.commit()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.ORGANIZER_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    init_db(conn)
    return conn


def recover_pending(conn: sqlite3.Connection) -> list[str]:
    warnings = []
    rows = conn.execute(
        "SELECT id, src, dst, checksum FROM moves WHERE status='PENDING_DELETE'"
    ).fetchall()
    for row_id, src, dst, checksum in rows:
        if os.path.exists(dst) and _sha256(dst) == checksum:
            try:
                os.unlink(src)
                conn.execute("UPDATE moves SET status='COMPLETED' WHERE id=?", (row_id,))
                conn.commit()
            except OSError:
                conn.execute(
                    "UPDATE moves SET status='DELETE_FAILED_MANUAL_ACTION_REQUIRED' WHERE id=?",
                    (row_id,),
                )
                conn.commit()
                warnings.append(f"Could not delete original after move: {src}")
        else:
            warnings.append(f"Destination missing or checksum mismatch, skipping: {dst}")
    return warnings


def move_files(
    assignments: dict[str, str],
    root_src: str,
    root_dst: str,
    session_id: str,
    conn: sqlite3.Connection,
    on_progress=None,
) -> list[str]:
    errors = []
    total = len(assignments)
    for i, (filename, folder) in enumerate(assignments.items()):
        src = _find_file(filename, root_src)
        if src is None:
            errors.append(f"Source not found: {filename}")
            continue
        dst_dir = os.path.join(root_dst, folder)
        os.makedirs(dst_dir, exist_ok=True)
        dst = _collision_free_path(dst_dir, filename)
        try:
            _move_atomic(src, dst, conn, session_id)
        except Exception as e:
            errors.append(f"Failed to move {filename}: {e}")
        if on_progress:
            on_progress(i + 1, total)
    return errors


def undo_last(session_id: str, conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT id, src, dst FROM moves WHERE session_id=? AND status='COMPLETED'",
        (session_id,),
    ).fetchall()
    errors = []
    for row_id, src, dst in rows:
        try:
            if os.path.exists(dst):
                os.makedirs(os.path.dirname(src), exist_ok=True)
                os.rename(dst, src)
                conn.execute("DELETE FROM moves WHERE id=?", (row_id,))
                conn.commit()
        except OSError as e:
            errors.append(f"Undo failed for {dst}: {e}")
    return errors


def _move_atomic(src: str, dst: str, conn: sqlite3.Connection, session_id: str) -> None:
    if _same_filesystem(src, dst):
        conn.execute(
            "INSERT INTO moves (session_id, src, dst, status) VALUES (?, ?, ?, 'COMPLETED')",
            (session_id, src, dst),
        )
        conn.commit()
        os.rename(src, dst)
    else:
        checksum = _sha256(src)
        cur = conn.execute(
            "INSERT INTO moves (session_id, src, dst, checksum, status) VALUES (?, ?, ?, ?, 'PENDING_DELETE')",
            (session_id, src, dst, checksum),
        )
        row_id = cur.lastrowid
        conn.commit()
        shutil.copy2(src, dst)
        if _sha256(dst) != checksum:
            os.unlink(dst)
            raise RuntimeError(f"Checksum mismatch after copy: {src}")
        conn.execute("UPDATE moves SET status='COMPLETED' WHERE id=?", (row_id,))
        conn.commit()
        try:
            os.unlink(src)
        except OSError:
            conn.execute(
                "UPDATE moves SET status='DELETE_FAILED_MANUAL_ACTION_REQUIRED' WHERE id=?",
                (row_id,),
            )
            conn.commit()


def _collision_free_path(directory: str, filename: str) -> str:
    name, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{name} ({counter}){ext}")
        counter += 1
    return candidate


def _find_file(filename: str, root: str) -> str | None:
    for dirpath, _, filenames in os.walk(root):
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None


def _same_filesystem(path_a: str, path_b: str) -> bool:
    try:
        return os.stat(path_a).st_dev == os.stat(os.path.dirname(path_b)).st_dev
    except OSError:
        return False


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
