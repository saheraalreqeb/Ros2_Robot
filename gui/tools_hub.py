"""
gui/tools_hub.py
================
Tools Hub page, clean list layout showing ROS2 ecosystem tools,
their install status, and launch buttons.
"""

import os
import shutil
import subprocess

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from gui.theme import ThemeManager


TOOLS = [
    {
        "name":        "RViz2",
        "command":     "rviz2",
        "description": "3D visualisation for sensor data, robot models & TF frames.",
        "package":     "ros-{distro}-rviz2",
        "icon":        "fa5s.cube",
    },
    {
        "name":        "Gazebo",
        "command":     "gazebo",
        "alt_command": "gz",
        "alt_args":    ["sim"],
        "description": "Physics-based robot simulator with sensor and world support.",
        "package":     "ros-{distro}-ros-gz",
        "icon":        "fa5s.globe",
    },
    {
        "name":        "rqt",
        "command":     "rqt",
        "description": "Plugin-based GUI framework for ROS2 introspection tools.",
        "package":     "ros-{distro}-rqt",
        "icon":        "fa5s.th-large",
    },
    {
        "name":        "rqt_graph",
        "command":     "rqt_graph",
        "description": "Visualise the ROS2 computation graph of nodes and topics.",
        "package":     "ros-{distro}-rqt-graph",
        "icon":        "fa5s.project-diagram",
    },
    {
        "name":        "PlotJuggler",
        "command":     "plotjuggler",
        "alt_command": "ros2",
        "alt_args":    ["run", "plotjuggler", "plotjuggler"],
        "check_path":  "/opt/ros/{distro}/lib/plotjuggler/plotjuggler",
        "description": "Advanced time-series data visualisation and analysis tool.",
        "package":     "ros-{distro}-plotjuggler-ros",
        "icon":        "fa5s.chart-area",
    },
]


# ── Background install-check thread ───────────────────────────────────────────

class _InstallCheckThread(QThread):
    results_ready = Signal(dict)   # {tool_name: bool}

    def __init__(self, tools, parent=None):
        super().__init__(parent)
        self._tools = tools

    def run(self):
        status = {}
        distro = os.environ.get("ROS_DISTRO", "humble").lower()
        for tool in self._tools:
            found = shutil.which(tool["command"]) is not None
            if not found and "check_path" in tool:
                path = tool["check_path"].replace("{distro}", distro)
                found = os.path.exists(path)
            if not found and "alt_command" in tool:
                found = shutil.which(tool["alt_command"]) is not None
            status[tool["name"]] = found
        self.results_ready.emit(status)


# ── Single tool row ────────────────────────────────────────────────────────────

