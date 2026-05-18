import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QMessageBox, QInputDialog,
    QLineEdit,
)

import config
from gui.organizer_tab import OrganizerTab
from gui.librarian_tab import LibrarianTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
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
