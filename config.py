import os
import sys

if sys.platform == "darwin":
    APP_DATA_DIR = os.path.expanduser("~/Library/Application Support/FileOrganizer")
elif sys.platform == "win32":
    APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "FileOrganizer")
else:
    APP_DATA_DIR = os.path.expanduser("~/.config/fileorganizer")

os.makedirs(APP_DATA_DIR, exist_ok=True)

ORGANIZER_DB_PATH  = os.path.join(APP_DATA_DIR, "organizer.db")
LIBRARIAN_DB_PATH  = os.path.join(APP_DATA_DIR, "librarian.db")
BATCH_CACHE_DIR    = os.path.join(APP_DATA_DIR, "batch_cache")
LARGE_FILE_CEILING = 50 * 1024 * 1024  # 50MB — skip heavy parsers above this
PEEK_FOLDER_CEILING = 1000             # warn + offer downgrade above this file count
BATCH_SIZE = 50
MAX_PEEK_CHARS = 500
MAX_CONTEXT_CHARS = 500

# Haiku 4.5 pricing (USD per 1M tokens)
HAIKU_INPUT_PRICE_PER_M  = 0.80
HAIKU_OUTPUT_PRICE_PER_M = 4.00
DEFAULT_COST_THRESHOLD   = 1.00  # warn before exceeding this per run

os.makedirs(BATCH_CACHE_DIR, exist_ok=True)


def get_api_key() -> str | None:
    try:
        import keyring
        return keyring.get_password("FileOrganizer", "anthropic_api_key")
    except Exception:
        return None


def set_api_key(key: str) -> None:
    import keyring
    keyring.set_password("FileOrganizer", "anthropic_api_key", key)


def get_cost_threshold() -> float:
    try:
        import keyring
        v = keyring.get_password("FileOrganizer", "cost_threshold")
        return float(v) if v else DEFAULT_COST_THRESHOLD
    except Exception:
        return DEFAULT_COST_THRESHOLD


def set_cost_threshold(value: float) -> None:
    import keyring
    keyring.set_password("FileOrganizer", "cost_threshold", str(value))


def get_folder_depth() -> int:
    try:
        import keyring
        v = keyring.get_password("FileOrganizer", "folder_depth")
        return int(v) if v else 2
    except Exception:
        return 2


def set_folder_depth(value: int) -> None:
    import keyring
    keyring.set_password("FileOrganizer", "folder_depth", str(value))
