import os

_SKIP_NAMES = {".DS_Store", "thumbs.db", "desktop.ini", "Thumbs.db"}
_SKIP_DIRS  = {"__MACOSX", "$RECYCLE.BIN", ".Trash", "node_modules", ".git"}


def scan_directory(path: str, max_depth: int = 2) -> list[dict]:
    results = []
    _walk(path, path, 0, max_depth, results)
    return results


def _walk(root: str, current: str, depth: int, max_depth: int, out: list) -> None:
    if depth > max_depth:
        return
    try:
        entries = os.scandir(current)
    except PermissionError:
        return

    for entry in entries:
        name = entry.name
        if name.startswith(".") or name in _SKIP_NAMES:
            continue
        if entry.is_dir(follow_symlinks=False):
            if name in _SKIP_DIRS:
                continue
            _walk(root, entry.path, depth + 1, max_depth, out)
        elif entry.is_file(follow_symlinks=False):
            try:
                stat = entry.stat()
                size_kb = stat.st_size / 1024
                _, ext = os.path.splitext(name)
                out.append({
                    "name": name,
                    "path": entry.path,
                    "ext":  ext.lower(),
                    "size_kb": round(size_kb, 1),
                    "mtime": stat.st_mtime,
                    "ctime": stat.st_ctime,
                })
            except OSError:
                pass
