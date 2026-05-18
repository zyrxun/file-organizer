import os
from collections import defaultdict


def build_tree(assignments: dict[str, str]) -> dict:
    tree = defaultdict(list)
    for filename, folder in assignments.items():
        tree[folder].append(filename)
    return dict(tree)


def to_markdown(tree: dict, root_label: str = "Organized Files") -> str:
    lines = [f"# {root_label}\n"]
    for folder in sorted(tree):
        lines.append(f"## {folder}")
        for name in sorted(tree[folder]):
            lines.append(f"  - {name}")
        lines.append("")
    return "\n".join(lines)


def open_in_finder(path: str) -> None:
    import subprocess, sys
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", path])
