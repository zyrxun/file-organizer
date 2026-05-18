import sys
import os

# Ensure file-organizer root is on the path when running directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from gui.app import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("File Organizer + Librarian")
    app.setOrganizationName("FileOrganizer")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
