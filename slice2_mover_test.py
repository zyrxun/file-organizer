"""
Slice 2 verification: mover.py — atomic rename, collision loop, undo, PENDING_DELETE reconciliation.
Run: python3 slice2_mover_test.py
"""
import os, sys, shutil, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from organizer.mover import execute_moves, undo_last, reconcile_pending, _sha256, _unique_dest, DB_PATH

PASS = "[+]"
FAIL = "[!]"

def check(label, condition, detail=""):
    if condition:
        print(f"{PASS} {label}")
    else:
        print(f"{FAIL} FAILED: {label} {detail}")
        sys.exit(1)

def make_file(path: str, content: str = "test content") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return path


with tempfile.TemporaryDirectory() as tmp:
    src_dir = os.path.join(tmp, "source")
    dst_dir = os.path.join(tmp, "dest")
    os.makedirs(src_dir); os.makedirs(dst_dir)

    print("\n── Test 1: Basic same-volume move ──")
    f1 = make_file(os.path.join(src_dir, "report.pdf"), "report data")
    result = execute_moves([{"src": f1, "dest_dir": dst_dir}], session_id="test1")
    check("file moved", os.path.exists(os.path.join(dst_dir, "report.pdf")))
    check("source gone", not os.path.exists(f1))
    check("method is rename", result["moved"][0]["method"] == "rename")
    check("no failures", len(result["failed"]) == 0)

    print("\n── Test 2: Collision loop ──")
    # Pre-populate destination with taxes.pdf, taxes (1).pdf, taxes (2).pdf
    for i, name in enumerate(["taxes.pdf", "taxes (1).pdf", "taxes (2).pdf"]):
        make_file(os.path.join(dst_dir, name), f"existing {i}")
    f2 = make_file(os.path.join(src_dir, "taxes.pdf"), "new taxes")
    result = execute_moves([{"src": f2, "dest_dir": dst_dir}], session_id="test2")
    landed = result["moved"][0]["dest"]
    check("collision resolved to (3)", landed.endswith("taxes (3).pdf"))
    check("no existing files clobbered", open(os.path.join(dst_dir, "taxes.pdf")).read() == "existing 0")

    print("\n── Test 3: Undo ──")
    session = "test3"
    f3 = make_file(os.path.join(src_dir, "undo_me.txt"), "undo content")
    result = execute_moves([{"src": f3, "dest_dir": dst_dir}], session_id=session)
    dest_path = result["moved"][0]["dest"]
    check("file at dest before undo", os.path.exists(dest_path))
    undo = undo_last(session)
    check("undo restored file", len(undo["restored"]) == 1)
    check("file back at original path", os.path.exists(f3))
    check("dest gone after undo", not os.path.exists(dest_path))

    print("\n── Test 4: Missing source handled gracefully ──")
    result = execute_moves([{"src": "/nonexistent/ghost.pdf", "dest_dir": dst_dir}], session_id="test4")
    check("failure recorded", len(result["failed"]) == 1)
    check("reason is source not found", "source not found" in result["failed"][0]["reason"])

    print("\n── Test 5: PENDING_DELETE reconciliation ──")
    import sqlite3 as _sqlite3
    # Simulate a crash: file copied to dest but src not yet deleted, status = PENDING_DELETE
    crash_src = make_file(os.path.join(src_dir, "crash_file.txt"), "crash content")
    crash_dest = os.path.join(dst_dir, "crash_file.txt")
    shutil.copy2(crash_src, crash_dest)
    checksum = _sha256(crash_src)
    conn = _sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        INSERT INTO moves (session_id, src, dest, checksum, status, created_at)
        VALUES ('test5', ?, ?, ?, 'PENDING_DELETE', ?)
    """, (crash_src, crash_dest, checksum, time.time()))
    conn.commit(); conn.close()
    # Reconcile — should delete the original
    resolved = reconcile_pending()
    check("reconciled 1 pending record", resolved >= 1)
    check("original deleted after reconcile", not os.path.exists(crash_src))
    check("dest still intact", os.path.exists(crash_dest))

    print("\n── Test 6: _unique_dest loop ──")
    with tempfile.TemporaryDirectory() as d:
        make_file(os.path.join(d, "a.txt"))
        make_file(os.path.join(d, "a (1).txt"))
        make_file(os.path.join(d, "a (2).txt"))
        result_path = _unique_dest(os.path.join(d, "a.txt"))
        check("unique dest is a (3).txt", result_path.endswith("a (3).txt"))

print("\n[+] Slice 2 PASSED — mover fully verified")
