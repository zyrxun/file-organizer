"""QThread workers — never touch UI widgets directly, communicate via Signals only."""
import os
import sys
import tempfile
from PySide6.QtCore import QThread, Signal


class CategorizeWorker(QThread):
    progress = Signal(int, int)       # (current_batch, total_batches)
    finished = Signal(dict)           # {"results": {filename: folder}, "failed_batches": [...]}
    error = Signal(str)

    def __init__(self, files, api_key, peek_mode, parent=None):
        super().__init__(parent)
        self.files = files
        self.api_key = api_key
        self.peek_mode = peek_mode
        self._cache_dir = os.path.join(tempfile.gettempdir(), "file-organizer-cache")

    def run(self):
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from organizer.categorizer import categorize
            result = categorize(
                self.files,
                api_key=self.api_key,
                peek_mode=self.peek_mode,
                cache_dir=self._cache_dir,
                progress_cb=lambda cur, total: self.progress.emit(cur, total),
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MoveWorker(QThread):
    progress = Signal(int, int)       # (done, total)
    finished = Signal(dict)           # {"moved": [...], "failed": [...], "session_id": str}
    error = Signal(str)

    def __init__(self, moves, session_id, parent=None):
        super().__init__(parent)
        self.moves = moves
        self.session_id = session_id

    def run(self):
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from organizer.mover import execute_moves
            result = execute_moves(self.moves, session_id=self.session_id)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class IndexWorker(QThread):
    progress = Signal(str)            # status message
    sync_complete = Signal(int)       # number of files indexed
    error = Signal(str)

    def __init__(self, root_path, db_path, ext_path, parent=None):
        super().__init__(parent)
        self.root_path = root_path
        self.db_path = db_path
        self.ext_path = ext_path

    def run(self):
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from librarian.indexer import build_index
            count = build_index(
                self.root_path,
                self.db_path,
                self.ext_path,
                progress_cb=lambda msg: self.progress.emit(msg),
            )
            self.sync_complete.emit(count)
        except Exception as e:
            self.error.emit(str(e))
