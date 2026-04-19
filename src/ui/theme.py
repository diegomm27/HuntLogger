from __future__ import annotations


PALETTE = {
    # Base — deep, near-black with a warm tungsten bias, reminiscent of
    # the Hunt: Showdown main menu backdrop.
    "bg":        "#0b0806",
    "bg_alt":    "#120d09",
    "bg_deep":   "#060403",

    # Surfaces / cards
    "panel":     "#1a130d",
    "panel_alt": "#231810",
    "panel_hi":  "#2d2015",

    # Borders — warm brown, with a brighter accent variant
    "border":    "#3a2a1c",
    "border_hi": "#5e4428",

    # Text — aged parchment / worn paper
    "text":      "#dac6a0",
    "text_dim":  "#9b8463",
    "text_mute": "#5c4a34",

    # Signature Hunt gold / amber
    "gold":      "#c89b5c",
    "gold_hi":   "#ecc079",
    "gold_lo":   "#8a6a3d",

    # Danger / blood
    "blood":     "#7a2418",
    "blood_hi":  "#c74a34",
    "red":       "#c04030",

    # Success / swamp green
    "green":     "#7ab855",
    "green_dim": "#4a7d35",
}


DISPLAY_FONT = '"Rockwell", "Bookman Old Style", "Georgia", serif'
BODY_FONT    = '"Segoe UI", "Trebuchet MS", sans-serif'


