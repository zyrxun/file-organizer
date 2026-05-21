import os
from collections import defaultdict


def build_tree(assignments: dict[str, str]) -> dict:
    """Return a nested dict: {top: {sub: [filenames]}} or {top: [filenames]}."""
    tree = defaultdict(lambda: defaultdict(list))
    for filename, folder in assignments.items():
        parts = folder.split("/", 1)
        top = parts[0]
        sub = parts[1] if len(parts) > 1 else ""
        tree[top][sub].append(filename)
    return {k: dict(v) for k, v in tree.items()}


def to_markdown(tree: dict, root_label: str = "Organized Files") -> str:
    lines = [f"# {root_label}\n"]
    for top in sorted(tree):
        lines.append(f"## {top}")
        for sub, files in sorted(tree[top].items()):
            if sub:
                lines.append(f"### {sub}")
                for name in sorted(files):
                    lines.append(f"    - {name}")
            else:
                for name in sorted(files):
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
