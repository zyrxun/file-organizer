import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QMessageBox, QInputDialog,
    QLineEdit,
)

import config
from gui.organizer_tab import OrganizerTab
from gui.librarian_tab import LibrarianTab

# ---------------------------------------------------------------------------
# Global light theme — applied once to the QApplication instance.
# Accent:  #2563EB  (blue)
# Success: #16A34A  (green)   used by Confirm & Move
# Border:  #E5E7EB
# BG:      #F9FAFB  (off-white)
# ---------------------------------------------------------------------------
GLOBAL_STYLE = """
/* ── Base ─────────────────────────────────────────────────────────── */
QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter",
                 "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    color: #111827;
    background-color: #F9FAFB;
}

/* ── Tab bar ──────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #E5E7EB;
    border-top: none;
    background-color: #F9FAFB;
}
QTabBar::tab {
    background: #F3F4F6;
    border: 1px solid #E5E7EB;
    border-bottom: none;
    padding: 7px 22px;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
    color: #6B7280;
    font-size: 14px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #2563EB;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: #E5E7EB;
    color: #374151;
}

/* ── Buttons (default — ghost/neutral) ────────────────────────────── */
QPushButton {
    background-color: #F3F4F6;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 14px;
    color: #374151;
    min-height: 28px;
}
QPushButton:hover  { background-color: #E5E7EB; }
QPushButton:pressed { background-color: #D1D5DB; }
QPushButton:disabled {
    color: #9CA3AF;
    background-color: #F3F4F6;
    border-color: #E5E7EB;
}

/* ── Text inputs ──────────────────────────────────────────────────── */
QLineEdit, QPlainTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 14px;
    color: #111827;
    selection-background-color: #DBEAFE;
}
QLineEdit:focus, QPlainTextEdit:focus { border-color: #2563EB; }
QLineEdit:disabled, QPlainTextEdit:disabled {
    background-color: #F3F4F6;
    color: #9CA3AF;
}

/* ── Combo / date ─────────────────────────────────────────────────── */
QComboBox, QDateEdit {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 14px;
    color: #111827;
    min-height: 28px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox:hover, QDateEdit:hover { border-color: #D1D5DB; }
QDateEdit:disabled { background-color: #F3F4F6; color: #9CA3AF; }

/* ── Checkbox ─────────────────────────────────────────────────────── */
QCheckBox {
    font-size: 14px;
    color: #374151;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1.5px solid #D1D5DB;
    border-radius: 4px;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    background-color: #2563EB;
    border-color: #2563EB;
}
QCheckBox::indicator:hover  { border-color: #2563EB; }
QCheckBox::indicator:disabled {
    background: #F3F4F6;
    border-color: #E5E7EB;
}

/* ── Progress bar (accent blue fill) ─────────────────────────────── */
QProgressBar {
    border: none;
    border-radius: 4px;
    background-color: #E5E7EB;
    max-height: 8px;
    font-size: 0px;
}
QProgressBar::chunk {
    background-color: #2563EB;
    border-radius: 4px;
}

/* ── Tree widget ──────────────────────────────────────────────────── */
QTreeWidget {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    alternate-background-color: #F9FAFB;
    font-size: 13px;
    outline: none;
}
QTreeWidget::item { padding: 3px 2px; }
QTreeWidget::item:selected { background-color: #DBEAFE; color: #1E40AF; }
QTreeWidget::item:hover    { background-color: #F3F4F6; }

/* ── Header ───────────────────────────────────────────────────────── */
QHeaderView::section {
    background-color: #F3F4F6;
    border: none;
    border-bottom: 1px solid #E5E7EB;
    padding: 6px 8px;
    font-size: 12px;
    color: #6B7280;
    font-weight: 600;
}

/* ── List widget ──────────────────────────────────────────────────── */
QListWidget {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    alternate-background-color: #F9FAFB;
    font-size: 13px;
    outline: none;
}
QListWidget::item { padding: 6px 8px; border-bottom: 1px solid #F3F4F6; }
QListWidget::item:hover    { background-color: #F3F4F6; }
QListWidget::item:selected { background-color: #DBEAFE; color: #1E40AF; }

/* ── Group box ────────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 4px;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #374151;
}

/* ── Scroll bars ──────────────────────────────────────────────────── */
QScrollBar:vertical {
    border: none;
    background: #F3F4F6;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #D1D5DB;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #9CA3AF; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    border: none;
    background: #F3F4F6;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #D1D5DB;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #9CA3AF; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Tooltip ──────────────────────────────────────────────────────── */
QToolTip {
    background-color: #1F2937;
    color: #F9FAFB;
    border: none;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
}

/* ── Context menu ─────────────────────────────────────────────────── */
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 16px;
    border-radius: 4px;
    font-size: 13px;
    color: #374151;
}
QMenu::item:selected { background-color: #EFF6FF; color: #2563EB; }

/* ── Dialogs ──────────────────────────────────────────────────────── */
QMessageBox, QInputDialog { background-color: #FFFFFF; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Apply global light theme to the entire application
        QApplication.instance().setStyleSheet(GLOBAL_STYLE)
        self.setWindowTitle("File Organizer + Librarian")
        self.resize(900, 650)

        self._ensure_api_key()

        tabs = QTabWidget()
        tabs.addTab(OrganizerTab(), "Organizer")
        tabs.addTab(LibrarianTab(), "Librarian")
        self.setCentralWidget(tabs)

    def _ensure_api_key(self) -> None:
        if config.get_api_key():
            return
        key, ok = QInputDialog.getText(
            self,
            "Anthropic API Key",
            "Enter your Anthropic API key to use the Organizer:",
            QLineEdit.EchoMode.Password,
        )
        if ok and key.strip():
            config.set_api_key(key.strip())
        else:
            QMessageBox.warning(
                self, "No API Key",
                "The Organizer requires an Anthropic API key. You can still use the Librarian."
            )
