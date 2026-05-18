import os
import uuid
from datetime import datetime

from PySide6.QtCore import (
    Qt, QThread, Signal, QDate, QDateTime,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QCheckBox, QComboBox, QDateEdit, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QMessageBox, QSizePolicy, QGroupBox, QPlainTextEdit,
)

import config
from organizer.scanner import scan_directory
from organizer.date_filter import apply_date_filter
from organizer.categorizer import categorize
from organizer.mover import get_db, move_files, undo_last, recover_pending
from organizer.tree_renderer import build_tree, open_in_finder


class _AnalyseWorker(QThread):
    progress = Signal(int, int)
    done = Signal(dict)
    error = Signal(str)

    def __init__(self, files: list[dict], peek_mode: bool, user_context: str = ""):
        super().__init__()
        self.files = files
        self.peek_mode = peek_mode
        self.user_context = user_context

    def run(self) -> None:
        try:
            result = categorize(
                self.files,
                peek_mode=self.peek_mode,
                user_context=self.user_context,
                on_batch_complete=lambda i, n: self.progress.emit(i + 1, n),
            )
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class _MoveWorker(QThread):
    progress = Signal(int, int)
    done = Signal(list)

    def __init__(self, assignments, src_root, dst_root, session_id, db):
        super().__init__()
        self.assignments = assignments
        self.src_root = src_root
        self.dst_root = dst_root
        self.session_id = session_id
        self.db = db

    def run(self) -> None:
        errors = move_files(
            self.assignments,
            self.src_root,
            self.dst_root,
            self.session_id,
            self.db,
            on_progress=lambda i, n: self.progress.emit(i, n),
        )
        self.done.emit(errors)


