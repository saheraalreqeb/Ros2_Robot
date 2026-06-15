"""
gui/theme.py
============
Centralised theme registry.  Import ``ThemeManager`` and call
``ThemeManager.apply(app, theme_name)`` to switch themes at runtime.
Provides helper ``icon(name)`` that returns correctly-coloured QIcons.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
import qtawesome as qta

# ─── Palette definitions ──────────────────────────────────────────────────────

THEMES: dict[str, dict] = {
    "dark": {
        # backgrounds
        "bg_main":      "#0d0f14",
        "bg_sidebar":   "#111318",
        "bg_card":      "#161a24",
        "bg_input":     "#1c2130",
        "bg_hover":     "#1e2435",
        "bg_selected":  "#1f2d4a",

        # borders / dividers
        "border":       "#242b3d",
        "border_accent":"#2563eb",

        # text
        "text_primary": "#e2e8f0",
        "text_secondary":"#8892a4",
        "text_dim":     "#4a5568",

        # accent / brand
        "accent":       "#3b82f6",
        "accent_hover": "#60a5fa",
        "accent_glow":  "rgba(59,130,246,0.18)",

        # semantic
        "success":      "#22c55e",
        "warning":      "#f59e0b",
        "danger":       "#ef4444",
        "info":         "#06b6d4",

        # status bar
        "statusbar_bg": "#111318",
        "statusbar_text":"#8892a4",

        # icon colour (qta)
        "icon_color":   "#8892a4",
        "icon_active":  "#e2e8f0",
        "icon_accent":  "#3b82f6",
    },

    "light": {
        "bg_main":      "#f0f4f8",
        "bg_sidebar":   "#ffffff",
        "bg_card":      "#ffffff",
        "bg_input":     "#f8fafc",
        "bg_hover":     "#eff6ff",
        "bg_selected":  "#dbeafe",

        "border":       "#e2e8f0",
        "border_accent":"#2563eb",

        "text_primary": "#1e293b",
        "text_secondary":"#475569",
        "text_dim":     "#94a3b8",

        "accent":       "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_glow":  "rgba(37,99,235,0.12)",

        "success":      "#16a34a",
        "warning":      "#d97706",
        "danger":       "#dc2626",
        "info":         "#0891b2",

        "statusbar_bg": "#2563eb",
        "statusbar_text":"#ffffff",

        "icon_color":   "#475569",
        "icon_active":  "#1e293b",
        "icon_accent":  "#2563eb",
    },
}

# ─── QSS templates ────────────────────────────────────────────────────────────

_QSS_TEMPLATE = """
/* ── Reset ──────────────────────────────────────────────────────────── */
* {{ outline: 0; }}

QMainWindow, QDialog {{
    background-color: {bg_main};
}}

QWidget {{
    color: {text_primary};
    font-family: "Segoe UI", "Inter", "Helvetica Neue", sans-serif;
    font-size: 14px;
    background-color: transparent;
}}

QLabel a {{
    color: {accent};
    text-decoration: none;
}}
QLabel a:hover {{
    color: {accent_hover};
    text-decoration: underline;
}}

/* ── Sidebar ─────────────────────────────────────────────────────────── */
QFrame#sidebar {{
    background-color: {bg_sidebar};
    border-right: 1px solid {border};
}}

/* ── Nav buttons ─────────────────────────────────────────────────────── */
QPushButton[class="nav-button"] {{
    background-color: transparent;
    text-align: left;
    padding: 11px 18px 11px 16px;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    font-size: 13px;
    font-weight: 500;
    color: {text_secondary};
    min-height: 40px;
}}
QPushButton[class="nav-button"]:hover {{
    background-color: {bg_hover};
    color: {text_primary};
    border-left: 3px solid {border};
}}
QPushButton[class="nav-button"]:checked {{
    background-color: {bg_selected};
    color: {accent};
    border-left: 3px solid {accent};
    font-weight: 600;
}}

/* ── Stacked content area ────────────────────────────────────────────── */
QStackedWidget {{
    background-color: {bg_main};
}}

/* ── Page headings ───────────────────────────────────────────────────── */
QLabel[class="h1"] {{
    font-size: 24px;
    font-weight: 700;
    color: {text_primary};
    letter-spacing: -0.5px;
}}

/* ── Cards ───────────────────────────────────────────────────────────── */
QFrame[class="card"] {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 20px;
    margin-top: 14px;
}}

/* ── Action buttons ──────────────────────────────────────────────────── */
QPushButton[class="action-button"] {{
    background-color: {accent};
    color: #ffffff;
    border: none;
    padding: 9px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.2px;
}}
QPushButton[class="action-button"]:hover {{
    background-color: {accent_hover};
}}
QPushButton[class="action-button"]:pressed {{
    background-color: {accent};
    opacity: 0.8;
}}

