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
        "bg_main":      "#11151f",
        "bg_titlebar":  "#171b26",
        "bg_sidebar":   "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #181d29, stop:1 #0d1017)",
        "bg_sidebar_img": "assets/images/sidebar_bg_dark.png",
        "bg_card":      "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1c212e, stop:1 #161a24)",
        "bg_input":     "#12151d",
        "bg_hover":     "rgba(255, 255, 255, 0.06)",
        "bg_selected":  "rgba(59, 130, 246, 0.15)",
        
        "nav_bg_active": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #1d4ed8)",
        "nav_text_active": "#ffffff",
        "nav_text": "#ffffff",
        "nav_border":    "1px solid rgba(255, 255, 255, 0.04)",

        # borders / dividers
        "border":       "rgba(255, 255, 255, 0.08)",
        "border_accent":"#3b82f6",
        "border_launch_btn": "rgba(255, 255, 255, 0.15)",

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
        "bg_main":      "#f3f6f9",
        "bg_titlebar":  "#d2dae5",
        "bg_sidebar":   "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #e8eff5)",
        "bg_sidebar_img": "assets/images/sidebar_bg_light.png",
        "bg_card":      "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f8fafc)",
        "bg_input":     "#e9eff5",
        "bg_hover":     "rgba(0, 0, 0, 0.04)",
        "bg_selected":  "rgba(37, 99, 235, 0.1)",
        
        "nav_bg_active": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb)",
        "nav_text_active": "#ffffff",
        "nav_text": "#0f172a",
        "nav_border":    "1px solid rgba(0, 0, 0, 0.05)",

        "border":       "rgba(0, 0, 0, 0.08)",
        "border_accent":"#3b82f6",
        "border_launch_btn": "rgba(0, 0, 0, 0.15)",

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

QWidget {{
    color: {text_primary};
    font-family: "Segoe UI", "Inter", "Helvetica Neue", sans-serif;
    font-size: 14px;
    background-color: transparent;
}}

QMainWindow, QDialog, QFileDialog, QInputDialog, QMessageBox {{
    background-color: {bg_main};
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
    border-image: url({bg_sidebar_img}) 0 0 0 0 stretch stretch;
    background-color: {bg_sidebar};
}}

/* ── Nav buttons ─────────────────────────────────────────────────────── */
QPushButton[class="nav-button"] {{
    background-color: transparent;
    text-align: left;
    padding: 8px 18px 8px 16px;
    border: none;
    border-radius: 10px;
    margin: 2px 12px;
    font-size: 13px;
    font-weight: 500;
    color: {nav_text};
    min-height: 28px;
}}
QPushButton[class="nav-button"]:hover {{
    background: {bg_hover};
    color: {text_primary};
}}
QPushButton[class="nav-button"]:checked {{
    background: {nav_bg_active};
    border: none;
    color: {nav_text_active};
    font-weight: 600;
}}

/* ── Stacked content area ────────────────────────────────────────────── */
QStackedWidget {{
    background-color: {bg_main};
}}

/* ── Text properties ─────────────────────────────────────────────────── */
QLabel[class="text-primary"] {{ color: {text_primary}; }}
QLabel[class="text-secondary"] {{ color: {text_secondary}; }}
QLabel[class="text-dim"] {{ color: {text_dim}; }}

/* ── Page headings ───────────────────────────────────────────────────── */
QLabel[class="h1"] {{
    font-size: 24px;
    font-weight: 700;
    color: {text_primary};
    letter-spacing: -0.5px;
}}

/* ── Cards ───────────────────────────────────────────────────────────── */
QFrame[class="card"] {{
    background: {bg_card};
    border: 1px solid {border};
    border-radius: 14px;
    padding: 24px;
    margin-top: 14px;
}}

/* ── Action buttons ──────────────────────────────────────────────────── */
QPushButton[class="action-button"], QPushButton[class="btn-primary"] {{
    background: {nav_bg_active};
    color: #ffffff;
    border: none;
    padding: 9px 20px;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.2px;
}}
QPushButton[class="action-button"]:hover, QPushButton[class="btn-primary"]:hover {{
    opacity: 0.9;
}}
QPushButton[class="action-button"]:disabled, QPushButton[class="btn-primary"]:disabled {{
    background-color: {bg_hover};
    color: {text_dim};
}}
QPushButton[class="btn-success"] {{
    background-color: {success};
    color: #ffffff;
    border: none;
    padding: 9px 20px;
    border-radius: 10px;
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
    border-radius: 10px;
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
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[class="btn-warning"]:hover {{
    opacity: 0.9;
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
    border-radius: 10px;
    padding: 9px 14px;
    selection-background-color: {accent};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {accent};
}}

QPushButton {{
    background-color: {bg_selected};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {bg_hover};
}}
QPushButton[class="launch-btn"] {{
    border: 1px solid {border_launch_btn};
}}
QPushButton[class="launch-btn"]:hover {{
    background-color: {bg_hover};
}}

QComboBox {{
    background-color: {bg_input};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 9px 14px;
    min-height: 32px;
}}
QComboBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
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
    border-radius: 10px;
    padding: 9px 14px;
}}
QSpinBox:focus {{
    border: 1px solid {accent};
}}

/* ── Tables ──────────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 12px;
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
    border-radius: 12px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 10px 14px;
    border-radius: 8px;
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
    width: 7px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 3.5px;
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
    height: 7px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border};
    border-radius: 3.5px;
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
    border-radius: 12px;
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
    padding: 8px 12px;
    font-size: 12px;
    border-radius: 10px;
}}

/* ── Progress / Dialogs ──────────────────────────────────────────────── */
QProgressDialog {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 14px;
}}
QProgressBar {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    color: {text_primary};
    height: 8px;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 6px;
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
    border-radius: 6px;
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
/* ── Title Bar ───────────────────────────────────────────────────────── */
QFrame#titleBar {{
    background-color: {bg_titlebar};
}}
QLabel#titleLabel {{
    color: {text_primary};
}}
QPushButton[class="mac-btn"] {{
    border: none;
    border-radius: 6px;
    min-width: 12px;
    max-width: 12px;
    min-height: 12px;
    max-height: 12px;
    font-family: Arial, sans-serif;
    font-size: 9px;
    font-weight: 900;
    color: transparent;
    padding: 0px 0px 1px 0px;
    margin: 0px 3px;
}}
QPushButton#macClose {{ background-color: #ff5f56; }}
QPushButton#macMin {{ background-color: #ffbd2e; }}
QPushButton#macMax {{ background-color: #27c93f; }}

QFrame#macBtnContainer:hover QPushButton#macClose {{ color: #4d0000; }}
QFrame#macBtnContainer:hover QPushButton#macMin {{ color: #995b00; }}
QFrame#macBtnContainer:hover QPushButton#macMax {{ color: #004d00; }}

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