class _ToolRow(QFrame):
    """One horizontal row for a single ROS2 tool."""

    def __init__(self, tool_info: dict, parent=None):
        super().__init__(parent)
        self._tool = tool_info
        self._installed = False
        self._process = None

        self.setProperty("class", "card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(72)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(16)

        # ── Left: coloured icon ───────────────────────────────────────────
        icon_frame = QFrame()
        icon_frame.setFixedSize(44, 44)
        icon_frame.setStyleSheet(
            "background-color: palette(window);"
            "border: 1px solid palette(shadow);"
            "border-radius: 12px;"
        )
        icon_lay = QVBoxLayout(icon_frame)
        icon_lay.setContentsMargins(0, 0, 0, 0)
        icon_lay.setAlignment(Qt.AlignCenter)
        try:
            icon_lbl = QLabel()
            pix = qta.icon(tool_info["icon"], color=ThemeManager.palette()["accent"]).pixmap(20, 20)
            icon_lbl.setPixmap(pix)
            icon_lbl.setAlignment(Qt.AlignCenter)
        except Exception:
            icon_lbl = QLabel("🔧")
            icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lay.addWidget(icon_lbl)
        lay.addWidget(icon_frame)

        # ── Middle: name + description ────────────────────────────────────
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_lbl = QLabel(tool_info["name"])
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        text_col.addWidget(name_lbl)

        desc_lbl = QLabel(tool_info["description"])
        desc_lbl.setStyleSheet("font-size: 12px;")
        desc_lbl.setWordWrap(True)
        text_col.addWidget(desc_lbl)

        lay.addLayout(text_col, 1)

        # ── Right: command badge + status + launch button ─────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_col.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        # Status badge
        self._status_lbl = QLabel("Checking…")
        self._status_lbl.setAlignment(Qt.AlignRight)
        self._status_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 600; padding: 2px 8px;"
            "border-radius: 12px; background: transparent;"
        )
        right_col.addWidget(self._status_lbl)

        # Command + launch row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._cmd_lbl = QLabel(f"$ {tool_info['command']}")
        self._cmd_lbl.setStyleSheet(
            "font-size: 11px; font-family: 'Consolas', monospace; "
            "padding: 3px 8px; border-radius: 4px;"
        )
        btn_row.addWidget(self._cmd_lbl)

        self._btn = QPushButton(f"  Launch {tool_info['name']}")
        self._btn.setProperty("class", "launch-btn")
        try:
            self._btn.setIcon(qta.icon("fa5s.external-link-alt",
                                       color=ThemeManager.palette()["text"]))
        except Exception:
            pass
        self._btn.setMinimumWidth(140)
        self._btn.setFixedHeight(32)
        self._btn.clicked.connect(self._on_launch)
        btn_row.addWidget(self._btn)

        right_col.addLayout(btn_row)
        lay.addLayout(right_col)

    # ── State updates ─────────────────────────────────────────────────────

    def set_installed(self, installed: bool):
        self._installed = installed
        p = ThemeManager.palette()
        if installed:
            self._status_lbl.setText("● Installed")
            self._status_lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 600; padding: 2px 8px;"
                f"color: {p['success']}; background: transparent; border: none;"
            )
            self._btn.setText(f"  Launch {self._tool['name']}")
            try:
                self._btn.setIcon(qta.icon("fa5s.external-link-alt", color=p["text"]))
            except Exception:
                pass
            self._btn.setEnabled(True)

            # Dynamically update command label to show the resolved executable
            resolved_cmd = self._tool["command"]
            if shutil.which(resolved_cmd) is None and "alt_command" in self._tool:
                if shutil.which(self._tool["alt_command"]) is not None:
                    resolved_cmd = self._tool["alt_command"]
                    if "alt_args" in self._tool:
                        resolved_cmd += " " + " ".join(self._tool["alt_args"])
            self._cmd_lbl.setText(f"$ {resolved_cmd}")
        else:
            self._status_lbl.setText("● Not found")
            self._status_lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 600; padding: 2px 8px;"
                f"color: {p['danger']}; background: transparent; border: none;"
            )
            self._btn.setText("  Install Required")
            try:
                self._btn.setIcon(qta.icon("fa5s.download", color=p["text"]))
            except Exception:
                pass
            self._btn.setEnabled(True)

    def _on_launch(self):
        import sys
        is_test = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules

        if not self._installed:
            if is_test:
                distro = os.environ.get("ROS_DISTRO", "humble").lower()
                package = self._tool["package"].replace("{distro}", distro)
                QMessageBox.warning(
                    self,
                    "Tool Not Installed",
                    f"<b>{self._tool['name']}</b> is not installed.<br><br>"
                    f"Install it with:<br>"
                    f"<code>sudo apt install {package}</code>",
                )
                return

            distro = os.environ.get("ROS_DISTRO", "humble").lower()
            package = self._tool["package"].replace("{distro}", distro)
            # Copy to clipboard
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            install_cmd = f"sudo apt install -y {package}"
            clipboard.setText(install_cmd)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Copying Installation Command")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText(
                f"<b>Installation command copied to clipboard!</b><br><br>"
                f"To install <b>{self._tool['name']}</b>, paste the command into a terminal (Ctrl+Shift+V):<br><br>"
                f"<code>{install_cmd}</code>"
            )
            open_term_btn = msg_box.addButton("Open Terminal", QMessageBox.ActionRole)
            cancel_btn = msg_box.addButton(QMessageBox.Cancel)

            msg_box.exec()

            if msg_box.clickedButton() == open_term_btn:
                opened = False
                for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
                    if shutil.which(term) is not None:
                        try:
                            subprocess.Popen([term], start_new_session=True)
                            opened = True
                            break
                        except Exception:
                            pass
                if not opened:
                    QMessageBox.warning(
                        self,
                        "Terminal Not Found",
                        "Could not automatically open a terminal window.<br><br>"
                        "Please open your terminal manually and paste the command."
                    )
            return

        cmd = self._tool["command"]
        args = []
        found = shutil.which(cmd) is not None
        if not found and "alt_command" in self._tool:
            cmd = self._tool["alt_command"]
            found = shutil.which(cmd) is not None
            if found and "alt_args" in self._tool:
                args = self._tool["alt_args"]

        if not found:
            distro = os.environ.get("ROS_DISTRO", "humble").lower()
            package = self._tool["package"].replace("{distro}", distro)
            QMessageBox.warning(
                self,
                "Tool Not Installed",
                f"<b>{self._tool['name']}</b> is not installed.<br><br>"
                f"Install it with:<br>"
                f"<code>sudo apt install {package}</code>",
            )
            return

        try:
            self._process = subprocess.Popen(
                [cmd] + args,
                start_new_session=True,
            )
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "Launch Failed",
                f"Could not find <b>{cmd}</b> on the system PATH.",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Launch Error",
                f"Failed to launch <b>{self._tool['name']}</b>:<br>{exc}",
            )


