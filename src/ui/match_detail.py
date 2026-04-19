from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QStackedLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db import Database
from .theme import DISPLAY_FONT, PALETTE

# ── result-tinted colours (mirrors match_list.py) ───────────────────────────
_WIN_BG  = "#0f1a0d"
_WIN_BAR = "#5a9142"
_WIN_TXT = "#8cc968"

_LOSS_BG  = "#180c08"
_LOSS_BAR = "#a12d1b"
_LOSS_TXT = "#d04a36"


# ── small helpers ─────────────────────────────────────────────────────────────

def _mono_font() -> QFont:
    f = QFont("Consolas")
    f.setStyleHint(QFont.Monospace)
    f.setPointSize(9)
    return f


def _lbl(text: str, style: str) -> QLabel:
    """Label that is transparent so it doesn't cover its parent's background."""
    w = QLabel(text)
    w.setStyleSheet(f"background: transparent; {style}")
    return w


def _vsep() -> QFrame:
    s = QFrame()
    s.setFrameShape(QFrame.VLine)
    s.setFixedWidth(1)
    s.setStyleSheet(f"background: {PALETTE['border']}; border: none; color: {PALETTE['border']};")
    return s


# ── _StatChip ─────────────────────────────────────────────────────────────────

class _StatChip(QWidget):
    """Vertical value-over-label chip, op.gg style."""

    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 8, 14, 8)
        v.setSpacing(3)
        v.setAlignment(Qt.AlignCenter)

        self._val = _lbl(value,
            f"color: {PALETTE['gold_hi']}; font-family: {DISPLAY_FONT};"
            f" font-size: 20px; font-weight: bold;")
        self._val.setAlignment(Qt.AlignCenter)

        self._lbl = _lbl(label.upper(),
            f"color: {PALETTE['text_mute']}; font-size: 8px;"
            f" font-weight: bold; letter-spacing: 3px;")
        self._lbl.setAlignment(Qt.AlignCenter)

        v.addWidget(self._val)
        v.addWidget(self._lbl)

    def set_value(self, value: str, tone: str = "") -> None:
        self._val.setText(value)
        colour = {
            "good": PALETTE["green"],
            "bad":  PALETTE["blood_hi"],
        }.get(tone, PALETTE["gold_hi"])
        self._val.setStyleSheet(
            f"background: transparent; color: {colour}; font-family: {DISPLAY_FONT};"
            f" font-size: 20px; font-weight: bold;"
        )

    def reset(self) -> None:
        self.set_value("—")


# ── _ResultBanner ─────────────────────────────────────────────────────────────

