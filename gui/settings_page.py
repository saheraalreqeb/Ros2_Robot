"""
gui/settings_page.py
====================
Settings tab – theme picker + sidebar-tab visibility manager.
"""

from __future__ import annotations

from typing import Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QCheckBox, QScrollArea, QButtonGroup,
    QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from gui.theme import ThemeManager


# ─── Settings page ────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    """
    Settings panel.

    Signals
    -------
    theme_changed(str)      – emitted when user picks a theme
    tab_visibility_changed  – emitted when user toggles a tab checkbox
    """

    theme_changed: Signal = Signal(str)
    tab_visibility_changed: Signal = Signal()
    opengl_setting_changed: Signal = Signal(bool)
    save_requested: Signal = Signal()

    # Tabs the user can show / hide.
    # Format:  (key, display_label, always_visible)
    _TAB_DEFS: list[tuple[str, str, bool]] = [
        ("workspace",      "Workspace",         True),   # always shown
        ("packages",       "Packages",          False),
        ("nodes",          "Nodes",             False),
        ("topics",         "Topic Inspector",   False),
        ("launch",         "Launch Manager",    False),
        ("services",       "Service Inspector", False),
        ("actions",        "Action Inspector",  False),
        ("logs",           "Log Viewer",        False),
        ("troubleshooter", "DDS Troubleshooter",False),
        ("params",         "Parameters",        False),
        ("visualizer",     "Visualizer",        False),
        ("bags",           "Bag Manager",       False),
        ("urdf",           "URDF Viewer",       False),
        ("tools",          "Tools Hub",         False),
        ("settings",       "Settings",          True),   # always shown
    ]


    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tab_checks: dict[str, QCheckBox] = {}
        self._chk_opengl: QCheckBox | None = None
        self._build_ui()

    # ── public ────────────────────────────────────────────────────────────────

    def tab_visibility(self) -> dict[str, bool]:
        """Return {key: visible} for every managed tab."""
        return {k: cb.isChecked() for k, cb in self._tab_checks.items()}

    def set_tab_visibility(self, state: dict[str, bool]) -> None:
        """Restore previously saved tab visibility."""
        for key, cb in self._tab_checks.items():
            if key in state:
                cb.blockSignals(True)
                cb.setChecked(state[key])
                cb.blockSignals(False)
        self.tab_visibility_changed.emit()

    def is_opengl_enabled(self) -> bool:
        return self._chk_opengl.isChecked() if self._chk_opengl else False

    def set_opengl_enabled(self, enabled: bool) -> None:
        if self._chk_opengl:
            self._chk_opengl.blockSignals(True)
            self._chk_opengl.setChecked(enabled)
            self._chk_opengl.blockSignals(False)
            self.opengl_setting_changed.emit(enabled)

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Outer scroll so it works on small screens
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(48, 40, 48, 40)
        root.setSpacing(0)
        root.setAlignment(Qt.AlignTop)

        # ── Page title ─────────────────────────────────────────────────────
        try:
            from gui.theme import ThemeManager as TM
            icon_lbl = QLabel()
            import qtawesome as qta
            pix = qta.icon(
                "fa5s.cog", color=TM.palette()["accent"]
            ).pixmap(28, 28)
            icon_lbl.setPixmap(pix)
        except Exception:
            icon_lbl = QLabel("⚙")

        title = QLabel("Settings")
        title.setProperty("class", "h1")

        hdr = QHBoxLayout()
        hdr.setSpacing(12)
        hdr.addWidget(icon_lbl)
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        sub = QLabel("Personalise your Ros2 Robot experience.")
        sub.setStyleSheet("color: palette(mid); font-size: 13px; margin-bottom: 28px;")
        root.addWidget(sub)
        root.addSpacing(28)

        # ── Section 1 – Theme ──────────────────────────────────────────────
        root.addWidget(_section_label("Appearance"))
        root.addSpacing(10)
        theme_card = _Card()
        theme_lay = QVBoxLayout(theme_card)
        theme_lay.setSpacing(16)

        row_label = QLabel("Color Theme")
        row_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        theme_lay.addWidget(row_label)

        desc = QLabel(
            "Choose how the application looks. Icons and colours update instantly."
        )
        desc.setStyleSheet("font-size: 12px;")
        desc.setWordWrap(True)
        theme_lay.addWidget(desc)

        # Theme option buttons
        theme_btn_row = QHBoxLayout()
        theme_btn_row.setSpacing(12)

        self._btn_dark  = _ThemeOptionButton("Dark",  "fa5s.moon",  "dark")
        self._btn_light = _ThemeOptionButton("Light", "fa5s.sun",   "light")

        for btn in (self._btn_dark, self._btn_light):
            btn.clicked.connect(lambda *args, b=btn: self._on_theme_clicked(b))
            theme_btn_row.addWidget(btn)

        theme_btn_row.addStretch()
        theme_lay.addLayout(theme_btn_row)

        # Rendering options
        theme_lay.addSpacing(10)
        rend_label = QLabel("3D Rendering")
        rend_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        theme_lay.addWidget(rend_label)

        rend_desc = QLabel(
            "Use your GPU to render 3D meshes in the URDF Viewer. "
            "Faster, but may cause issues on systems with missing graphics drivers."
        )
        rend_desc.setStyleSheet("font-size: 12px; color: palette(mid);")
        rend_desc.setWordWrap(True)
        theme_lay.addWidget(rend_desc)

        chk_lay = QHBoxLayout()
        self._chk_opengl = QCheckBox(" Enable Hardware OpenGL Rendering")
        self._chk_opengl.stateChanged.connect(
            lambda state: self.opengl_setting_changed.emit(bool(state))
        )
        
        try:
            import qtawesome as qta
            info_icon = QLabel()
            info_icon.setPixmap(qta.icon("fa5s.microchip", color=ThemeManager.palette()["accent"]).pixmap(16, 16))
            chk_lay.addWidget(info_icon)
        except Exception:
            pass
            
        chk_lay.addWidget(self._chk_opengl)
        chk_lay.addStretch()
        theme_lay.addLayout(chk_lay)

        root.addWidget(theme_card)
        root.addSpacing(28)

        # Sync initial selection
        self._sync_theme_buttons()

        # ── Section 2 – Sidebar Tabs ───────────────────────────────────────
        root.addWidget(_section_label("Sidebar Tabs"))
        root.addSpacing(10)

        tab_card = _Card()
        tab_lay = QVBoxLayout(tab_card)
        tab_lay.setSpacing(4)

        row_label2 = QLabel("Choose which tabs appear in the sidebar")
        row_label2.setStyleSheet("font-weight: 600; font-size: 14px; margin-bottom: 6px;")
        tab_lay.addWidget(row_label2)

        desc2 = QLabel(
            "Hidden tabs can always be re-enabled here. "
            "The Workspace tab is always visible and cannot be hidden."
        )
        desc2.setWordWrap(True)
        desc2.setStyleSheet("font-size: 12px; margin-bottom: 12px;")
        tab_lay.addWidget(desc2)

        for key, label, locked in self._TAB_DEFS:
            row = QHBoxLayout()
            row.setSpacing(10)

            cb = QCheckBox(label)
            cb.blockSignals(True)
            cb.setChecked(True)           # default: all visible
            cb.blockSignals(False)
            cb.setEnabled(not locked)     # Workspace always on
            cb.stateChanged.connect(lambda _: self.tab_visibility_changed.emit())
            self._tab_checks[key] = cb

            row.addWidget(cb)
            row.addStretch()

            if locked:
                badge = QLabel("Always on")
                badge.setStyleSheet(
                    "color: palette(mid); font-size: 11px; "
                    "background: palette(window); border-radius: 4px; padding: 2px 6px;"
                )
                row.addWidget(badge)

            tab_lay.addLayout(row)

        root.addWidget(tab_card)
        root.addSpacing(28)

        # ── Section 3 – About & Contact ────────────────────────────────────
        root.addWidget(_section_label("About & Contact"))
        root.addSpacing(10)

        about_card = _Card()
        about_lay = QVBoxLayout(about_card)
        about_lay.setSpacing(10)

        owner_name = QLabel("Saher ALREQEB")
        owner_name.setStyleSheet("font-weight: 700; font-size: 15px;")
        about_lay.addWidget(owner_name)

        owner_info = QLabel("Developer of Ros2 Robot.\n"
                            "Feel free to get in touch or check out my work using the links below.")
        owner_info.setStyleSheet("font-size: 13px; color: palette(mid);")
        owner_info.setWordWrap(True)
        about_lay.addWidget(owner_info)

        links_lay = QHBoxLayout()
        links_lay.setSpacing(20)

        email_lbl = QLabel()
        email_lbl.setText('<a href="mailto:s.a.alreqeb@gmail.com">📧 s.a.alreqeb@gmail.com</a>')
        email_lbl.setOpenExternalLinks(True)
        links_lay.addWidget(email_lbl)

        web_lbl = QLabel()
        web_lbl.setText('<a href="https://www.saheralreqeb.work/">🌐 saheralreqeb.work</a>')
        web_lbl.setOpenExternalLinks(True)
        links_lay.addWidget(web_lbl)

        links_lay.addStretch()
        about_lay.addLayout(links_lay)

        root.addWidget(about_card)
        root.addSpacing(28)

        # ── Section 4 – Save Settings ──────────────────────────────────────
        save_lay = QHBoxLayout()
        self.btn_save = QPushButton("  Save Settings")
        self.btn_save.setFixedSize(160, 40)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 13px;
                border-radius: 8px;
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
            QPushButton:hover {
                background-color: palette(link);
            }
        """)
        
        try:
            import qtawesome as qta
            self.btn_save.setIcon(qta.icon("fa5s.save", color="white"))
        except Exception:
            pass
            
        self.btn_save.clicked.connect(self.save_requested.emit)
        save_lay.addWidget(self.btn_save)
        save_lay.addStretch()
        
        root.addLayout(save_lay)
        root.addStretch()

        scroll_lay = QVBoxLayout(self)
        scroll_lay.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(inner)
        scroll_lay.addWidget(scroll)

    # ── handlers ──────────────────────────────────────────────────────────────

    def _on_theme_clicked(self, btn: "_ThemeOptionButton") -> None:
        self.theme_changed.emit(btn.theme_key)
        self._sync_theme_buttons()

    def _sync_theme_buttons(self) -> None:
        current = ThemeManager.current()
        for btn in (self._btn_dark, self._btn_light):
            btn.set_active(btn.theme_key == current)


