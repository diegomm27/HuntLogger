from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..account_parser import AccountProfile, load_account_profile
from .theme import PALETTE


class _SettingsSection(QGroupBox):
    def __init__(self, title: str, *, columns: int = 1, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self._columns = max(1, columns)
        self._grid = QGridLayout()
        self._grid.setContentsMargins(14, 12, 14, 14)
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(8)
        self.setLayout(self._grid)

    def set_entries(self, data: dict[str, str]) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not data:
            empty = QLabel("-")
            empty.setStyleSheet(f"color: {PALETTE['text_mute']};")
            self._grid.addWidget(empty, 0, 0)
            self._grid.setColumnStretch(0, 1)
            return

        entries = list(data.items())
        rows_per_column = max(1, math.ceil(len(entries) / self._columns))

        for idx, (label, value) in enumerate(entries):
            section_col = idx // rows_per_column
            row = idx % rows_per_column
            key_col = section_col * 2
            value_col = key_col + 1

            key = QLabel(label.upper())
            key.setWordWrap(True)
            key.setStyleSheet(
                f"color: {PALETTE['text_dim']}; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 1px;"
            )

            val = QLabel(str(value))
            val.setWordWrap(True)
            val.setStyleSheet(f"color: {PALETTE['text']};")

            self._grid.addWidget(key, row, key_col)
            self._grid.addWidget(val, row, value_col)

        for section_col in range(self._columns):
            self._grid.setColumnStretch(section_col * 2, 0)
            self._grid.setColumnStretch(section_col * 2 + 1, 1)


class AccountPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile: AccountProfile | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        title = QLabel("INGAME SETTINGS")
        title.setStyleSheet(
            f"color: {PALETTE['gold']}; font-size: 14px; font-weight: bold;"
            f"letter-spacing: 3px; padding: 12px 16px 4px 16px;"
        )
        root.addWidget(title)

        self._overview_widget = self._build_overview_tab()
        root.addWidget(self._overview_widget, 1)

    def _build_overview_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        from PySide6.QtWidgets import QFrame

        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        self._header_label = QLabel("-")
        self._header_label.setStyleSheet(
            f"color: {PALETTE['gold_hi']}; font-size: 16px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(self._header_label)

        sections = QGridLayout()
        sections.setHorizontalSpacing(16)
        sections.setVerticalSpacing(16)
        sections.setColumnStretch(0, 1)
        sections.setColumnStretch(1, 1)

        self._g_info = _SettingsSection("GENERAL", columns=2)
        self._g_graphics = _SettingsSection("GRAPHICS", columns=2)
        self._g_audio = _SettingsSection("AUDIO", columns=1)
        self._g_sens = _SettingsSection("SENSITIVITY", columns=1)
        self._g_keys = _SettingsSection("KEYBINDINGS", columns=3)

        sections.addWidget(self._g_info, 0, 0)
        sections.addWidget(self._g_graphics, 0, 1)
        sections.addWidget(self._g_audio, 1, 0)
        sections.addWidget(self._g_sens, 1, 1)
        sections.addWidget(self._g_keys, 2, 0, 1, 2)

        layout.addLayout(sections)
        layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def reload(self, path: Path) -> None:
        profile = load_account_profile(path)
        if not profile:
            return
        self._profile = profile

        parts = []
        if profile.region:
            parts.append(f"Region: {profile.region.upper()}")
        if profile.last_event:
            parts.append(f"Event: {profile.last_event.replace('_', ' ').title()}")
        self._header_label.setText("  |  ".join(parts) if parts else "HUNT: SHOWDOWN 1896")

        info_data: dict[str, str] = {}
        if profile.region:
            info_data["Region"] = profile.region.upper()
        if profile.last_event:
            info_data["Active Event"] = profile.last_event.replace("_", " ").title()
        for key, value in profile.misc.items():
            info_data[key.replace("_", " ")] = value
        for map_name, duration in profile.map_loading_times.items():
            info_data[f"Load Time {map_name}"] = f"{duration} ms"

        self._g_info.set_entries(info_data)
        self._g_graphics.set_entries(profile.graphics)
        self._g_audio.set_entries(profile.audio)
        self._g_sens.set_entries(profile.sensitivities)
        self._g_keys.set_entries(profile.keybindings)
