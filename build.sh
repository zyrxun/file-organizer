#!/usr/bin/env bash
# py2app build + DMG packaging for File Organizer + Librarian (macOS)
set -euo pipefail

APP_NAME="File Organizer"
BUNDLE_ID="com.fileorganizer.app"
DEVELOPER_ID="${DEVELOPER_ID:-}"   # set in env: export DEVELOPER_ID="Developer ID Application: ..."
TEAM_ID="${TEAM_ID:-}"             # set in env: export TEAM_ID="XXXXXXXXXX"

cd "$(dirname "$0")"

echo "==> Installing dependencies"
pip install -r requirements.txt

echo "==> Downloading model files"
python scripts/download_model.py

# Locate sqlite-vec dylib installed by the Python package
VEC_DYLIB=$(python -c "import sqlite_vec, os; print(os.path.join(os.path.dirname(sqlite_vec.__file__), 'sqlite_vec.dylib'))" 2>/dev/null || true)
if [ -z "$VEC_DYLIB" ] || [ ! -f "$VEC_DYLIB" ]; then
  echo "WARNING: sqlite_vec.dylib not found via package, searching site-packages..."
  VEC_DYLIB=$(find "$(python -c 'import site; print(site.getsitepackages()[0])')" -name "sqlite_vec.dylib" 2>/dev/null | head -1)
fi
echo "sqlite-vec dylib: ${VEC_DYLIB:-NOT FOUND}"

# Write setup.py dynamically
python - <<PYEOF
import os

vec_dylib = "${VEC_DYLIB:-}"
data_files = [
    ("", ["models/minilm/model_quantized.onnx",
          "models/minilm/tokenizer.json",
          "models/minilm/vocab.txt"]),
]
if vec_dylib and os.path.exists(vec_dylib):
    data_files.append(("", [vec_dylib]))

setup_src = '''
from setuptools import setup

APP = ["main.py"]
DATA_FILES = {data_files!r}
OPTIONS = {{
    "argv_emulation": False,
    "packages": ["anthropic", "PySide6", "pysqlite3", "onnxruntime", "tokenizers",
                 "numpy", "watchdog", "pypdf", "docx", "keyring"],
    "excludes": ["test", "tkinter", "matplotlib"],
    "iconfile": "assets/icon.icns" if os.path.exists("assets/icon.icns") else None,
    "plist": {{
        "CFBundleName": "File Organizer",
        "CFBundleDisplayName": "File Organizer + Librarian",
        "CFBundleIdentifier": "com.fileorganizer.app",
        "CFBundleVersion": "1.0.0",
        "NSHumanReadableCopyright": "© 2026 File Organizer",
    }},
}}

setup(
    name="File Organizer",
    app=APP,
    data_files=DATA_FILES,
    options={{"py2app": OPTIONS}},
    setup_requires=["py2app"],
)
'''.format(data_files=DATA_FILES)

with open("setup.py", "w") as f:
    f.write(setup_src)
print("setup.py written")
PYEOF

echo "==> Building .app bundle"
python setup.py py2app 2>&1

APP_PATH="dist/${APP_NAME}.app"

echo "==> Verifying dylib references"
SQLITE3_DYLIB=$(find "$APP_PATH" -name "*.so" -path "*pysqlite3*" | head -1)
PYSIDE6_DYLIB=$(find "$APP_PATH" -name "*.dylib" -path "*PySide6*" | head -1)
if [ -n "$SQLITE3_DYLIB" ]; then
  echo "pysqlite3 deps:"; otool -L "$SQLITE3_DYLIB"
fi

if [ -n "$DEVELOPER_ID" ]; then
  echo "==> Code signing"
  codesign --deep --force --options runtime \
    --sign "$DEVELOPER_ID" \
    --entitlements entitlements.plist \
    "$APP_PATH"

  echo "==> Notarizing"
  xcrun notarytool submit "${APP_NAME}.zip" \
    --team-id "$TEAM_ID" --wait
  xcrun stapler staple "$APP_PATH"
else
  echo "SKIP: DEVELOPER_ID not set, skipping codesign + notarize"
fi

if command -v create-dmg &>/dev/null; then
  echo "==> Creating DMG"
  create-dmg \
    --volname "${APP_NAME}" \
    --window-pos 200 120 \
    --window-size 600 300 \
    --icon-size 100 \
    --app-drop-link 450 150 \
    "${APP_NAME}.dmg" \
    "dist/"
else
  echo "SKIP: create-dmg not installed (brew install create-dmg)"
fi

echo "==> Build complete: dist/${APP_NAME}.app"
