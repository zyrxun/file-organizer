import os
import uuid
from datetime import datetime

from PySide6.QtCore import (
    Qt, QThread, Signal, QDate, QDateTime, QTime,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QCheckBox, QComboBox, QDateEdit, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QMessageBox, QSizePolicy, QGroupBox, QPlainTextEdit,
    QFrame, QGraphicsDropShadowEffect,
)

import subprocess
import sys

import config
from organizer.scanner import scan_directory
from organizer.date_filter import apply_date_filter
from organizer.categorizer import categorize, estimate_cost
from organizer.mover import get_db, move_files, undo_last, recover_pending
from organizer.tree_renderer import build_tree, open_in_finder


def _notify(title: str, body: str) -> None:
    if sys.platform == "darwin":
        try:
            script = (
                f'display notification "{body}" with title "{title}" '
                f'sound name "default"'
            )
            subprocess.run(["osascript", "-e", script], check=False, timeout=3)
        except Exception:
            pass


class _AnalyseWorker(QThread):
    progress = Signal(int, int)
    done = Signal(dict, object)  # (assignments, CostInfo)
    error = Signal(str)

    def __init__(self, files: list[dict], peek_mode: bool, user_context: str = ""):
        super().__init__()
        self.files = files
        self.peek_mode = peek_mode
        self.user_context = user_context

    def run(self) -> None:
        try:
            assignments, cost_info = categorize(
                self.files,
                peek_mode=self.peek_mode,
                user_context=self.user_context,
                on_batch_complete=lambda i, n: self.progress.emit(i + 1, n),
            )
            self.done.emit(assignments, cost_info)
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
        # Shared style for read-only path labels (looks like a disabled input)
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
        # Accent-blue primary button
        PRIMARY_BTN_STYLE = """
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 7px 18px;
                min-height: 32px;
            }
            QPushButton:hover    { background-color: #1D4ED8; }
            QPushButton:pressed  { background-color: #1E40AF; }
            QPushButton:disabled { background-color: #93C5FD; color: #FFFFFF; }
        """
        # Green success button
        SUCCESS_BTN_STYLE = """
            QPushButton {
                background-color: #16A34A;
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 7px 18px;
                min-height: 32px;
            }
            QPushButton:hover    { background-color: #15803D; }
            QPushButton:pressed  { background-color: #166534; }
            QPushButton:disabled { background-color: #86EFAC; color: #FFFFFF; }
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ── Card 1: Folder pickers ─────────────────────────────────
        folders_card, folders_vbox = self._make_card()

        src_row = QHBoxLayout()
        src_hdr = QLabel("Source")
        src_hdr.setStyleSheet("font-weight: 600; color: #374151; min-width: 52px;")
        self._src_label = QLabel("No folder selected")
        self._src_label.setStyleSheet(PATH_LABEL_STYLE)
        src_btn = QPushButton("Choose…")
        src_btn.clicked.connect(self._pick_src)
        src_row.addWidget(src_hdr)
        src_row.addWidget(self._src_label, 1)
        src_row.addWidget(src_btn)
        folders_vbox.addLayout(src_row)

        dst_row = QHBoxLayout()
        dst_hdr = QLabel("Dest")
        dst_hdr.setStyleSheet("font-weight: 600; color: #374151; min-width: 52px;")
        self._dst_label = QLabel("Same as source")
        self._dst_label.setStyleSheet(PATH_LABEL_STYLE)
        dst_btn = QPushButton("Choose…")
        dst_btn.clicked.connect(self._pick_dst)
        dst_row.addWidget(dst_hdr)
        dst_row.addWidget(self._dst_label, 1)
        dst_row.addWidget(dst_btn)
        folders_vbox.addLayout(dst_row)

        layout.addWidget(folders_card)

        # ── Card 2: Options (peek · context · date filter) ─────────
        options_card, options_vbox = self._make_card()

        self._peek_cb = QCheckBox("Peek inside files (reads content, opt-in, may increase cost)")
        options_vbox.addWidget(self._peek_cb)

        # Profile quick-select
        profile_row = QHBoxLayout()
        profile_lbl = QLabel("Profile:")
        profile_lbl.setStyleSheet("font-weight: 600; color: #374151;")
        self._profile_combo = QComboBox()
        self._profile_combo.addItems([
            "Custom (write your own below)",
            "High School Student",
            "University / College Student",
            "Freelancer / Creative",
            "Office Professional",
            "Small Business Owner",
            "Parent / Family",
            "Researcher / Academic",
        ])
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_row.addWidget(profile_lbl)
        profile_row.addWidget(self._profile_combo, 1)
        options_vbox.addLayout(profile_row)

        # Collapsible context hint
        self._context_box = QGroupBox("Context — describe yourself so folders match your life")
        self._context_box.setCheckable(True)
        self._context_box.setChecked(True)
        context_layout = QVBoxLayout(self._context_box)
        self._context_edit = QPlainTextEdit()
        self._context_edit.setPlaceholderText(
            "e.g. I'm in Year 12 doing IB. I study Maths, Biology, Chemistry, History and English. "
            "I also do freelance graphic design on the side."
        )
        self._context_edit.setFixedHeight(72)
        self._context_edit.textChanged.connect(self._on_context_changed)
        self._context_counter = QLabel(f"0 / {config.MAX_CONTEXT_CHARS}")
        self._context_counter.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        context_layout.addWidget(self._context_edit)
        context_layout.addWidget(self._context_counter)
        options_vbox.addWidget(self._context_box)

        # Date filter row
        date_row = QHBoxLayout()
        date_hdr = QLabel("Date filter:")
        date_hdr.setStyleSheet("font-weight: 600; color: #374151;")
        date_row.addWidget(date_hdr)
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
        options_vbox.addLayout(date_row)

        layout.addWidget(options_card)

        # ── Card 3: Action buttons ─────────────────────────────────
        actions_card, actions_vbox = self._make_card()

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("font-size: 12px; color: #6B7280;")
        actions_vbox.addWidget(self._count_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._analyse_btn = QPushButton("Analyse & Preview")
        self._analyse_btn.clicked.connect(self._start_analyse)
        self._analyse_btn.setStyleSheet(PRIMARY_BTN_STYLE)

        self._confirm_btn = QPushButton("Confirm & Move")
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._start_move)
        self._confirm_btn.setStyleSheet(SUCCESS_BTN_STYLE)

        self._undo_btn = QPushButton("Undo Last")
        self._undo_btn.clicked.connect(self._undo)
        # ghost style — inherits from global QPushButton rules

        btn_row.addWidget(self._analyse_btn)
        btn_row.addWidget(self._confirm_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._undo_btn)
        actions_vbox.addLayout(btn_row)

        layout.addWidget(actions_card)

        # ── Progress bar (accent blue, slim) ───────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedHeight(8)
        layout.addWidget(self._progress)

        # ── Status label (shown during analysis) ───────────────────
        self._status_label = QLabel("")
        self._status_label.setVisible(False)
        self._status_label.setStyleSheet(
            "color: #2563EB; font-size: 13px; padding: 2px 0;"
        )
        layout.addWidget(self._status_label)

        # ── Tree preview ───────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Proposed folder structure")
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._tree_context)
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree)

        self._src_path: str | None = None
        self._dst_path: str | None = None

    _PROFILE_PRESETS = {
        "High School Student": (
            "I am a high school student. I have files related to my subjects (e.g. Maths, English, Sciences, Humanities), "
            "homework, assignments, and exam prep. I also have personal files like photos, music, and social content."
        ),
        "University / College Student": (
            "I am a university student. I have lecture notes, assignments, and readings organised by course/subject. "
            "I also have research papers, a thesis or project, and personal files."
        ),
        "Freelancer / Creative": (
            "I am a freelancer or creative professional. I have client projects, invoices, contracts, and design or "
            "creative assets. I also have business admin files and personal files."
        ),
        "Office Professional": (
            "I work in an office environment. I have work documents, meeting notes, reports, presentations, and "
            "spreadsheets organised by project or department. I also have personal files."
        ),
        "Small Business Owner": (
            "I run a small business. I have invoices, receipts, contracts, employee records, marketing materials, "
            "and financial documents. I also have personal files mixed in."
        ),
        "Parent / Family": (
            "I manage files for a family. I have school documents for kids, family photos and videos, medical records, "
            "household bills and receipts, and personal documents for multiple family members."
        ),
        "Researcher / Academic": (
            "I am a researcher or academic. I have research papers, literature notes, data files, writing drafts, "
            "conference materials, and teaching resources organised by project or topic."
        ),
    }

    def _on_profile_changed(self, index: int) -> None:
        label = self._profile_combo.currentText()
        preset = self._PROFILE_PRESETS.get(label)
        if preset:
            self._context_edit.setPlainText(preset)
            self._context_box.setChecked(True)

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
            QDateTime(self._from_date.date(), QTime(0, 0)).toSecsSinceEpoch()
            if self._from_enabled.isChecked() else None
        )
        to_ts = (
            QDateTime(self._to_date.date(), QTime(23, 59, 59)).toSecsSinceEpoch()
            if self._to_enabled.isChecked() else None
        )
        filtered = apply_date_filter(self._scanned, date_type, from_ts, to_ts)

        excluded = len(self._scanned) - len(filtered)
        peek = self._peek_cb.isChecked()
        est = estimate_cost(filtered, peek)
        base = f"Found {len(filtered)} files" + (f" ({excluded} excluded by date filter)" if excluded else "")
        self._count_label.setText(f"{base} — est. cost ~${est:.3f}")

        if not filtered:
            QMessageBox.information(self, "No Files", "No files match the date filter.")
            return

        # Large folder + peek mode warning
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
                est = estimate_cost(filtered, False)
                self._count_label.setText(self._count_label.text().split(" — ")[0] + f" — est. cost ~${est:.3f}")

        # Cost threshold warning
        threshold = config.get_cost_threshold()
        if est > threshold:
            resp = QMessageBox.question(
                self, "Cost Warning",
                f"Estimated cost ~${est:.3f} exceeds your warning threshold of ${threshold:.2f}.\n"
                "Proceed anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return

        self._analyse_btn.setEnabled(False)
        self._analyse_btn.setText("Analysing…")
        self._confirm_btn.setEnabled(False)
        self._progress.setFixedHeight(16)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._status_label.setText("Contacting Claude API…")
        self._status_label.setVisible(True)
        _notify("Analysis started", f"Organising {len(filtered)} files with Claude…")

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
        self._analyse_btn.setText(f"Analysing… ({done} of {total} batches)")
        self._status_label.setText(f"Processing batch {done} of {total}…")

    def _on_analyse_done(self, assignments: dict, cost_info) -> None:
        self._assignments = assignments
        self._progress.setVisible(False)
        self._progress.setFixedHeight(8)
        self._analyse_btn.setEnabled(True)
        self._analyse_btn.setText("Analyse & Preview")
        self._confirm_btn.setEnabled(True)
        self._status_label.setVisible(False)
        _notify("Analysis complete", f"Found {len(assignments)} files to organise.")
        total_tokens = cost_info.input_tokens + cost_info.output_tokens
        self._count_label.setText(
            self._count_label.text().split(" — ")[0]
            + f" — actual cost ${cost_info.cost_usd:.4f} ({total_tokens:,} tokens)"
        )
        self._render_preview(assignments)

    def _on_analyse_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._progress.setFixedHeight(8)
        self._analyse_btn.setEnabled(True)
        self._analyse_btn.setText("Analyse & Preview")
        self._status_label.setVisible(False)
        QMessageBox.critical(self, "Analysis Failed", msg)

    def _render_preview(self, assignments: dict) -> None:
        self._tree.clear()
        # System icons via QFileIconProvider (no extra dependencies)
        try:
            from PySide6.QtWidgets import QFileIconProvider
        except ImportError:
            from PySide6.QtGui import QFileIconProvider  # Qt 6.4+ location
        _ip = QFileIconProvider()
        folder_icon = _ip.icon(QFileIconProvider.IconType.Folder)
        file_icon   = _ip.icon(QFileIconProvider.IconType.File)

        tree = build_tree(assignments)
        for top in sorted(tree):
            top_item = QTreeWidgetItem([top])
            top_item.setIcon(0, folder_icon)
            for sub, files in sorted(tree[top].items()):
                if sub:
                    sub_item = QTreeWidgetItem([sub])
                    sub_item.setIcon(0, folder_icon)
                    for name in sorted(files):
                        child = QTreeWidgetItem([name])
                        child.setIcon(0, file_icon)
                        child.setToolTip(0, f"Will be moved to: {top}/{sub}/{name}")
                        sub_item.addChild(child)
                    top_item.addChild(sub_item)
                else:
                    for name in sorted(files):
                        child = QTreeWidgetItem([name])
                        child.setIcon(0, file_icon)
                        child.setToolTip(0, f"Will be moved to: {top}/{name}")
                        top_item.addChild(child)
            self._tree.addTopLevelItem(top_item)
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
            _notify("Move finished with errors", f"{len(errors)} file(s) could not be moved.")
        else:
            QMessageBox.information(self, "Done", "All files moved successfully.")
            _notify("Move complete", "All files have been organised successfully.")
        self._assignments = {}

    def _undo(self) -> None:
        errors = undo_last(self._session_id, self._db)
        if errors:
            QMessageBox.warning(self, "Undo Errors", "\n".join(errors))
        else:
            QMessageBox.information(self, "Undo Complete", "Last session moves reversed.")

    def _tree_context(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item and item.parent() is not None and item.parent().parent() is None:
            # sub-folder node or top-level folder node
            pass
        if item and item.childCount() > 0:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            open_act = menu.addAction("Open in Finder")
            action = menu.exec(self._tree.mapToGlobal(pos))
            if action == open_act:
                dst = self._dst_path or self._src_path
                if dst:
                    # Build path from top → sub
                    parts = [item.text(0)]
                    parent = item.parent()
                    while parent:
                        parts.insert(0, parent.text(0))
                        parent = parent.parent()
                    open_in_finder(os.path.join(dst, *parts))
