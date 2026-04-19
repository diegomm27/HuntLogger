from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..db import Database, DisplayMatchSummary
from .theme import PALETTE

# ── Per-result palette ────────────────────────────────────────────────────────

_WIN_BG     = "#0f1a0d"
_WIN_BG_HOV = "#162414"
_WIN_BG_SEL = "#1d2f1b"
_WIN_BAR    = "#5a9142"
_WIN_TEXT   = "#8cc968"

_LOSS_BG     = "#180c08"
_LOSS_BG_HOV = "#22110c"
_LOSS_BG_SEL = "#2d1810"
_LOSS_BAR    = "#a12d1b"
_LOSS_TEXT   = "#d04a36"

_CARD_H = 72   # px
_RECENT_MATCH_LIMIT = 20


@dataclass(frozen=True)
class _MatchStats:
    matches: int
    extractions: int
    deaths: int
    kills: int
    combat_deaths: int
    avg_kills: float
    kda: float
    extraction_rate: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_ago(dt: datetime) -> str:
    s = int((datetime.now() - dt).total_seconds())
    if s < 60:   return f"{s}s ago"
    m = s // 60
    if m < 60:   return f"{m}m ago"
    h = m // 60
    if h < 24:   return f"{h}h ago"
    return f"{h // 24}d ago"


