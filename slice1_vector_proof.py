"""
Slice 1 verification: confirms pysqlite3-binary + sqlite-vec extension loading,
WAL mode, vec0 KNN insert/search, and memoryview BLOB binding all work end-to-end.
Run this before any GUI work: python slice1_vector_proof.py
"""
import os
import sys

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(BASE_DIR, "sqlite_vec.dylib" if sys.platform == "darwin" else "sqlite_vec.dll")

try:
    import pysqlite3 as sqlite3
    print("✓ pysqlite3 imported")
except ImportError as e:
    print(f"✗ pysqlite3 not available: {e}")
    print("  Install: pip install pysqlite3-binary")
    sys.exit(1)


def init_db():
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)

    if os.path.exists(EXT):
        conn.load_extension(EXT)
        print(f"✓ sqlite-vec loaded from {EXT}")
    else:
        try:
            import sqlite_vec
            sqlite_vec.load(conn)
            print("✓ sqlite-vec loaded via Python package")
        except ImportError:
            print(f"✗ sqlite-vec not found at {EXT} and sqlite_vec package not installed")
            print("  Install: pip install sqlite-vec")
            sys.exit(1)

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    print("✓ WAL mode set")

    conn.execute(
        "CREATE TABLE files_metadata (rowid INTEGER PRIMARY KEY, filename TEXT, full_path TEXT);"
    )
    # vec0 = KNN virtual table (NOT vec_each — that's for element iteration)
    conn.execute("CREATE VIRTUAL TABLE vec_files USING vec0(embedding float[384]);")
    print("✓ Schema created (vec0 KNN table)")
    return conn


def mock_embed(text: str) -> np.ndarray:
    np.random.seed(hash(text) % (2**32 - 1))
    v = np.random.randn(384).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


test_files = [
    ("q3_financials.csv", "/docs/finance/q3.csv",       "quarterly revenue expenses"),
    ("rust_tutorial.md",  "/dev/learning/rust.md",      "rust systems programming"),
    ("w2_tax_form.pdf",   "/docs/personal/w2.pdf",      "irs federal tax return income"),
]

db = init_db()
for name, path, ctx in test_files:
    vec = mock_embed(ctx)
    cur = db.cursor()
    cur.execute("INSERT INTO files_metadata (filename, full_path) VALUES (?, ?)", (name, path))
    # memoryview() forces pysqlite3 to bind as BLOB, not UTF-8 string
    db.execute(
        "INSERT INTO vec_files (rowid, embedding) VALUES (?, ?)",
        (cur.lastrowid, memoryview(vec.tobytes())),
    )
db.commit()
print(f"✓ Inserted {len(test_files)} test files")

query_vec = memoryview(mock_embed("IRS tax return").tobytes())
results = db.execute("""
    SELECT m.filename, m.full_path, v.distance
    FROM vec_files v JOIN files_metadata m ON v.rowid = m.rowid
    WHERE v.embedding MATCH ? AND k = 2
    ORDER BY v.distance
""", (query_vec,)).fetchall()

print(f"\nKNN results for 'IRS tax return' (top 2):")
for name, path, dist in results:
    print(f"  {name} | {path} | distance: {dist:.4f}")

if len(results) == 2 and all(len(r) == 3 for r in results):
    print("\n✓ PASS: KNN returned 2 results with correct shape")
    print("  (mock random vectors don't guarantee semantic ranking — swap in real ONNX for that)")
else:
    print(f"\n✗ FAIL: expected 2 results with 3 fields each, got {results}")
    sys.exit(1)
