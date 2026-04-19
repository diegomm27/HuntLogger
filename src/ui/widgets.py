from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class SectionLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setProperty("class", "section")
        # QSS selectors need explicit class via style-class
        self.setObjectName("section")
        self.setStyleSheet("")
        self.setAttribute(Qt.WA_StyledBackground, True)


def _apply_class(w: QWidget, cls: str) -> None:
    w.setProperty("class", cls)
    w.setAttribute(Qt.WA_StyledBackground, True)
    w.style().unpolish(w)
    w.style().polish(w)


class KpiCard(QFrame):
    """A small card showing a numeric KPI with a label."""

    def __init__(
        self,
        label: str,
        value: str = "-",
        tone: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        _apply_class(self, "card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        self._label = QLabel(label.upper())
        self._label.setProperty("class", "kpi_label")
        self._label.style().unpolish(self._label)
        self._label.style().polish(self._label)
        self._value = QLabel(value)
        self._value.setProperty("class", "kpi_value")
        if tone:
            self._value.setProperty("tone", tone)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
        layout.addWidget(self._label)
        layout.addWidget(self._value)

    def set_value(self, value: str, tone: str = "") -> None:
        self._value.setText(value)
        self._value.setProperty("tone", tone)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)


class HLine(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Plain)
        self.setStyleSheet("color: #3a2a1c; background: #3a2a1c; border: none;")
        self.setFixedHeight(1)
