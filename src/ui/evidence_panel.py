from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db import Database, HuntSessionSummary
from .theme import PALETTE


def _time(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _item(value: object) -> QTableWidgetItem:
    item = QTableWidgetItem("" if value is None else str(value))
    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    return item


def _duration_text(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


class EvidencePanel(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title = QLabel("MY GAME SESSIONS")
        title.setStyleSheet(
            f"color: {PALETTE['gold']}; font-size: 14px; font-weight: bold;"
            f"letter-spacing: 3px; padding: 12px 16px 4px 16px;"
        )
        root.addWidget(title)

        self.sessions_table = QTableWidget(0, 5)
        self.sessions_table.setHorizontalHeaderLabels(
            ["STARTED", "ENDED", "MAP", "DURATION", "CONFIDENCE"]
        )
        self.sessions_table.setAlternatingRowColors(True)
        self.sessions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sessions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sessions_table.verticalHeader().setVisible(False)
        self.sessions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.sessions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.sessions_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.sessions_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.sessions_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        root.addWidget(self.sessions_table, 1)

    def refresh(self) -> None:
        self._load_sessions(self._db.list_hunt_sessions())

    def _load_sessions(self, sessions: list[HuntSessionSummary]) -> None:
        self.sessions_table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            values = [
                _time(session.started_at),
                _time(session.ended_at),
                session.map_name or "",
                _duration_text(session.duration_seconds),
                session.confidence.upper(),
            ]
            for col, value in enumerate(values):
                self.sessions_table.setItem(row, col, _item(value))
        self.sessions_table.resizeRowsToContents()