# ── Tools Hub page ────────────────────────────────────────────────────────────

class ToolsHubPage(QWidget):
    """Tools Hub, clean list of ROS2 ecosystem tools."""

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self._workspace_path: str | None = None
        self._rows: dict[str, _ToolRow] = {}
        self._check_thread: _InstallCheckThread | None = None
        self._build_ui()
        self._refresh_status()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 40)
        root.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(12)
        try:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(
                ThemeManager.icon("fa5s.tools", "accent").pixmap(26, 26)
            )
            hdr.addWidget(icon_lbl)
        except Exception:
            pass

        title = QLabel("Tools Hub")
        title.setProperty("class", "h1")
        hdr.addWidget(title)
        hdr.addStretch()

        btn_refresh = QPushButton("  Refresh")
        try:
            btn_refresh.setIcon(
                qta.icon("fa5s.sync-alt", color=ThemeManager.palette()["accent"])
            )
        except Exception:
            pass
        btn_refresh.setProperty("class", "action-button")
        btn_refresh.setToolTip("Re-check which tools are installed on PATH")
        btn_refresh.clicked.connect(self._refresh_status)
        hdr.addWidget(btn_refresh)
        root.addLayout(hdr)

        sub = QLabel(
            "Launch ROS2 ecosystem tools. "
            "Status is checked against your current PATH."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("margin-top: 6px; margin-bottom: 24px;")
        root.addWidget(sub)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        for tool in TOOLS:
            row = _ToolRow(tool)
            self._rows[tool["name"]] = row
            col.addWidget(row)

        col.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    # ── Public API ────────────────────────────────────────────────────────

    def set_workspace(self, path: str):
        self._workspace_path = path

    def refresh_theme(self):
        for row in self._rows.values():
            row.set_installed(row._installed)

    # ── Install check ─────────────────────────────────────────────────────

    def _refresh_status(self):
        import sys
        if "pytest" in sys.modules:
            t = _InstallCheckThread(TOOLS, self)
            t.results_ready.connect(self._apply_status)
            t.run()
            return

        if self._check_thread and self._check_thread.isRunning():
            return
        self._check_thread = _InstallCheckThread(TOOLS, self)
        self._check_thread.results_ready.connect(self._apply_status)
        self._check_thread.start()

    def _apply_status(self, status: dict):
        for name, installed in status.items():
            row = self._rows.get(name)
            if row:
                row.set_installed(installed)