class _ResultBanner(QFrame):
    """Coloured header strip: thick left bar + SURVIVED/DIED + match info."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(58)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 20, 0)
        outer.setSpacing(0)

        self._bar = QFrame()
        self._bar.setFixedWidth(5)
        outer.addWidget(self._bar)

        outer.addSpacing(18)

        self._result_lbl = _lbl(
            "",
            f"font-family: {DISPLAY_FONT}; font-size: 24px; font-weight: bold; letter-spacing: 4px;",
        )
        outer.addWidget(self._result_lbl)

        outer.addSpacing(16)

        self._info_lbl = _lbl("",
            f"font-size: 11px; color: {PALETTE['text_dim']};")
        outer.addWidget(self._info_lbl)

        outer.addStretch(1)

        self._ts_lbl = _lbl("",
            f"font-size: 9px; color: {PALETTE['text_mute']}; letter-spacing: 1px;")
        outer.addWidget(self._ts_lbl)

    def set_result(self, survived: bool, match_id: int, ts: datetime) -> None:
        bg  = _WIN_BG   if survived else _LOSS_BG
        bar = _WIN_BAR  if survived else _LOSS_BAR
        txt = _WIN_TXT  if survived else _LOSS_TXT
        res = "SURVIVED" if survived else "DIED"

        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-bottom: 1px solid {PALETTE['border']}; }}"
        )
        self._bar.setStyleSheet(f"background: {bar}; border: none;")
        self._result_lbl.setStyleSheet(
            f"background: transparent; color: {txt}; font-family: {DISPLAY_FONT};"
            f" font-size: 24px; font-weight: bold; letter-spacing: 4px;"
        )
        self._result_lbl.setText(res)
        self._info_lbl.setText(f"MATCH #{match_id}")
        self._ts_lbl.setText(ts.strftime("%A, %d %B %Y — %H:%M:%S").upper())

    def clear(self) -> None:
        self.setStyleSheet(
            f"QFrame {{ background-color: {PALETTE['panel']};"
            f" border-bottom: 1px solid {PALETTE['border']}; }}"
        )
        self._bar.setStyleSheet(f"background: {PALETTE['border']}; border: none;")
        self._result_lbl.setText("")
        self._info_lbl.setText("")
        self._ts_lbl.setText("")


# ── _StatsBar ─────────────────────────────────────────────────────────────────

class _StatsBar(QFrame):
    """Horizontal row of stat chips separated by vertical rules."""

    def __init__(self, chips: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background-color: {PALETTE['panel_alt']};"
            f" border-bottom: 1px solid {PALETTE['border']}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(0)

        self._chips: dict[str, _StatChip] = {}
        for i, (key, label) in enumerate(chips):
            if i:
                row.addWidget(_vsep())
            chip = _StatChip(label)
            self._chips[key] = chip
            row.addWidget(chip, 1)

    def set(self, key: str, value: str, tone: str = "") -> None:
        if key in self._chips:
            self._chips[key].set_value(value, tone)

    def reset_all(self) -> None:
        for c in self._chips.values():
            c.reset()


# ── _OverviewTab ──────────────────────────────────────────────────────────────

class _OverviewTab(QWidget):

    _STAT_CHIPS = [
        ("result",  "RESULT"),
        ("kd",      "K / D"),
        ("bounty",  "BOUNTY"),
        ("xp",      "HUNTER XP"),
        ("gold",    "GOLD"),
        ("mmr",     "TEAM MMR"),
    ]

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._banner = _ResultBanner()
        outer.addWidget(self._banner)

        self._stats = _StatsBar(self._STAT_CHIPS)
        self._stats.setFixedHeight(72)
        outer.addWidget(self._stats)

        teams_hdr = QLabel("TEAMS")
        teams_hdr.setStyleSheet(
            f"background-color: {PALETTE['bg_alt']};"
            f" color: {PALETTE['gold']}; font-size: 10px; font-weight: bold;"
            f" letter-spacing: 3px; padding: 8px 18px 6px;"
            f" border-bottom: 1px solid {PALETTE['border']};"
        )
        outer.addWidget(teams_hdr)

        self.teams_tree = QTreeWidget()
        self.teams_tree.setHeaderLabels(["TEAM / HUNTER", "MMR", "K/D ON ME", "BOUNTY", "FLAGS"])
        self.teams_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.teams_tree.setAlternatingRowColors(True)
        self.teams_tree.setIndentation(16)
        outer.addWidget(self.teams_tree, 1)

    def clear(self) -> None:
        self._banner.clear()
        self._stats.reset_all()
        self.teams_tree.clear()

    def load(self, match_id: int) -> None:
        header = self._db.get_match_header(match_id)
        if not header:
            self.clear()
            return

        ts       = datetime.fromisoformat(header["timestamp"])
        survived = not bool(header["is_hunter_dead"])

        self._banner.set_result(survived, match_id, ts)

        self._stats.set("result",
            "SURVIVED" if survived else "DIED",
            tone="good" if survived else "bad")
        self._stats.set("kd",     f"{header['total_kills']} / {header['total_deaths']}")
        self._stats.set("bounty", str(header["total_bounty"]  or 0))
        self._stats.set("xp",     str(header["total_hunter_xp"] or 0))
        self._stats.set("gold",   str(header["total_gold"]    or 0))
        self._stats.set("mmr",    str(header["own_team_mmr"]  or "—"))

        self._populate_teams(match_id)

    def _populate_teams(self, match_id: int) -> None:
        self.teams_tree.clear()
        teams   = self._db.get_match_teams(match_id)
        players = self._db.get_match_players(match_id)
        by_team: dict[int, list[dict]] = {}
        for p in players:
            by_team.setdefault(p["team_idx"], []).append(p)

        for t in teams:
            own   = bool(t["is_own_team"])
            label = f"TEAM {t['team_idx']}" + ("  ·  YOUR TEAM" if own else "")
            flags = []
            if t["handicap"]:  flags.append(f"handicap={t['handicap']}")
            if t["prestige"]:  flags.append(f"prestige={t['prestige']}")
            if t["is_invite"]: flags.append("invite")

            team_item = QTreeWidgetItem([label, str(t["mmr"] or "—"), "", "", "  ·  ".join(flags)])
            font = team_item.font(0)
            font.setBold(True)
            team_item.setFont(0, font)
            if own:
                team_item.setForeground(0, Qt.GlobalColor.yellow)
            self.teams_tree.addTopLevelItem(team_item)

            for pl in by_team.get(t["team_idx"], []):
                pf = []
                if pl["had_bounty"]:      pf.append("bounty")
                if pl["is_partner"]:      pf.append("partner")
                if pl["team_extraction"]: pf.append("extracted")
                if pl["is_soul_survivor"]:pf.append("soul-survivor")
                if pl["proximity_to_me"]: pf.append("near-me")
                kd_on_me = f"{pl['killed_by_me'] + pl['downed_by_me']} / {pl['killed_me'] + pl['downed_me']}"
                child = QTreeWidgetItem([
                    f"  {pl['name'] or '(unknown)'}",
                    str(pl["mmr"] or "—"),
                    kd_on_me,
                    str(pl["bounty_picked_up"] or 0),
                    "  ·  ".join(pf),
                ])
                team_item.addChild(child)
            team_item.setExpanded(True)


# ── _PlayersTab ───────────────────────────────────────────────────────────────

class _PlayersTab(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["TEAM", "NAME", "PROFILE ID", "MMR",
             "K BY ME", "D BY ME", "K ON ME", "D ON ME", "BOUNTY", "FLAGS"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def clear(self) -> None:
        self.table.setRowCount(0)

    def load(self, match_id: int) -> None:
        players = self._db.get_match_players(match_id)
        self.table.setRowCount(len(players))
        for i, pl in enumerate(players):
            flags = []
            if pl["is_partner"]:      flags.append("partner")
            if pl["had_bounty"]:      flags.append("bounty")
            if pl["team_extraction"]: flags.append("extracted")
            if pl["is_soul_survivor"]:flags.append("soul-survivor")
            cells = [
                str(pl["team_idx"]),
                pl["name"] or "(unknown)",
                pl["profile_id"] or "",
                str(pl["mmr"] or ""),
                str(pl["killed_by_me"]),
                str(pl["downed_by_me"]),
                str(pl["killed_me"]),
                str(pl["downed_me"]),
                str(pl["bounty_picked_up"]),
                "  ·  ".join(flags),
            ]
            for j, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()


# ── _AccoladesTab ─────────────────────────────────────────────────────────────

class _AccoladesTab(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["#", "CATEGORY", "TITLE", "BOUNTY", "GOLD", "XP", "HUNTER XP", "HITS"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def clear(self) -> None:
        self.table.setRowCount(0)

    def load(self, match_id: int) -> None:
        accolades = self._db.get_match_accolades(match_id)
        self.table.setRowCount(len(accolades))
        for i, a in enumerate(accolades):
            cells = [
                str(a["idx"]), a["category"] or "", a["title"] or "",
                str(a["bounty"] or 0), str(a["gold"] or 0),
                str(a["xp"] or 0), str(a["hunter_xp"] or 0), str(a["hits"] or 0),
            ]
            for j, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()


# ── _EntriesTab ───────────────────────────────────────────────────────────────

class _EntriesTab(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "CATEGORY", "AMOUNT", "REWARD", "UI NAME", "DESCRIPTOR"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def clear(self) -> None:
        self.table.setRowCount(0)

    def load(self, match_id: int) -> None:
        entries = self._db.get_match_entries(match_id)
        self.table.setRowCount(len(entries))
        for i, e in enumerate(entries):
            cells = [
                str(e["idx"]), e["category"] or "",
                str(e["amount"] or 0), str(e["reward"] or 0),
                e["ui_name"] or "", e["descriptor_name"] or "",
            ]
            for j, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()


# ── _RawTab ───────────────────────────────────────────────────────────────────

class _RawTab(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()

        self.attrs_view = QPlainTextEdit()
        self.attrs_view.setReadOnly(True)
        self.attrs_view.setFont(_mono_font())

        self.xml_view = QPlainTextEdit()
        self.xml_view.setReadOnly(True)
        self.xml_view.setFont(_mono_font())

        self.tabs.addTab(self.attrs_view, "PARSED ATTRS")
        self.tabs.addTab(self.xml_view,   "RAW XML")
        layout.addWidget(self.tabs)

    def clear(self) -> None:
        self.attrs_view.setPlainText("")
        self.xml_view.setPlainText("")

    def load(self, match_id: int) -> None:
        raw = self._db.get_match_raw(match_id)
        if not raw:
            self.clear()
            return
        lines = [f"{k} = {v}" for k, v in sorted(raw["raw_attrs"].items())]
        self.attrs_view.setPlainText("\n".join(lines))
        self.xml_view.setPlainText(raw["raw_xml"] or "")


# ── _VisualMatchWidget ────────────────────────────────────────────────────────

class _VisualMatchWidget(QWidget):

    _STAT_CHIPS = [
        ("bounty",   "BOUNTY"),
        ("hunters",  "HUNTERS KILLED"),
        ("monsters", "MONSTERS"),
        ("token",    "BOUNTY TOKEN"),
        ("status",   "STATUS"),
        ("xp",       "BLOODLINE XP"),
    ]

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._banner = _ResultBanner()
        outer.addWidget(self._banner)

        self._stats = _StatsBar(self._STAT_CHIPS)
        self._stats.setFixedHeight(72)
        outer.addWidget(self._stats)

        outer.addStretch(1)

    def load(self, group_path: str) -> None:
        detail = self._db.get_visual_match_detail(group_path)
        if not detail:
            self._banner.clear()
            self._stats.reset_all()
            return

        started     = detail["started_at"]
        ended       = detail["ended_at"]
        frame_count = detail["frame_count"]
        parsed      = detail.get("parsed_fields", {})
        is_dead     = parsed.get("hunter_status", "") == "dead"
        survived    = not is_dead

        self._banner.setStyleSheet(
            f"QFrame {{ background-color: {_WIN_BG if survived else _LOSS_BG};"
            f" border-bottom: 1px solid {PALETTE['border']}; }}"
        )
        self._banner._bar.setStyleSheet(
            f"background: {_WIN_BAR if survived else _LOSS_BAR}; border: none;"
        )
        txt = _WIN_TXT if survived else _LOSS_TXT
        self._banner._result_lbl.setStyleSheet(
            f"background: transparent; color: {txt}; font-family: {DISPLAY_FONT};"
            f" font-size: 24px; font-weight: bold; letter-spacing: 4px;"
        )
        self._banner._result_lbl.setText("SURVIVED" if survived else "DIED")
        self._banner._info_lbl.setText(
            f"{frame_count} frames  ·  {started.strftime('%Y-%m-%d %H:%M:%S')}"
            f" → {ended.strftime('%H:%M:%S')}"
        )
        self._banner._ts_lbl.setText("")

        self._stats.reset_all()
        if parsed:
            self._stats.set("bounty",   parsed.get("bounty_obtained_value", "?"))
            self._stats.set("hunters",  parsed.get("hunters_killed_value",  "?"))
            self._stats.set("monsters", parsed.get("monsters_killed_value", "?"))
            self._stats.set("token",    parsed.get("bounty_token_value",    "?"))
            self._stats.set("status",   parsed.get("hunter_status",         "?"),
                            tone="bad" if is_dead else "good")
            self._stats.set("xp",       parsed.get("bloodline_xp",          "?"))


# ── _Placeholder ─────────────────────────────────────────────────────────────

class _Placeholder(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        title = QLabel("NO MATCH RECORDED YET")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {PALETTE['gold']}; font-family: {DISPLAY_FONT};"
            f" font-size: 22px; letter-spacing: 5px; font-weight: bold;"
        )
        sub = QLabel(
            "Complete a match in Hunt: Showdown 1896 and the results will be logged here automatically."
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {PALETTE['text_dim']}; font-style: italic;")
        hint = QLabel(
            "IMPORTANT: Keep this app open while Hunt is running.\n"
            "Match data is written to attributes.xml on the post-match screen\n"
            "and is overwritten when the game closes — the logger must catch it live.\n\n"
            "Status bar must show READY."
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {PALETTE['text_mute']}; font-size: 10px; line-height: 1.5;")
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addWidget(hint)


# ── MatchDetailWidget ─────────────────────────────────────────────────────────

class MatchDetailWidget(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedLayout()
        layout.addLayout(self._stack)

        self._placeholder = _Placeholder()
        self._tabs        = QTabWidget()
        self._overview    = _OverviewTab(db)
        self._players     = _PlayersTab(db)
        self._accolades   = _AccoladesTab(db)
        self._entries     = _EntriesTab(db)
        self._raw         = _RawTab(db)
        self._visual      = _VisualMatchWidget(db)

        self._tabs.addTab(self._overview,  "OVERVIEW")
        self._tabs.addTab(self._players,   "HUNTERS")
        self._tabs.addTab(self._accolades, "ACCOLADES")
        self._tabs.addTab(self._entries,   "EVENTS")
        self._tabs.addTab(self._raw,       "RAW")

        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._tabs)
        self._stack.addWidget(self._visual)
        self._stack.setCurrentIndex(0)

    def show_match(self, match_id: object | None) -> None:
        if match_id is None:
            self._stack.setCurrentIndex(0)
            return
        key = str(match_id)
        if key.startswith("visual:"):
            self._visual.load(key[len("visual:"):])
            self._stack.setCurrentIndex(2)
            return
        if key.startswith("exact:"):
            match_id = int(key.split(":", 1)[1])
        self._overview.load(match_id)    # type: ignore[arg-type]
        self._players.load(match_id)     # type: ignore[arg-type]
        self._accolades.load(match_id)   # type: ignore[arg-type]
        self._entries.load(match_id)     # type: ignore[arg-type]
        self._raw.load(match_id)         # type: ignore[arg-type]
        self._stack.setCurrentIndex(1)

    def clear(self) -> None:
        self._overview.clear()
        self._players.clear()
        self._accolades.clear()
        self._entries.clear()
        self._raw.clear()
        self._stack.setCurrentIndex(0)