QPushButton[class="btn-success"] {{
    background-color: {success};
    color: #ffffff;
    border: none;
    padding: 9px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[class="btn-success"]:hover {{
    opacity: 0.9;
}}
QPushButton[class="btn-danger"] {{
    background-color: {danger};
    color: #ffffff;
    border: none;
    padding: 9px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[class="btn-danger"]:hover {{
    opacity: 0.9;
}}
QPushButton[class="btn-warning"] {{
    background-color: {warning};
    color: #ffffff;
    border: none;
    padding: 9px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[class="btn-warning"]:hover {{
    opacity: 0.9;
}}
QPushButton[class="btn-primary"] {{
    background-color: {accent};
    color: #ffffff;
    border: none;
    padding: 9px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[class="btn-primary"]:hover {{
    background-color: {accent_hover};
}}

/* ── Typography & helper labels ───────────────────────────────────────── */
QLabel[class="section-title"] {{
    font-size: 18px;
    font-weight: 700;
    color: {text_primary};
}}
QLabel[class="muted"] {{
    color: {text_secondary};
    font-size: 12px;
}}
QLabel[class="detail"] {{
    color: {text_secondary};
    font-size: 13px;
}}
QLabel[class="path"] {{
    color: {text_dim};
    font-size: 11px;
}}
QTextEdit[class="monospace"], QPlainTextEdit[class="monospace"] {{
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}}

/* ── Input fields ────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {bg_input};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 11px;
    selection-background-color: {accent};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {accent};
}}

QComboBox {{
    background-color: {bg_input};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 11px;
    min-height: 32px;
}}
QComboBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox QAbstractItemView {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    selection-background-color: {accent};
    outline: none;
}}

QSpinBox {{
    background-color: {bg_input};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 11px;
}}
QSpinBox:focus {{
    border: 1px solid {accent};
}}

/* ── Tables ──────────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 8px;
    gridline-color: {border};
}}
QHeaderView::section {{
    background-color: {bg_input};
    color: {text_secondary};
    border: none;
    border-bottom: 1px solid {border};
    padding: 8px 12px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QTableWidget::item:selected {{
    background-color: {bg_selected};
    color: {accent};
}}

/* ── List widgets ────────────────────────────────────────────────────── */
QListWidget {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 9px 12px;
    border-radius: 6px;
}}
QListWidget::item:hover {{
    background-color: {bg_hover};
}}
QListWidget::item:selected {{
    background-color: {bg_selected};
    color: {accent};
}}

/* ── Scroll bars ─────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {text_dim};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {text_dim};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Group boxes ─────────────────────────────────────────────────────── */
QGroupBox {{
    color: {text_secondary};
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.5px;
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    text-transform: uppercase;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {text_secondary};
}}

/* ── Status bar ──────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {statusbar_bg};
    color: {statusbar_text};
    font-size: 12px;
    font-weight: 500;
    border-top: 1px solid {border};
    padding: 0 12px;
    min-height: 26px;
}}

/* ── Tooltips ────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border_accent};
    padding: 6px 10px;
    font-size: 12px;
    border-radius: 6px;
}}

/* ── Progress / Dialogs ──────────────────────────────────────────────── */
QProgressDialog {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 10px;
}}
QProgressBar {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: 4px;
    text-align: center;
    color: {text_primary};
    height: 8px;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 4px;
}}

/* ── Check boxes / Radio ─────────────────────────────────────────────── */
QCheckBox {{
    color: {text_primary};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {border};
    border-radius: 4px;
    background: {bg_input};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}

QRadioButton {{
    color: {text_primary};
    spacing: 8px;
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {border};
    border-radius: 9px;
    background: {bg_input};
}}
QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}

/* ── Slider ──────────────────────────────────────────────────────────── */
QSlider::horizontal {{
    min-height: 24px;
}}
QSlider::groove:horizontal {{
    background: {bg_input};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}

/* ── Message boxes ───────────────────────────────────────────────────── */
QMessageBox {{
    background-color: {bg_card};
}}
QMessageBox QLabel {{
    color: {text_primary};
}}
"""


class ThemeManager:
    """Singleton-style class that tracks & applies the active theme."""

    _current: str = "dark"

    @classmethod
    def current(cls) -> str:
        return cls._current

    @classmethod
    def palette(cls, name: str | None = None) -> dict:
        return THEMES[name or cls._current]

    @classmethod
    def apply(cls, app, name: str) -> None:
        """Apply *name* theme to *app* (QApplication)."""
        if name not in THEMES:
            return
        cls._current = name
        p = THEMES[name]
        qss = _QSS_TEMPLATE.format(**p)
        app.setStyleSheet(qss)
        # Update qtawesome defaults so icons already created will re-render
        qta.reset_cache()

    @classmethod
    def icon(cls, icon_name: str, role: str = "normal", **kwargs) -> "QIcon":
        """
        Return a qtawesome icon pre-coloured for the current theme.

        role: 'normal' | 'active' | 'accent' | 'success' | 'warning' | 'danger'
        """
        p = cls.palette()
        colour_map = {
            "normal":  p["icon_color"],
            "active":  p["icon_active"],
            "accent":  p["icon_accent"],
            "success": p["success"],
            "warning": p["warning"],
            "danger":  p["danger"],
        }
        color = colour_map.get(role, p["icon_color"])
        return qta.icon(icon_name, color=color, **kwargs)
