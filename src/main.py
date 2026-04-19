from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName("HuntLogger")
    app.setOrganizationName("HuntLogger")
    app.setFont(QFont("Segoe UI", 10))
    apply_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
