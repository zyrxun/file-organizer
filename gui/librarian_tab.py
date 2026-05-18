import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QMessageBox,
    QFrame, QGraphicsDropShadowEffect,
)

import config
from librarian.indexer import build_index, WatchdogWorker
from librarian.searcher import search


class _IndexWorker(QThread):
    progress = Signal(int, int)
    status = Signal(str)
    done = Signal()
    error = Signal(str)

    def __init__(self, root_path: str):
        super().__init__()
        self.root_path = root_path

    def run(self) -> None:
        try:
            self.status.emit("Syncing local database…")
            build_index(
                self.root_path,
                on_progress=lambda i, n: self.progress.emit(i, n),
            )
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class _SearchWorker(QThread):
    done = Signal(list)
    error = Signal(str)

    def __init__(self, query: str, root_path: str):
        super().__init__()
        self.query = query
        self.root_path = root_path

    def run(self) -> None:
        try:
            results = search(self.query, self.root_path)
            self.done.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class _WatchdogThread(QThread):
    def __init__(self, worker: WatchdogWorker, root_path: str):
        super().__init__()
        self._worker = worker
        self._root = root_path

    def run(self) -> None:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        w = self._worker

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    w.on_created(event.src_path)
            def on_modified(self, event):
                if not event.is_directory:
                    w.on_modified(event.src_path)
            def on_deleted(self, event):
                if not event.is_directory:
                    w.on_deleted(event.src_path)
            def on_moved(self, event):
                if not event.is_directory:
                    w.on_moved(event.src_path, event.dest_path)

        observer = Observer()
        observer.schedule(_Handler(), self._root, recursive=True)
        observer.start()
        try:
            observer.join()
        except Exception:
            observer.stop()


class LibrarianTab(QWidget):
    def __init__(self):
        super().__init__()
        self._root_path: str | None = None
        self._watchdog_thread: _WatchdogThread | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Card factory — white rounded panel with a soft drop shadow.
    # ------------------------------------------------------------------
    def _make_card(self) -> tuple["QFrame", "QVBoxLayout"]:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 18))
        card.setGraphicsEffect(shadow)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(14, 12, 14, 12)
        vbox.setSpacing(8)
        return card, vbox

    def _build_ui(self) -> None:
        PATH_LABEL_STYLE = """
            QLabel {
                background: #F3F4F6;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 4px 8px;
                color: #374151;
                font-size: 13px;
            }
        """
        SEARCH_BTN_STYLE = """
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
                min-height: 30px;
            }
            QPushButton:hover    { background-color: #1D4ED8; }
            QPushButton:pressed  { background-color: #1E40AF; }
            QPushButton:disabled { background-color: #93C5FD; color: #FFFFFF; }
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ── Card 1: Folder picker ──────────────────────────────────
        folder_card, folder_vbox = self._make_card()

        folder_row = QHBoxLayout()
        folder_hdr = QLabel("Folder")
        folder_hdr.setStyleSheet("font-weight: 600; color: #374151; min-width: 52px;")
        self._folder_label = QLabel("No folder indexed")
        self._folder_label.setStyleSheet(PATH_LABEL_STYLE)
        pick_btn = QPushButton("Choose Folder…")
        pick_btn.clicked.connect(self._pick_folder)
        folder_row.addWidget(folder_hdr)
        folder_row.addWidget(self._folder_label, 1)
        folder_row.addWidget(pick_btn)
        folder_vbox.addLayout(folder_row)

        layout.addWidget(folder_card)

        # Status / progress (outside card — collapses when empty)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 12px; color: #6B7280; padding-left: 2px;")
        layout.addWidget(self._status_label)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedHeight(8)
        layout.addWidget(self._progress)

        # ── Card 2: Search bar ─────────────────────────────────────
        search_card, search_vbox = self._make_card()

        search_row = QHBoxLayout()
        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("Describe what you're looking for…")
        self._search_bar.returnPressed.connect(self._run_search)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._run_search)
        search_btn.setStyleSheet(SEARCH_BTN_STYLE)
        search_row.addWidget(self._search_bar, 1)
        search_row.addWidget(search_btn)
        search_vbox.addLayout(search_row)

        layout.addWidget(search_card)

        # ── Results list ───────────────────────────────────────────
        self._results = QListWidget()
        self._results.itemDoubleClicked.connect(self._open_result)
        self._results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._results.customContextMenuRequested.connect(self._results_context)
        self._results.setAlternatingRowColors(True)
        layout.addWidget(self._results)

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Folder to Index")
        if not path:
            return
        self._root_path = path
        self._folder_label.setText(path)
        self._start_index()

    def _start_index(self) -> None:
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._status_label.setText("Syncing local database…")

        self._index_worker = _IndexWorker(self._root_path)
        self._index_worker.progress.connect(self._on_index_progress)
        self._index_worker.status.connect(self._status_label.setText)
        self._index_worker.done.connect(self._on_index_done)
        self._index_worker.error.connect(self._on_index_error)
        self._index_worker.start()

    def _on_index_progress(self, done: int, total: int) -> None:
        self._progress.setRange(0, total)
        self._progress.setValue(done)
        self._status_label.setText(f"Syncing local database… {done}/{total} files")

    def _on_index_done(self) -> None:
        self._progress.setVisible(False)
        self._status_label.setText("Index ready. Starting live sync…")
        self._start_watchdog()

    def _on_index_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._status_label.setText("Index error — check console.")
        QMessageBox.critical(self, "Index Error", msg)

    def _start_watchdog(self) -> None:
        if self._watchdog_thread:
            self._watchdog_thread.quit()
        worker = WatchdogWorker(self._root_path)
        self._watchdog_thread = _WatchdogThread(worker, self._root_path)
        self._watchdog_thread.start()
        self._status_label.setText("Live sync active.")

    def _run_search(self) -> None:
        query = self._search_bar.text().strip()
        if not query or not self._root_path:
            return
        self._results.clear()
        self._status_label.setText("Searching…")

        self._search_worker = _SearchWorker(query, self._root_path)
        self._search_worker.done.connect(self._on_search_done)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_done(self, results: list) -> None:
        self._results.clear()
        self._status_label.setText(f"{len(results)} result(s)")
        for r in results:
            score_pct = int(r["score"] * 100)
            item = QListWidgetItem(f"[{score_pct}%]  {r['filename']}  —  {r['path']}")
            item.setData(Qt.ItemDataRole.UserRole, r["path"])
            self._results.addItem(item)

    def _on_search_error(self, msg: str) -> None:
        self._status_label.setText("Search error.")
        QMessageBox.critical(self, "Search Error", msg)

    def _open_result(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])

    def _results_context(self, pos) -> None:
        item = self._results.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        reveal = menu.addAction("Reveal in Finder")
        action = menu.exec(self._results.mapToGlobal(pos))
        if action == reveal and path:
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