# ─── Helper widgets ───────────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        "font-size: 11px; font-weight: 700; letter-spacing: 1.2px; "
        "color: palette(mid);"
    )
    return lbl


class _Card(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.setStyleSheet("")          # inherit from theme


class _ThemeOptionButton(QFrame):
    """Clickable theme card with icon + label."""

    clicked: Signal = Signal()

    def __init__(self, label: str, icon_name: str, theme_key: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.theme_key = theme_key
        self._active = False

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(130, 80)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_name = icon_name
        lay.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(label)
        self._text_lbl.setAlignment(Qt.AlignCenter)
        self._text_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        lay.addWidget(self._text_lbl)

        self._refresh_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._refresh_style()

    def _refresh_style(self) -> None:
        try:
            import qtawesome as qta
            p = ThemeManager.palette()
            color = p["accent"] if self._active else p["icon_color"]
            pix = qta.icon(self._icon_name, color=color).pixmap(24, 24)
            self._icon_lbl.setPixmap(pix)
        except Exception:
            pass

        p = ThemeManager.palette()
        if self._active:
            self.setStyleSheet(
                f"QFrame {{ background-color: {p['bg_selected']};"
                f" border: 2px solid {p['accent']};"
                f" border-radius: 10px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background-color: {p['bg_card']};"
                f" border: 1px solid {p['border']};"
                f" border-radius: 10px; }}"
            )

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self.clicked.emit()