STYLESHEET = f"""
* {{
    font-family: {BODY_FONT};
    color: {PALETTE["text"]};
    outline: 0;
}}

QToolTip {{
    background-color: {PALETTE["panel_hi"]};
    color: {PALETTE["gold_hi"]};
    border: 1px solid {PALETTE["gold_lo"]};
    padding: 5px 8px;
    font-size: 11px;
    letter-spacing: 1px;
}}

QMainWindow, QDialog {{
    background-color: {PALETTE["bg"]};
}}
QWidget {{
    background-color: transparent;
    color: {PALETTE["text"]};
    selection-background-color: {PALETTE["blood"]};
    selection-color: {PALETTE["gold_hi"]};
}}
QMainWindow > QWidget#centralwidget,
QMainWindow::separator {{
    background-color: {PALETTE["bg"]};
}}

/* ── Top bar ─────────────────────────────────────────────────────────── */
QFrame#TopBar {{
    background-color: {PALETTE["bg_alt"]};
    border: none;
    border-bottom: 1px solid {PALETTE["border_hi"]};
}}
QFrame#TopBarAccent {{
    background-color: {PALETTE["gold"]};
    border: none;
}}
QLabel#AppTitle {{
    color: {PALETTE["gold_hi"]};
    font-family: {DISPLAY_FONT};
    font-size: 19px;
    font-weight: bold;
    letter-spacing: 5px;
    padding-left: 2px;
}}
QLabel#AppSubtitle {{
    color: {PALETTE["text_mute"]};
    font-size: 9px;
    letter-spacing: 3px;
    padding-top: 2px;
}}
QLabel#StatusDot {{
    font-size: 14px;
    padding: 0 4px 0 0;
}}
QLabel#StatusDot[state="watching"] {{ color: {PALETTE["green"]}; }}
QLabel#StatusDot[state="error"]    {{ color: {PALETTE["red"]}; }}
QLabel#StatusDot[state="idle"]     {{ color: {PALETTE["text_mute"]}; }}

QLabel#StatusLabel {{
    color: {PALETTE["text_dim"]};
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 3px;
}}
QLabel#StatusLabel[state="watching"] {{ color: {PALETTE["green"]}; }}
QLabel#StatusLabel[state="error"]    {{ color: {PALETTE["blood_hi"]}; }}
QLabel#StatusLabel[state="idle"]     {{ color: {PALETTE["text_mute"]}; }}

QLabel#PathLabel {{
    color: {PALETTE["text_mute"]};
    font-size: 10px;
    letter-spacing: 1px;
}}

/* ── Section headers (serif display) ─────────────────────────────────── */
QLabel.section {{
    color: {PALETTE["gold"]};
    font-family: {DISPLAY_FONT};
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 3px;
    padding: 8px 0 4px 0;
    border-bottom: 1px solid {PALETTE["border"]};
}}
QLabel.kpi_label {{
    color: {PALETTE["text_dim"]};
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 3px;
}}
QLabel.kpi_value {{
    color: {PALETTE["gold_hi"]};
    font-family: {DISPLAY_FONT};
    font-size: 22px;
    font-weight: bold;
}}
QLabel.kpi_value[tone="good"] {{ color: {PALETTE["green"]}; }}
QLabel.kpi_value[tone="bad"]  {{ color: {PALETTE["blood_hi"]}; }}

/* ── Cards / panels ──────────────────────────────────────────────────── */
QFrame.card {{
    background-color: {PALETTE["panel"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 0;
}}
QFrame.card_hi {{
    background-color: {PALETTE["panel_alt"]};
    border: 1px solid {PALETTE["gold_lo"]};
    border-radius: 0;
}}

/* ── List / tree / table / plain text ────────────────────────────────── */
QListWidget, QTreeWidget, QTableWidget, QPlainTextEdit, QTextEdit {{
    background-color: {PALETTE["panel"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 0;
    gridline-color: {PALETTE["border"]};
    alternate-background-color: {PALETTE["panel_alt"]};
    selection-background-color: {PALETTE["blood"]};
    selection-color: {PALETTE["gold_hi"]};
}}
QListWidget::item {{
    padding: 0;
    border: none;
    background: transparent;
}}
QListWidget::item:selected {{ background: transparent; }}

QTreeWidget::item, QTableWidget::item {{
    padding: 7px 10px;
    border-bottom: 1px solid {PALETTE["bg_alt"]};
}}
QTreeWidget::item:hover, QTableWidget::item:hover {{
    background-color: {PALETTE["bg_alt"]};
}}
QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: {PALETTE["blood"]};
    color: {PALETTE["gold_hi"]};
}}

QHeaderView::section {{
    background-color: {PALETTE["bg_alt"]};
    color: {PALETTE["gold"]};
    padding: 8px 10px;
    border: none;
    border-right: 1px solid {PALETTE["border"]};
    border-bottom: 1px solid {PALETTE["border_hi"]};
    font-weight: bold;
    font-size: 10px;
    letter-spacing: 2px;
}}
QHeaderView::section:last {{
    border-right: none;
}}

/* ── Tabs ────────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {PALETTE["border"]};
    border-top: 1px solid {PALETTE["border_hi"]};
    background-color: {PALETTE["panel"]};
    top: -1px;
}}
QTabBar {{
    qproperty-drawBase: 0;
    background: {PALETTE["bg"]};
}}
QTabBar::tab {{
    background: {PALETTE["bg_alt"]};
    color: {PALETTE["text_dim"]};
    padding: 10px 22px;
    border: 1px solid {PALETTE["border"]};
    border-bottom: none;
    font-weight: bold;
    font-size: 10px;
    letter-spacing: 3px;
    margin-right: 1px;
}}
QTabBar::tab:selected {{
    background: {PALETTE["panel"]};
    color: {PALETTE["gold_hi"]};
    border-top: 2px solid {PALETTE["gold"]};
    padding-top: 9px;
}}
QTabBar::tab:hover:!selected {{
    color: {PALETTE["gold"]};
    background: {PALETTE["panel"]};
}}

/* ── Buttons ─────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {PALETTE["panel_hi"]},
        stop:1 {PALETTE["panel"]}
    );
    color: {PALETTE["gold"]};
    border: 1px solid {PALETTE["border_hi"]};
    padding: 7px 18px;
    font-weight: bold;
    font-size: 10px;
    letter-spacing: 2px;
}}
QPushButton:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {PALETTE["panel_hi"]},
        stop:1 {PALETTE["panel_alt"]}
    );
    color: {PALETTE["gold_hi"]};
    border: 1px solid {PALETTE["gold"]};
}}
QPushButton:pressed {{
    background-color: {PALETTE["blood"]};
    color: {PALETTE["gold_hi"]};
    border: 1px solid {PALETTE["blood_hi"]};
    padding-top: 8px;
    padding-bottom: 6px;
}}
QPushButton:disabled {{
    color: {PALETTE["text_mute"]};
    background-color: {PALETTE["bg_alt"]};
    border-color: {PALETTE["border"]};
}}
QPushButton#Primary {{
    color: {PALETTE["gold_hi"]};
    border: 1px solid {PALETTE["gold"]};
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {PALETTE["panel_hi"]},
        stop:1 {PALETTE["panel"]}
    );
}}
QPushButton#Primary:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {PALETTE["gold_lo"]},
        stop:1 {PALETTE["panel_hi"]}
    );
    color: #ffffff;
}}
QPushButton#Danger {{
    color: {PALETTE["blood_hi"]};
    border-color: {PALETTE["blood"]};
}}
QPushButton#Danger:hover {{
    background-color: {PALETTE["blood"]};
    color: {PALETTE["gold_hi"]};
    border-color: {PALETTE["blood_hi"]};
}}

/* ── Nav buttons (top-bar section switcher) ──────────────────────────── */
QPushButton#NavBtn {{
    background: transparent;
    color: {PALETTE["text_mute"]};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 18px 4px 18px;
    font-weight: bold;
    font-size: 10px;
    letter-spacing: 3px;
}}
QPushButton#NavBtn:hover {{
    color: {PALETTE["gold"]};
    background: transparent;
    border-bottom: 2px solid {PALETTE["gold_lo"]};
}}
QPushButton#NavBtn[active="true"] {{
    color: {PALETTE["gold_hi"]};
    background: transparent;
    border-bottom: 2px solid {PALETTE["gold"]};
}}

/* ── Inputs ──────────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {PALETTE["bg_alt"]};
    border: 1px solid {PALETTE["border"]};
    padding: 6px 10px;
    color: {PALETTE["text"]};
    selection-background-color: {PALETTE["blood"]};
    selection-color: {PALETTE["gold_hi"]};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {PALETTE["gold"]};
    background-color: {PALETTE["bg"]};
}}

/* ── Scrollbars ──────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {PALETTE["bg"]};
    width: 10px;
    margin: 0;
    border-left: 1px solid {PALETTE["border"]};
}}
QScrollBar::handle:vertical {{
    background: {PALETTE["border_hi"]};
    min-height: 40px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {PALETTE["gold_lo"]}; }}
QScrollBar::handle:vertical:pressed {{ background: {PALETTE["gold"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: {PALETTE["bg"]};
    height: 10px;
    margin: 0;
    border-top: 1px solid {PALETTE["border"]};
}}
QScrollBar::handle:horizontal {{
    background: {PALETTE["border_hi"]};
    min-width: 40px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {PALETTE["gold_lo"]}; }}
QScrollBar::handle:horizontal:pressed {{ background: {PALETTE["gold"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; background: none; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ── Menus ───────────────────────────────────────────────────────────── */
QMenu {{
    background-color: {PALETTE["panel"]};
    border: 1px solid {PALETTE["border_hi"]};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 22px;
    color: {PALETTE["text"]};
}}
QMenu::item:selected {{
    background-color: {PALETTE["blood"]};
    color: {PALETTE["gold_hi"]};
}}

/* ── Splitter handle ─────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {PALETTE["border"]};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical   {{ height: 1px; }}
QSplitter::handle:hover {{
    background: {PALETTE["gold_lo"]};
}}

/* ── Status bar ──────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {PALETTE["bg_alt"]};
    color: {PALETTE["text_dim"]};
    border-top: 1px solid {PALETTE["border_hi"]};
    font-size: 10px;
    letter-spacing: 1px;
}}
QStatusBar::item {{ border: none; }}

/* ── GroupBox ────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {PALETTE["panel"]};
    color: {PALETTE["gold"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 0;
    margin-top: 14px;
    font-family: {DISPLAY_FONT};
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 3px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 8px;
    background-color: {PALETTE["bg"]};
    color: {PALETTE["gold_hi"]};
}}

/* ── Check/radio ─────────────────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {PALETTE["text"]};
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {PALETTE["border_hi"]};
    background: {PALETTE["bg_alt"]};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {PALETTE["gold"]};
    border-color: {PALETTE["gold_hi"]};
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