def _fnt(size: int, bold: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def _combat_deaths(match: DisplayMatchSummary) -> int:
    return max(0, match.total_deaths, 1 if match.is_hunter_dead else 0)


def _stats_for(matches: list[DisplayMatchSummary]) -> _MatchStats:
    count = len(matches)
    if count == 0:
        return _MatchStats(0, 0, 0, 0, 0, 0.0, 0.0, 0.0)

    deaths = sum(1 for m in matches if m.is_hunter_dead)
    extractions = count - deaths
    kills = sum(max(0, m.total_kills) for m in matches)
    combat_deaths = sum(_combat_deaths(m) for m in matches)
    return _MatchStats(
        matches=count,
        extractions=extractions,
        deaths=deaths,
        kills=kills,
        combat_deaths=combat_deaths,
        avg_kills=kills / count,
        kda=kills / max(1, combat_deaths),
        extraction_rate=extractions / count,
    )


def _fmt_decimal(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def _fmt_percent(value: float) -> str:
    return f"{round(value * 100):.0f}%"


def _label_stylesheet(color: str, size: int, *, bold: bool = False) -> str:
    weight = "font-weight: bold;" if bold else ""
    return f"color: {color}; font-size: {size}px; {weight}"


def _value_tone(value: float, good_at: float) -> str:
    return PALETTE["green"] if value >= good_at else PALETTE["gold_hi"]


class _MetricTile(QFrame):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MetricTile")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(52)
        self.setStyleSheet(
            f"QFrame#MetricTile {{ background-color: {PALETTE['panel_alt']};"
            f" border: 1px solid {PALETTE['border']}; border-radius: 0; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(2)

        self._value = QLabel("-")
        self._value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._value.setStyleSheet(_label_stylesheet(PALETTE["gold_hi"], 18, bold=True))

        self._label = QLabel(label.upper())
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(_label_stylesheet(PALETTE["text_dim"], 9, bold=True))

        layout.addWidget(self._value)
        layout.addWidget(self._label)

    def set_value(self, value: str, color: str | None = None) -> None:
        self._value.setText(value)
        self._value.setStyleSheet(
            _label_stylesheet(color or PALETTE["gold_hi"], 18, bold=True)
        )


class _ExtractionPie(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._extractions = 0
        self._deaths = 0
        self.setMinimumSize(104, 104)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_values(self, extractions: int, deaths: int) -> None:
        self._extractions = max(0, extractions)
        self._deaths = max(0, deaths)
        self.update()

    def paintEvent(self, _: object) -> None:
        total = self._extractions + self._deaths
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        size = min(self.width(), self.height()) - 8
        rect = QRectF(
            (self.width() - size) / 2,
            (self.height() - size) / 2,
            size,
            size,
        )

        p.setPen(QPen(QColor(PALETTE["border_hi"]), 1))
        p.setBrush(QColor(PALETTE["panel_hi"]))
        p.drawEllipse(rect)

        if total > 0:
            start = 90 * 16
            extraction_span = -round(360 * 16 * (self._extractions / total))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PALETTE["green_dim"]))
            p.drawPie(rect, start, extraction_span)

            p.setBrush(QColor(PALETTE["blood"]))
            p.drawPie(rect, start + extraction_span, -360 * 16 - extraction_span)

        inner = rect.adjusted(size * 0.22, size * 0.22, -size * 0.22, -size * 0.22)
        p.setPen(QPen(QColor(PALETTE["border"]), 1))
        p.setBrush(QColor(PALETTE["panel"]))
        p.drawEllipse(inner)

        p.setFont(_fnt(17, bold=True))
        p.setPen(QColor(PALETTE["gold_hi"]))
        p.drawText(inner, Qt.AlignCenter, str(total))
        p.end()


class _RecentSummaryPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RecentSummaryPanel")
        self.setFixedHeight(176)
        self.setStyleSheet(
            f"QFrame#RecentSummaryPanel {{ background-color: {PALETTE['panel']};"
            f" border-bottom: 1px solid {PALETTE['border_hi']}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._title = QLabel("RECENT HUNTS")
        self._title.setStyleSheet(_label_stylesheet(PALETTE["gold"], 13, bold=True))
        self._scope = QLabel("LAST 0")
        self._scope.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._scope.setStyleSheet(_label_stylesheet(PALETTE["text_mute"], 9, bold=True))
        head.addWidget(self._title)
        head.addStretch(1)
        head.addWidget(self._scope)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(14)
        self._pie = _ExtractionPie()
        body.addWidget(self._pie)

        legend = QVBoxLayout()
        legend.setSpacing(5)
        self._extract_label = QLabel("0 EXTRACTIONS")
        self._extract_label.setStyleSheet(_label_stylesheet(PALETTE["green"], 10, bold=True))
        self._death_label = QLabel("0 DEATHS")
        self._death_label.setStyleSheet(_label_stylesheet(PALETTE["blood_hi"], 10, bold=True))
        self._rate_label = QLabel("0% EXTRACTION RATE")
        self._rate_label.setWordWrap(True)
        self._rate_label.setStyleSheet(_label_stylesheet(PALETTE["text_dim"], 9))
        legend.addStretch(1)
        legend.addWidget(self._extract_label)
        legend.addWidget(self._death_label)
        legend.addWidget(self._rate_label)
        legend.addStretch(1)
        body.addLayout(legend)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self._avg_kills = _MetricTile("Average Kills")
        self._kda = _MetricTile("KDA")
        self._games = _MetricTile("Games")
        grid.addWidget(self._avg_kills, 0, 0)
        grid.addWidget(self._kda, 0, 1)
        grid.addWidget(self._games, 1, 0, 1, 2)
        body.addLayout(grid, 1)
        root.addLayout(body, 1)

    def set_stats(self, stats: _MatchStats, displayed: int) -> None:
        self._scope.setText(f"LAST {displayed}")
        self._pie.set_values(stats.extractions, stats.deaths)
        self._extract_label.setText(f"{stats.extractions} EXTRACTIONS")
        self._death_label.setText(f"{stats.deaths} DEATHS")
        self._rate_label.setText(f"{_fmt_percent(stats.extraction_rate)} EXTRACTION RATE")
        self._avg_kills.set_value(_fmt_decimal(stats.avg_kills, 1))
        self._kda.set_value(_fmt_decimal(stats.kda, 2), _value_tone(stats.kda, 1.0))
        self._games.set_value(str(stats.matches))


class _AccountSummaryPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AccountSummaryPanel")
        self.setFixedWidth(178)
        self.setStyleSheet(
            f"QFrame#AccountSummaryPanel {{ background-color: {PALETTE['bg_alt']};"
            f" border-right: 1px solid {PALETTE['border_hi']}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("ACCOUNT")
        title.setStyleSheet(_label_stylesheet(PALETTE["gold"], 13, bold=True))
        root.addWidget(title)

        self._games = _MetricTile("Games Played")
        self._kda = _MetricTile("KDA")
        self._extraction = _MetricTile("Extraction")
        self._avg_kills = _MetricTile("Average Kills")

        root.addWidget(self._games)
        root.addWidget(self._kda)
        root.addWidget(self._extraction)
        root.addWidget(self._avg_kills)

        root.addStretch(1)

    def set_stats(self, stats: _MatchStats) -> None:
        self._games.set_value(str(stats.matches))
        self._kda.set_value(_fmt_decimal(stats.kda, 2), _value_tone(stats.kda, 1.0))
        self._extraction.set_value(
            _fmt_percent(stats.extraction_rate),
            _value_tone(stats.extraction_rate, 0.5),
        )
        self._avg_kills.set_value(_fmt_decimal(stats.avg_kills, 1))


# ── Card widget (pure QPainter – zero stylesheet/inheritance conflicts) ────────

class _MatchCard(QWidget):
    clicked: Signal = Signal(object)

    def __init__(self, match: DisplayMatchSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._m = match
        self._hovered = False
        self._selected = False
        self.setFixedHeight(_CARD_H)
        self.setAttribute(Qt.WA_Hover)
        self.setCursor(Qt.PointingHandCursor)

    # ── state ─────────────────────────────────────────────────────────────────

    def set_selected(self, v: bool) -> None:
        self._selected = v
        self.update()

    def event(self, e: object) -> bool:
        t = e.type()  # type: ignore[attr-defined]
        if t == QEvent.HoverEnter:
            self._hovered = True
            self.update()
        elif t == QEvent.HoverLeave:
            self._hovered = False
            self.update()
        return super().event(e)  # type: ignore[arg-type]

    def mousePressEvent(self, e: object) -> None:
        if e.button() == Qt.LeftButton:  # type: ignore[attr-defined]
            self.clicked.emit(self._m.id)
        super().mousePressEvent(e)  # type: ignore[arg-type]

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _: object) -> None:
        m = self._m
        survived = not m.is_hunter_dead
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)

        W, H = self.width(), self.height()

        # ── background ───────────────────────────────────────────────────────
        if self._selected:
            bg = _WIN_BG_SEL if survived else _LOSS_BG_SEL
        elif self._hovered:
            bg = _WIN_BG_HOV if survived else _LOSS_BG_HOV
        else:
            bg = _WIN_BG if survived else _LOSS_BG

        p.fillRect(0, 0, W, H, QColor(bg))
        p.fillRect(0, H - 1, W, 1, QColor(PALETTE["border"]))   # bottom rule
        p.fillRect(0, 0, 5, H, QColor(_WIN_BAR if survived else _LOSS_BAR))  # left bar

        # ── colour helpers ───────────────────────────────────────────────────
        c_result = QColor(_WIN_TEXT if survived else _LOSS_TEXT)
        c_text   = QColor(PALETTE["text"])
        c_dim    = QColor(PALETTE["text_dim"])
        c_mute   = QColor(PALETTE["text_mute"])
        c_gold   = QColor(PALETTE["gold_hi"])
        c_death  = QColor(_LOSS_TEXT)
        c_sep    = QColor(PALETTE["border"])

        PAD = 14          # horizontal padding after bar
        x   = 5 + PAD

        # vertical baselines for two-line layout
        f_big   = _fnt(10, bold=True, spacing=0.5)
        f_small = _fnt(7,  bold=False, spacing=1.0)
        asc_big   = QFontMetrics(f_big).ascent()
        asc_small = QFontMetrics(f_small).ascent()
        y1 = H // 2 - asc_big - 1        # top line baseline
        y2 = H // 2 + asc_small + 3      # bottom line baseline

        # ── col 1 · Result + source tag (84 px) ──────────────────────────────
        result_text = ("SURVIVED" if survived else "DIED") if m.source == "exact" else ("ALIVE" if survived else "DIED")
        src_text    = "EXACT" if m.source == "exact" else "SCREENSHOT"

        p.setFont(f_big);   p.setPen(c_result)
        p.drawText(x, y1 + asc_big, result_text)

        p.setFont(f_small); p.setPen(c_mute)
        p.drawText(x, y2 + asc_small, src_text)

        COL1_W = 84
        sep_x = x + COL1_W + 6
        p.fillRect(sep_x, 12, 1, H - 24, c_sep)
        x = sep_x + 1 + 12

        # ── col 2 · K / D (88 px) ────────────────────────────────────────────
        if m.source == "visual" and m.parsed_fields:
            k_str = m.parsed_fields.get("hunters_killed_value", "?")
            d_str = "—"
        else:
            k_str = str(m.total_kills)
            d_str = str(m.total_deaths)

        f_kd      = _fnt(15, bold=True)
        f_kd_lbl  = _fnt(7,  bold=False, spacing=1.5)
        fm_kd     = QFontMetrics(f_kd)
        fm_kd_lbl = QFontMetrics(f_kd_lbl)

        slash = " / "
        kw = fm_kd.horizontalAdvance(k_str)
        sw = fm_kd.horizontalAdvance(slash)
        dw = fm_kd.horizontalAdvance(d_str)
        COL2_W  = 88
        kd_x    = x + max(0, (COL2_W - kw - sw - dw) // 2)
        kd_y    = H // 2 + fm_kd.ascent() // 2 - 4

        p.setFont(f_kd)
        p.setPen(c_text);  p.drawText(kd_x,      kd_y, k_str)
        p.setPen(c_mute);  p.drawText(kd_x + kw, kd_y, slash)
        p.setPen(c_death); p.drawText(kd_x + kw + sw, kd_y, d_str)

        lbl_str = "K  /  D"
        lbl_w   = fm_kd_lbl.horizontalAdvance(lbl_str)
        p.setFont(f_kd_lbl); p.setPen(c_mute)
        p.drawText(x + max(0, (COL2_W - lbl_w) // 2),
                   kd_y + fm_kd_lbl.ascent() + 4, lbl_str)

        sep_x = x + COL2_W + 6
        p.fillRect(sep_x, 12, 1, H - 24, c_sep)
        x = sep_x + 1 + 12

        # ── col 3 · stat chips (flexible) ────────────────────────────────────
        f_sv  = _fnt(10, bold=True)
        f_sl  = _fnt(7,  bold=False, spacing=0.8)
        fm_sv = QFontMetrics(f_sv)
        fm_sl = QFontMetrics(f_sl)

        TIME_W = 96
        sx = x  # stats start x
        stats_end_x = W - PAD - TIME_W - 10

        if m.source == "visual" and m.parsed_fields:
            pf = m.parsed_fields
            chips = [
                (pf.get("bounty_obtained_value", "?"), "BOUNTY"),
                (pf.get("monsters_killed_value", "?"), "MONSTERS"),
                (pf.get("bounty_token_value", "?"),    "BOUNTY TOKEN"),
                (pf.get("bloodline_xp", "?"),          "BLOODLINE XP"),
            ]
        elif m.source == "visual":
            p.setFont(f_sl); p.setPen(c_mute)
            p.drawText(sx, H // 2 + fm_sl.ascent() // 2,
                       f"{m.frame_count} frames captured · parser pending")
            chips = []
        else:
            bounty = f"+{m.total_bounty}"   if m.total_bounty    else "0"
            xp_v   = f"+{m.total_hunter_xp}" if m.total_hunter_xp else "0"
            gold   = f"+{m.total_gold}" if m.total_gold else "0"
            mmr    = str(m.own_team_mmr) if m.own_team_mmr else "-"
            chips  = [
                (bounty, "BOUNTY"),
                (xp_v, "HUNTER XP"),
                (gold, "GOLD"),
                (mmr, "MMR"),
            ]

        for val, lbl in chips:
            if sx > stats_end_x - 30:
                break
            vw    = fm_sv.horizontalAdvance(val)
            lw    = fm_sl.horizontalAdvance(lbl)
            chip_w = max(vw, lw) + 14

            p.setFont(f_sv); p.setPen(c_gold)
            p.drawText(sx + (chip_w - vw) // 2, y1 + fm_sv.ascent(), val)

            p.setFont(f_sl); p.setPen(c_mute)
            p.drawText(sx + (chip_w - lw) // 2, y2 + fm_sl.ascent(), lbl)

            sx += chip_w

        # ── col 4 · time (right-aligned) ─────────────────────────────────────
        f_ago  = _fnt(9,  bold=True)
        f_date = _fnt(7,  bold=False)
        fm_ago  = QFontMetrics(f_ago)
        fm_date = QFontMetrics(f_date)

        ago_str  = _fmt_ago(m.timestamp)
        date_str = m.timestamp.strftime("%Y-%m-%d")

        ago_x  = W - PAD - fm_ago.horizontalAdvance(ago_str)
        date_x = W - PAD - fm_date.horizontalAdvance(date_str)

        p.setFont(f_ago);  p.setPen(c_dim)
        p.drawText(ago_x, y1 + fm_ago.ascent(), ago_str)

        p.setFont(f_date); p.setPen(c_mute)
        p.drawText(date_x, y2 + fm_date.ascent(), date_str)

        p.end()


# ── List widget ───────────────────────────────────────────────────────────────

class _MatchListView(QListWidget):
    match_selected: Signal = Signal(object)
    delete_requested: Signal = Signal(object)

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        # suppress the built-in selection highlight – cards paint their own
        self.setStyleSheet("""
            QListWidget {
                border: none;
                background: transparent;
                outline: none;
            }
            QListWidget::item { background: transparent; border: none; padding: 0; }
            QListWidget::item:selected { background: transparent; }
        """)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.currentItemChanged.connect(self._on_item_changed)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ── public API (unchanged from original) ─────────────────────────────────

    def refresh(self, preserve_selection: bool = True) -> None:
        self.set_matches(
            self._db.list_display_matches(limit=1000),
            preserve_selection=preserve_selection,
        )

    def set_matches(
        self,
        matches: list[DisplayMatchSummary],
        *,
        preserve_selection: bool = True,
    ) -> None:
        prev_id = self.current_match_id() if preserve_selection else None
        self.clear()
        for match in matches:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, match.id)
            item.setSizeHint(QSize(0, _CARD_H + 1))
            self.addItem(item)
            card = _MatchCard(match)
            card.clicked.connect(self._on_card_clicked)
            self.setItemWidget(item, card)

        if prev_id is not None:
            for i in range(self.count()):
                if self.item(i).data(Qt.UserRole) == prev_id:
                    self.setCurrentRow(i)
                    return
        if self.count() > 0:
            self.setCurrentRow(0)

    def current_match_id(self) -> object | None:
        item = self.currentItem()
        return item.data(Qt.UserRole) if item else None

    def select_match(self, match_id: object) -> None:
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == match_id:
                self.setCurrentRow(i)
                return

    # ── internal ─────────────────────────────────────────────────────────────

    def _on_card_clicked(self, match_id: object) -> None:
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == match_id:
                self.setCurrentRow(i)
                return

    def _show_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        self.setCurrentItem(item)
        match_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        action = menu.addAction("DELETE GAME")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == action:
            self.delete_requested.emit(match_id)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            match_id = self.current_match_id()
            if match_id is not None:
                self.delete_requested.emit(match_id)
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_item_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if previous:
            w = self.itemWidget(previous)
            if isinstance(w, _MatchCard):
                w.set_selected(False)
        if current:
            w = self.itemWidget(current)
            if isinstance(w, _MatchCard):
                w.set_selected(True)
            self.match_selected.emit(current.data(Qt.UserRole))


class MatchListWidget(QWidget):
    match_selected: Signal = Signal(object)
    delete_requested: Signal = Signal(object)

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._account_summary = _AccountSummaryPanel()
        root.addWidget(self._account_summary)

        combo = QWidget()
        combo_layout = QVBoxLayout(combo)
        combo_layout.setContentsMargins(0, 0, 0, 0)
        combo_layout.setSpacing(0)

        self._recent_summary = _RecentSummaryPanel()
        combo_layout.addWidget(self._recent_summary)

        self._list = _MatchListView(db)
        self._list.match_selected.connect(self.match_selected.emit)
        self._list.delete_requested.connect(self.delete_requested.emit)
        combo_layout.addWidget(self._list, 1)

        root.addWidget(combo, 1)

    def refresh(self, preserve_selection: bool = True) -> None:
        matches = self._db.list_display_matches(limit=1000)
        recent = matches[:_RECENT_MATCH_LIMIT]
        self._account_summary.set_stats(_stats_for(matches))
        self._recent_summary.set_stats(_stats_for(recent), len(recent))
        self._list.set_matches(matches, preserve_selection=preserve_selection)

    def count(self) -> int:
        return self._list.count()

    def current_match_id(self) -> object | None:
        return self._list.current_match_id()

    def select_match(self, match_id: object) -> None:
        self._list.select_match(match_id)