class OrganizerTab(QWidget):
    def __init__(self):
        super().__init__()
        self._assignments: dict[str, str] = {}
        self._scanned: list[dict] = []
        self._session_id = str(uuid.uuid4())
        self._db = get_db()
        _warn = recover_pending(self._db)
        if _warn:
            QMessageBox.warning(self, "Incomplete Moves Detected", "\n".join(_warn))

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Source row
        src_row = QHBoxLayout()
        self._src_label = QLabel("No folder selected")
        src_btn = QPushButton("Choose Source Folder…")
        src_btn.clicked.connect(self._pick_src)
        src_row.addWidget(QLabel("Source:"))
        src_row.addWidget(self._src_label, 1)
        src_row.addWidget(src_btn)
        layout.addLayout(src_row)

        # Dest row (same folder by default)
        dst_row = QHBoxLayout()
        self._dst_label = QLabel("Same as source")
        dst_btn = QPushButton("Choose Destination…")
        dst_btn.clicked.connect(self._pick_dst)
        dst_row.addWidget(QLabel("Dest:"))
        dst_row.addWidget(self._dst_label, 1)
        dst_row.addWidget(dst_btn)
        layout.addLayout(dst_row)

        # Peek mode
        peek_row = QHBoxLayout()
        self._peek_cb = QCheckBox("Peek inside files (reads content, opt-in, may increase cost)")
        peek_row.addWidget(self._peek_cb)
        layout.addLayout(peek_row)

        # Context hint box (collapsible)
        self._context_box = QGroupBox("Context (optional)")
        self._context_box.setCheckable(True)
        self._context_box.setChecked(False)
        context_layout = QVBoxLayout(self._context_box)
        self._context_edit = QPlainTextEdit()
        self._context_edit.setPlaceholderText(
            "e.g. 2020–2024 I was a university student studying engineering. "
            "I also do freelance graphic design."
        )
        self._context_edit.setFixedHeight(72)
        self._context_edit.textChanged.connect(self._on_context_changed)
        self._context_counter = QLabel(f"0 / {config.MAX_CONTEXT_CHARS}")
        self._context_counter.setStyleSheet("color: #888; font-size: 11px;")
        context_layout.addWidget(self._context_edit)
        context_layout.addWidget(self._context_counter)
        layout.addWidget(self._context_box)

        # Date filter row
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Date filter:"))
        self._date_type = QComboBox()
        self._date_type.addItems(["Modified", "Created"])
        date_row.addWidget(self._date_type)

        self._from_enabled = QCheckBox("From")
        self._from_date = QDateEdit(calendarPopup=True)
        self._from_date.setDate(QDate.currentDate())
        self._from_date.setEnabled(False)
        self._from_enabled.toggled.connect(self._from_date.setEnabled)
        date_row.addWidget(self._from_enabled)
        date_row.addWidget(self._from_date)

        self._to_enabled = QCheckBox("To")
        self._to_date = QDateEdit(calendarPopup=True)
        self._to_date.setDate(QDate.currentDate())
        self._to_date.setEnabled(False)
        self._to_enabled.toggled.connect(self._to_date.setEnabled)
        date_row.addWidget(self._to_enabled)
        date_row.addWidget(self._to_date)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_date_filter)
        date_row.addWidget(clear_btn)
        date_row.addStretch()
        layout.addLayout(date_row)

        # File count label
        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

        # Action buttons
        btn_row = QHBoxLayout()
        self._analyse_btn = QPushButton("Analyse & Preview")
        self._analyse_btn.clicked.connect(self._start_analyse)
        self._confirm_btn = QPushButton("Confirm & Move")
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._start_move)
        self._undo_btn = QPushButton("Undo Last")
        self._undo_btn.clicked.connect(self._undo)
        btn_row.addWidget(self._analyse_btn)
        btn_row.addWidget(self._confirm_btn)
        btn_row.addWidget(self._undo_btn)
        layout.addLayout(btn_row)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Tree preview
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Proposed folder structure")
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._tree_context)
        layout.addWidget(self._tree)

        self._src_path: str | None = None
        self._dst_path: str | None = None

    def _on_context_changed(self) -> None:
        text = self._context_edit.toPlainText()
        limit = config.MAX_CONTEXT_CHARS
        if len(text) > limit:
            cursor = self._context_edit.textCursor()
            self._context_edit.setPlainText(text[:limit])
            self._context_edit.setTextCursor(cursor)
        count = min(len(text), limit)
        self._context_counter.setText(f"{count} / {limit}")
        color = "#cc4444" if count >= limit else "#888"
        self._context_counter.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _pick_src(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if path:
            self._src_path = path
            self._src_label.setText(path)
            if self._dst_path is None:
                self._dst_label.setText(f"{path} (same)")

    def _pick_dst(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if path:
            self._dst_path = path
            self._dst_label.setText(path)

    def _clear_date_filter(self) -> None:
        self._from_enabled.setChecked(False)
        self._to_enabled.setChecked(False)

    def _start_analyse(self) -> None:
        if not self._src_path:
            QMessageBox.warning(self, "No Source", "Please select a source folder first.")
            return

        if not config.get_api_key():
            QMessageBox.warning(self, "No API Key", "Please set your Anthropic API key.")
            return

        self._scanned = scan_directory(self._src_path)

        date_type = self._date_type.currentText().lower()
        from_ts = (
            QDateTime(self._from_date.date()).toSecsSinceEpoch()
            if self._from_enabled.isChecked() else None
        )
        to_ts = (
            QDateTime(self._to_date.date()).toSecsSinceEpoch()
            if self._to_enabled.isChecked() else None
        )
        filtered = apply_date_filter(self._scanned, date_type, from_ts, to_ts)

        excluded = len(self._scanned) - len(filtered)
        if excluded:
            self._count_label.setText(f"Found {len(filtered)} files ({excluded} excluded by date filter)")
        else:
            self._count_label.setText(f"Found {len(filtered)} files")

        if not filtered:
            QMessageBox.information(self, "No Files", "No files match the date filter.")
            return

        # Large folder + peek mode warning
        peek = self._peek_cb.isChecked()
        if peek and len(filtered) > config.PEEK_FOLDER_CEILING:
            resp = QMessageBox.question(
                self, "Large Folder",
                f"{len(filtered)} files with peek mode enabled may cost ~$0.50+.\n"
                "Switch to filename-only mode?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp == QMessageBox.StandardButton.Yes:
                peek = False
                self._peek_cb.setChecked(False)

        self._analyse_btn.setEnabled(False)
        self._confirm_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)

        user_context = ""
        if self._context_box.isChecked():
            user_context = self._context_edit.toPlainText().strip()[:config.MAX_CONTEXT_CHARS]

        self._worker = _AnalyseWorker(filtered, peek, user_context)
        self._worker.progress.connect(self._on_analyse_progress)
        self._worker.done.connect(self._on_analyse_done)
        self._worker.error.connect(self._on_analyse_error)
        self._worker.start()

    def _on_analyse_progress(self, done: int, total: int) -> None:
        self._progress.setRange(0, total)
        self._progress.setValue(done)

    def _on_analyse_done(self, assignments: dict) -> None:
        self._assignments = assignments
        self._progress.setVisible(False)
        self._analyse_btn.setEnabled(True)
        self._confirm_btn.setEnabled(True)
        self._render_preview(assignments)

    def _on_analyse_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._analyse_btn.setEnabled(True)
        QMessageBox.critical(self, "Analysis Failed", msg)

    def _render_preview(self, assignments: dict) -> None:
        self._tree.clear()
        tree = build_tree(assignments)
        for folder in sorted(tree):
            folder_item = QTreeWidgetItem([folder])
            for name in sorted(tree[folder]):
                child = QTreeWidgetItem([name])
                child.setToolTip(0, f"Will be moved to: {folder}/{name}")
                folder_item.addChild(child)
            self._tree.addTopLevelItem(folder_item)
        self._tree.expandAll()

    def _start_move(self) -> None:
        if not self._assignments:
            return
        dst = self._dst_path or self._src_path
        reply = QMessageBox.question(
            self, "Confirm Move",
            f"Move {len(self._assignments)} files to '{dst}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._confirm_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(self._assignments))
        self._progress.setValue(0)
        self._session_id = str(uuid.uuid4())

        self._move_worker = _MoveWorker(
            self._assignments, self._src_path, dst, self._session_id, self._db
        )
        self._move_worker.progress.connect(
            lambda i, n: self._progress.setValue(i)
        )
        self._move_worker.done.connect(self._on_move_done)
        self._move_worker.start()

    def _on_move_done(self, errors: list) -> None:
        self._progress.setVisible(False)
        self._confirm_btn.setEnabled(True)
        if errors:
            QMessageBox.warning(self, "Move Errors", "\n".join(errors[:10]))
        else:
            QMessageBox.information(self, "Done", "All files moved successfully.")
        self._assignments = {}

    def _undo(self) -> None:
        errors = undo_last(self._session_id, self._db)
        if errors:
            QMessageBox.warning(self, "Undo Errors", "\n".join(errors))
        else:
            QMessageBox.information(self, "Undo Complete", "Last session moves reversed.")

    def _tree_context(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item and item.parent() is None:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            open_act = menu.addAction("Open in Finder")
            action = menu.exec(self._tree.mapToGlobal(pos))
            if action == open_act:
                dst = self._dst_path or self._src_path
                if dst:
                    open_in_finder(os.path.join(dst, item.text(0)))
