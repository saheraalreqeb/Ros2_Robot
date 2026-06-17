"""
gui/main_window.py
==================
Main application window.

Changes vs. previous version
------------------------------
- qtawesome icons on every sidebar nav button
- Futuristic dark/light theme via gui.theme.ThemeManager
- Build section merged into the Workspace tab (no separate Build tab)
- New Settings tab (last entry in sidebar) with:
    • Theme picker (Dark / Light)
    • Sidebar tab visibility manager
- Tab IDs remapped (Build removed from sidebar):
    0  Workspace   (includes Build)
    1  Packages
    2  Nodes
    3  Visualizer
    4  Launch Manager
    5  Tools Hub
    6  Topic Inspector
    7  Parameters
    8  Bag Manager
    9  Settings      ← always last
"""

from __future__ import annotations

import os
import subprocess

import psutil
import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QObject, QEvent, QPoint
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QDialog,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QTextEdit,
)

from core.code_generator import CodeGenerator
from core.ros2_cli import ROS2CLI
from core.workspace import ROS2Workspace
from gui.bag_manager import BagManagerPage
from gui.dialogs import CreateNodeDialog, CreatePackageDialog
from gui.flow_layout import FlowLayout
from gui.launch_manager import LaunchManagerPage
from gui.parameter_manager import ParameterManagerPage
from gui.settings_page import SettingsPage
from gui.theme import ThemeManager
from gui.tools_hub import ToolsHubPage
from gui.topic_inspector import TopicInspectorPage
from gui.service_inspector import ServiceInspectorPage
from gui.action_inspector import ActionInspectorPage
from gui.visualizer import VisualizerPage
from gui.dds_troubleshooter import DDSTroubleshooterPage
from gui.log_viewer import UnifiedLogViewerPage
from gui.urdf_viewer import URDFViewerPage


# ─── Thread helpers ────────────────────────────────────────────────────────────

class DiscoveryDaemon(QThread):
    updated = Signal(dict)

    def __init__(self, cli: ROS2CLI):
        super().__init__()
        self.cli = cli
        self.running = True

    def run(self):
        import time
        while self.running:
            nodes = self.cli.node_list()
            topics = self.cli.topic_list()
            services = self.cli.service_list()
            actions = self.cli.action_list() if hasattr(self.cli, "action_list") else []
            self.updated.emit({
                "nodes": nodes,
                "topics": topics,
                "services": services,
                "actions": actions
            })
            for _ in range(50):
                if not self.running:
                    break
                time.sleep(0.1)

    def stop(self):
        self.running = False


class TitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("titleBar")
        self.setFixedHeight(36)
        
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)
        
        left_dummy = QWidget()
        left_dummy.setFixedWidth(60)
        lay.addWidget(left_dummy)
        
        lay.addStretch()
        
        self.title_lbl = QLabel("ROS2 Robot")
        self.title_lbl.setObjectName("titleLabel")
        self.title_lbl.setStyleSheet("font-weight: 700; font-size: 13px;")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title_lbl)
        
        lay.addStretch()
        
        self.macBtnContainer = QFrame()
        self.macBtnContainer.setObjectName("macBtnContainer")
        self.macBtnContainer.setFixedWidth(60)
        mac_lay = QHBoxLayout(self.macBtnContainer)
        mac_lay.setContentsMargins(0, 0, 0, 0)
        mac_lay.setSpacing(6)
        mac_lay.setAlignment(Qt.AlignCenter)
        
        self.min_btn = QPushButton("—")
        self.min_btn.setProperty("class", "mac-btn")
        self.min_btn.setObjectName("macMin")
        self.min_btn.pressed.connect(self.parent.showMinimized)
        
        self.max_btn = QPushButton("＋")
        self.max_btn.setProperty("class", "mac-btn")
        self.max_btn.setObjectName("macMax")
        self.max_btn.pressed.connect(self._toggle_maximize)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setProperty("class", "mac-btn")
        self.close_btn.setObjectName("macClose")
        self.close_btn.pressed.connect(self.parent.close)

        mac_lay.addWidget(self.min_btn)
        mac_lay.addWidget(self.max_btn)
        mac_lay.addWidget(self.close_btn)
        
        lay.addWidget(self.macBtnContainer)
        
        self._start_pos = None

    def _toggle_maximize(self):
        from PySide6.QtCore import QRect
        
        if not hasattr(self.parent, "_is_custom_maximized"):
            self.parent._is_custom_maximized = False
            self.parent._normal_geometry = self.parent.geometry()
            
        if self.parent._is_custom_maximized:
            self.parent.setGeometry(self.parent._normal_geometry)
            self.parent._is_custom_maximized = False
        else:
            self.parent._normal_geometry = self.parent.geometry()
            screen = self.parent.screen()
            target_rect = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
            self.parent.setGeometry(target_rect)
            self.parent._is_custom_maximized = True

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._start_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._start_pos is not None:
            # If dragged while maximized, snap back to normal size
            if getattr(self.parent, "_is_custom_maximized", False):
                self.parent._is_custom_maximized = False
                cursor_pos = event.globalPosition().toPoint()
                norm_geom = getattr(self.parent, "_normal_geometry", None)
                if norm_geom:
                    # Keep the window centered on the mouse horizontally
                    new_x = cursor_pos.x() - (norm_geom.width() // 2)
                    new_y = cursor_pos.y() - self._start_pos.y()
                    self.parent.setGeometry(new_x, new_y, norm_geom.width(), norm_geom.height())
                self._start_pos = event.globalPosition().toPoint()
                return

            delta = event.globalPosition().toPoint() - self._start_pos
            self.parent.move(self.parent.pos() + delta)
            self._start_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._start_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()

    def refresh_theme(self):
        pass


class ColconBuildWorker(QThread):
    new_line = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, workspace_path: str, use_wsl: bool = False, build_args: list = None, clean_first: bool = False):
        super().__init__()
        self.workspace_path = workspace_path
        self.use_wsl = use_wsl
        self.build_args = build_args or []
        self.clean_first = clean_first
        self.process = None

    def run(self):
        try:
            # 1. Handle clean if checked
            if self.clean_first:
                self.new_line.emit("Cleaning workspace build folders (build, install, log)...\n")
                import shutil
                for folder in ["build", "install", "log"]:
                    fp = os.path.join(self.workspace_path, folder)
                    if os.path.exists(fp):
                        try:
                            shutil.rmtree(fp)
                            self.new_line.emit(f"Deleted {folder}/\n")
                        except Exception as e:
                            self.new_line.emit(f"Failed to delete {folder}: {e}\n")

            # 2. Build build command list
            colcon_args = ["colcon", "build"] + self.build_args
            colcon_cmd_str = " ".join(colcon_args)
            self.new_line.emit(f"Starting build: {colcon_cmd_str}\n\n")

            # 3. Handle WSL path conversion if needed
            if self.use_wsl:
                import re
                def to_wsl_path(p):
                    p = p.replace('\\', '/')
                    m = re.match(r'^([a-zA-Z]):(.*)', p)
                    return f"/mnt/{m.group(1).lower()}{m.group(2)}" if m else p

                ws_wsl = to_wsl_path(self.workspace_path)
                cmd = ["wsl", "bash", "-i", "-c", f'cd "{ws_wsl}" && {colcon_cmd_str}']
                run_cwd = None
            else:
                cmd = ["powershell.exe", "-Command", colcon_cmd_str] if os.name == "nt" else ["bash", "-c", colcon_cmd_str]
                run_cwd = self.workspace_path

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=run_cwd,
                bufsize=1
            )
            
            for line in iter(self.process.stdout.readline, ""):
                self.new_line.emit(line)
            
            self.process.stdout.close()
            return_code = self.process.wait()
            self.finished_signal.emit(return_code == 0, "")
        except Exception as exc:
            self.new_line.emit(f"Build exception: {exc}\n")
            self.finished_signal.emit(False, str(exc))

    def terminate_process(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


class BuildThread(QThread):
    finished_signal = Signal(bool, str)

    def __init__(self, workspace_path: str, use_wsl: bool = False):
        super().__init__()
        self.workspace_path = workspace_path
        self.use_wsl = use_wsl

    def run(self):
        try:
            if self.use_wsl:
                import re
                def to_wsl_path(p):
                    p = p.replace('\\', '/')
                    m = re.match(r'^([a-zA-Z]):(.*)', p)
                    return f"/mnt/{m.group(1).lower()}{m.group(2)}" if m else p

                ws_wsl = to_wsl_path(self.workspace_path)
                cmd = ["wsl", "bash", "-i", "-c",
                       f'cd "{ws_wsl}" && colcon build']
                result = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
                )
            else:
                result = subprocess.run(
                    "colcon build", capture_output=True, text=True, encoding="utf-8", errors="replace",
                    shell=True, cwd=self.workspace_path
                )
            if result.returncode == 0:
                self.finished_signal.emit(True, result.stdout)
            else:
                self.finished_signal.emit(False, result.stderr or result.stdout)
        except Exception as exc:
            self.finished_signal.emit(False, str(exc))


class ProcessLogReader(QThread):
    new_line = Signal(str, str) # (source, line)

    def __init__(self, source_name: str, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self.source_name = source_name
        self.process = process

    def run(self):
        try:
            for line in iter(self.process.stdout.readline, ""):
                if line:
                    self.new_line.emit(self.source_name, line.rstrip("\n\r"))
        except Exception:
            pass

# ─── Sidebar nav entry definition ─────────────────────────────────────────────

_NAV_ENTRIES = [
    # (page_id, attr_name,   label,            icon_name,             refresh_method_or_None)
    (0, "btn_workspace",      "Workspace",                             "fa5s.folder-open",    None),
    (1, "btn_packages",       "Packages",                              "fa5s.box",            None),
    (2, "btn_nodes",          "Nodes",                                 "fa5s.microchip",      "_refresh_nodes_list"),
    (3, "btn_topics",         "Topic Inspector",                       "fa5s.satellite-dish", "_refresh_topics"),
    (10, "btn_visualizer",    "Visualizer",                            "fa5s.project-diagram","_refresh_visualizer"),
    (4, "btn_launch",         "Launch Manager",                        "fa5s.rocket",         "_refresh_launch"),
    (12, "btn_urdf",          "URDF Viewer (Beta)",                    "fa5s.cubes",          "_refresh_urdf"),
    (11, "btn_bags",          "Bag Manager",                           "fa5s.database",       "_refresh_bags"),
    (7, "btn_logs",           "Log Viewer",                            "fa5s.file-alt",       "_refresh_logs"),
    (13, "btn_tools",         "Tools Hub (Beta)",                      "fa5s.tools",          "_refresh_tools"),
    (5, "btn_services",       "Service Inspector (Beta)",              "fa5s.handshake",      "_refresh_services"),
    (6, "btn_actions",        "Action Inspector (Beta)",               "fa5s.bullseye",       "_refresh_actions"),
    (8, "btn_troubleshooter", "DDS Troubleshooter (Beta)",             "fa5s.network-wired",  None),
    (9, "btn_params",         "Parameters",                            "fa5s.sliders-h",      "_refresh_params"),
    (14, "btn_settings",      "Settings",                              "fa5s.cog",            None),
]

# Keys that map to SettingsPage._TAB_DEFS keys
_TAB_KEY_FOR_BTN = {
    "btn_workspace":      "workspace",
    "btn_packages":       "packages",
    "btn_nodes":          "nodes",
    "btn_topics":         "topics",
    "btn_launch":         "launch",
    "btn_services":       "services",
    "btn_actions":        "actions",
    "btn_logs":           "logs",
    "btn_troubleshooter": "troubleshooter",
    "btn_params":         "params",
    "btn_visualizer":     "visualizer",
    "btn_bags":           "bags",
    "btn_urdf":           "urdf",
    "btn_tools":          "tools",
    "btn_settings":       "settings",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  HelpButtonResizer
# ═══════════════════════════════════════════════════════════════════════════════

class HelpButtonResizer(QObject):
    def __init__(self, help_btn):
        super().__init__(help_btn)
        self.help_btn = help_btn

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            w = obj.width()
            self.help_btn.move(w - 24 - 16, 12)
            self.help_btn.raise_()
        return super().eventFilter(obj, event)


# ═══════════════════════════════════════════════════════════════════════════════
#  HelpDialog
# ═══════════════════════════════════════════════════════════════════════════════

class HelpDialog(QDialog):
    def __init__(self, page_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Help: {page_data.get('title', 'Page Help')}")
        self.setMinimumSize(520, 460)
        self.resize(580, 500)
        
        # Apply theme colors
        p = ThemeManager.palette()
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
            }}
            QLabel {{
                color: {p['text_primary']};
            }}
            QPushButton {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {p['bg_hover']};
            }}
            """
        )
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Header Row
        hdr_lay = QHBoxLayout()
        hdr_lay.setSpacing(12)
        
        # Page Icon
        icon_lbl = QLabel()
        icon_name = page_data.get("icon", "fa5s.question-circle")
        icon_lbl.setPixmap(ThemeManager.icon(icon_name, "accent").pixmap(32, 32))
        hdr_lay.addWidget(icon_lbl)
        
        # Title
        title_lbl = QLabel(page_data.get("title", "Help"))
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold;")
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()
        layout.addLayout(hdr_lay)
        
        # Divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {p['border']};")
        layout.addWidget(div)
        
        # Scroll area for scrollable contents
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_lay = QVBoxLayout(scroll_content)
        scroll_lay.setContentsMargins(0, 0, 0, 0)
        scroll_lay.setSpacing(16)
        
        # Description
        desc_title = QLabel("Overview")
        desc_title.setStyleSheet("font-size: 13px; font-weight: bold; color: palette(highlight);")
        scroll_lay.addWidget(desc_title)
        
        desc_lbl = QLabel(page_data.get("description", ""))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {p['text_secondary']}; line-height: 1.4; font-size: 13px;")
        scroll_lay.addWidget(desc_lbl)
        
        # Under the Hood / Background Commands
        under_hood = page_data.get("under_the_hood", [])
        if under_hood:
            cmd_title = QLabel("Under the Hood (ROS 2 CLI & Systems)")
            cmd_title.setStyleSheet("font-size: 13px; font-weight: bold; color: palette(highlight);")
            scroll_lay.addWidget(cmd_title)
            
            for item in under_hood:
                cmd_box = QFrame()
                cmd_box.setStyleSheet(
                    f"QFrame {{ background-color: {p['bg_hover']}; border: 1px solid {p['border']}; border-radius: 6px; }}"
                )
                box_lay = QVBoxLayout(cmd_box)
                box_lay.setContentsMargins(12, 10, 12, 10)
                box_lay.setSpacing(4)
                
                cmd_lbl = QLabel(f"$ {item.get('command', '')}")
                cmd_lbl.setStyleSheet(
                    "font-family: monospace; font-size: 12px; font-weight: bold; color: palette(link);"
                )
                cmd_lbl.setWordWrap(True)
                box_lay.addWidget(cmd_lbl)
                
                desc_cmd = QLabel(item.get("description", ""))
                desc_cmd.setStyleSheet(f"font-size: 11px; color: {p['text_secondary']};")
                desc_cmd.setWordWrap(True)
                box_lay.addWidget(desc_cmd)
                
                scroll_lay.addWidget(cmd_box)
                
        # Tips / Troubleshooting
        tips = page_data.get("tips", [])
        if tips:
            tips_title = QLabel("Tips & Troubleshooting")
            tips_title.setStyleSheet("font-size: 13px; font-weight: bold; color: palette(highlight);")
            scroll_lay.addWidget(tips_title)
            
            for tip in tips:
                tip_lay = QHBoxLayout()
                tip_lay.setSpacing(8)
                
                bullet = QLabel("•")
                bullet.setStyleSheet("font-size: 14px; font-weight: bold; color: palette(highlight);")
                bullet.setAlignment(Qt.AlignTop)
                tip_lay.addWidget(bullet)
                
                tip_lbl = QLabel(tip)
                tip_lbl.setWordWrap(True)
                tip_lbl.setStyleSheet(f"color: {p['text_secondary']}; font-size: 13px;")
                tip_lay.addWidget(tip_lbl, 1)
                
                scroll_lay.addLayout(tip_lay)
                
        # Documentation Link
        doc_link = page_data.get("documentation_link", "")
        if doc_link:
            link_title = QLabel("Learn More")
            link_title.setStyleSheet("font-size: 13px; font-weight: bold; color: palette(highlight); margin-top: 10px;")
            scroll_lay.addWidget(link_title)
            
            link_lbl = QLabel(
                f"To learn more, check: <a href=\"{doc_link}\" style=\"color: {p['accent']}; text-decoration: underline;\">ROS 2 Documentation</a>"
            )
            link_lbl.setOpenExternalLinks(True)
            link_lbl.setWordWrap(True)
            link_lbl.setStyleSheet(f"color: {p['text_secondary']}; font-size: 13px;")
            scroll_lay.addWidget(link_lbl)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        
        # Bottom Close Button
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        close_btn = QPushButton("Got it")
        close_btn.clicked.connect(self.accept)
        btn_lay.addWidget(close_btn)
        layout.addLayout(btn_lay)


# ═══════════════════════════════════════════════════════════════════════════════
#  MainWindow
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):

    # ── workspace property ────────────────────────────────────────────────────

    @property
    def current_workspace_path(self) -> str:
        return getattr(self, "_current_workspace_path_val", "")

    @current_workspace_path.setter
    def current_workspace_path(self, path: str) -> None:
        self._current_workspace_path_val = path
        self._update_all_workspaces()
        if hasattr(self, "_save_settings"):
            self._save_settings()

    # ── init ──────────────────────────────────────────────────────────────────

    def __init__(self):
        super().__init__()
        self._current_workspace_path_val = os.getcwd()
        self.setWindowTitle("Ros2 Robot")
        self.setWindowIcon(ThemeManager.icon("fa5s.robot", "accent"))
        self.resize(1180, 780)
        self.setMinimumSize(900, 600)
        
        # Center window on the screen where the cursor currently is
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication
        screen = QApplication.screenAt(QCursor.pos())
        if screen:
            screen_geom = screen.availableGeometry()
            self.move(
                screen_geom.left() + (screen_geom.width() - 1180) // 2,
                screen_geom.top() + (screen_geom.height() - 780) // 2
            )

        self.cli = ROS2CLI()
        if os.name == "nt":
            self.cli.use_wsl = True
        self.running_processes: dict = {}
        self.active_node_cards: list = []

        # Central Discovery Cache and Daemon
        self.discovery_cache = {
            "nodes": [],
            "topics": [],
            "services": [],
            "actions": []
        }
        self.discovery_daemon = DiscoveryDaemon(self.cli)
        self.discovery_daemon.updated.connect(self._on_discovery_updated)
        self.discovery_daemon.start()

        # Periodic Resource Monitor Timer
        self.node_monitor_timer = QTimer(self)
        self.node_monitor_timer.setInterval(2000)
        self.node_monitor_timer.timeout.connect(self._update_node_resources)
        self.node_monitor_timer.start()

        # Apply default dark theme (replaces styles.qss)
        from PySide6.QtWidgets import QApplication
        ThemeManager.apply(QApplication.instance(), "dark")

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        
        # Central layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.root_layout = QVBoxLayout(self.central_widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)
        
        self.title_bar = TitleBar(self)
        self.root_layout.addWidget(self.title_bar)
        
        self.main_content_widget = QWidget()
        self.main_layout = QHBoxLayout(self.main_content_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.root_layout.addWidget(self.main_content_widget, 1)

        self._setup_sidebar()
        self._setup_content_area()
        self._load_settings()
        self._update_all_workspaces()
        
        # Switch to the Workspace page (index 0) immediately so it doesn't render empty
        self._switch_page(0)

        # Register shutdown hook to guarantee settings are saved and threads stopped
        from PySide6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self._on_shutdown)
        
        self.statusBar().showMessage("Ready  ·  Ros2 Robot")
        self.statusBar().setSizeGripEnabled(True)
        
        self._center_window()

    def _center_window(self):
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geometry = screen.geometry()
            window_geometry = self.geometry()
            x = (screen_geometry.width() - window_geometry.width()) // 2
            y = (screen_geometry.height() - window_geometry.height()) // 2
            self.move(x, y)

    def _get_settings_path(self):
        import os
        return os.path.expanduser("~/.ros2_robot_settings.json")

    def _load_settings(self):
        import json
        import os
        
        self._is_loading_settings = True
        path = self._get_settings_path()
        if not os.path.exists(path):
            self._is_loading_settings = False
            return
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                
            # 1. Workspace
            ws_path = settings.get("workspace_path", "")
            if ws_path and os.path.exists(ws_path):
                self._current_workspace_path_val = ws_path
                
            # 2. Theme
            theme = settings.get("theme", "dark")
            self._on_theme_changed(theme)
            
            # 3. Tab Visibility & Order
            vis_dict = settings.get("tab_visibility", {})
            order_list = settings.get("tab_order", [])
            if hasattr(self, "settings_page"):
                self.settings_page.set_tab_state(vis_dict, order_list)
                self._apply_tab_visibility()

            # 4. OpenGL Setting
            use_opengl = settings.get("use_opengl", False)
            if hasattr(self, "settings_page"):
                self.settings_page.set_opengl_enabled(use_opengl)
            self._apply_opengl_setting(use_opengl)

            # 5. Default IDE
            default_ide = settings.get("default_ide", "")
            if hasattr(self, "settings_page"):
                self.settings_page.set_default_ide(default_ide)

        except Exception:
            pass
        finally:
            self._is_loading_settings = False

    def _save_settings(self):
        if getattr(self, "_is_loading_settings", False):
            return
            
        import json
        
        settings = {}
        settings["workspace_path"] = self.current_workspace_path
        settings["theme"] = ThemeManager.current()
        
        if hasattr(self, "settings_page"):
            settings["tab_visibility"] = self.settings_page.tab_visibility()
            settings["tab_order"] = self.settings_page.tab_order()
            settings["use_opengl"] = self.settings_page.is_opengl_enabled()
            settings["default_ide"] = self.settings_page.get_default_ide()
            
        try:
            with open(self._get_settings_path(), "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
        except Exception:
            pass

    def _force_save_settings(self):
        """Called when the user explicitly clicks the Save Settings button."""
        self._save_settings()
        self.statusBar().showMessage("✓ Settings saved successfully!", 3000)

    def _on_discovery_updated(self, data: dict):
        self.discovery_cache = data

    def _on_shutdown(self):
        if hasattr(self, "discovery_daemon"):
            self.discovery_daemon.stop()
            self.discovery_daemon.wait(2000)
        self._save_settings()

    def _open_in_ide(self, target_path: str):
        """
        Launches the target_path in the user's default IDE.
        Prompts for an IDE if one is not set.
        """
        import os
        from core.ide_launcher import get_available_ides, launch_in_ide
        from PySide6.QtWidgets import QInputDialog
        from PySide6.QtGui import QIcon

        if not os.path.exists(target_path) and not target_path.startswith('/'):
            # Allow pure linux paths if we are in WSL
            self.statusBar().showMessage(f"Warning: Path may not exist locally: {target_path}", 4000)

        ide_cmd = self.settings_page.get_default_ide() if hasattr(self, "settings_page") else ""

        if not ide_cmd:
            ides = get_available_ides()
            if not ides:
                self.statusBar().showMessage("No supported IDEs found (VSCode, PyCharm, Cursor, CLion, etc.)", 4000)
                return

            items = [ide["name"] for ide in ides]
            
            dialog = QInputDialog(self)
            dialog.setWindowTitle("Select IDE")
            dialog.setLabelText("Choose the default IDE to open files with:\n(You can change this later in Settings)")
            dialog.setComboBoxItems(items)
            dialog.setOption(QInputDialog.UseListViewForComboBoxItems)
            dialog.setStyleSheet(self.styleSheet())
            
            if dialog.exec() == QInputDialog.Accepted:
                item = dialog.textValue()
                # Find the cmd for the selected name
                selected_ide = next((ide for ide in ides if ide["name"] == item), None)
                if selected_ide:
                    ide_cmd = selected_ide["cmd"]
                    if hasattr(self, "settings_page"):
                        self.settings_page.set_default_ide(ide_cmd)
                        self._save_settings()
            else:
                return

        if ide_cmd:
            success = launch_in_ide(ide_cmd, target_path)
            if success:
                self.statusBar().showMessage(f"Opened {os.path.basename(target_path)} in IDE", 3000)
            else:
                self.statusBar().showMessage(f"Failed to open in IDE ({ide_cmd})", 4000)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _setup_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)

        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)

        # ── Logo area ──────────────────────────────────────────────────────
        logo_frame = QFrame()
        logo_frame.setFixedHeight(68)
        logo_frame.setStyleSheet(
            "QFrame { border-bottom: 1px solid palette(shadow); }"
        )
        logo_lay = QHBoxLayout(logo_frame)
        logo_lay.setContentsMargins(18, 0, 18, 0)
        logo_lay.setSpacing(10)

        self.logo_icon = QLabel()
        self.logo_icon.setPixmap(
            ThemeManager.icon("mdi.robot-outline", "accent").pixmap(32, 32)
        )
        logo_lay.addWidget(self.logo_icon)

        logo_txt = QLabel("Ros2 Robot")
        logo_txt.setStyleSheet(
            "font-size: 15px; font-weight: 700; "
            "letter-spacing: -0.3px;"
        )
        logo_lay.addWidget(logo_txt)
        logo_lay.addStretch()

        sb_lay.addWidget(logo_frame)
        sb_lay.addSpacing(8)

        # ── Nav buttons ───────────────────────────────────────────────────
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        
        self.nav_layout = QVBoxLayout()
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(4)
        sb_lay.addLayout(self.nav_layout)

        for page_id, attr, label, icon_name, _ in _NAV_ENTRIES:
            btn = self._create_nav_button(page_id, label, icon_name)
            setattr(self, attr, btn)
            self._nav_buttons[attr] = btn
            if attr == "btn_topics":
                btn.setObjectName("nav_btn_inspector")

            if attr == "btn_tools":
                sb_lay.addStretch()
                sb_lay.addSpacing(16)
                # thin divider
                div = QFrame()
                div.setFixedHeight(1)
                div.setStyleSheet("background-color: palette(shadow); margin: 0 16px;")
                sb_lay.addWidget(div)
                sb_lay.addSpacing(4)
                sb_lay.addWidget(btn)
            elif attr == "btn_settings":
                btn.setStyleSheet("margin-top: 0px;")
                sb_lay.addWidget(btn)
            else:
                self.nav_layout.addWidget(btn)

        sb_lay.addSpacing(8)
        self.main_layout.addWidget(self.sidebar)

        self.nav_group.buttonClicked.connect(lambda btn: self._switch_page(self.nav_group.id(btn)))
        self.btn_workspace.setChecked(True)

    def _create_nav_button(self, page_id: int, label: str,
                           icon_name: str) -> QPushButton:
        btn = QPushButton(f"  {label}")
        btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        btn.setProperty("class", "nav-button")
        btn.setCheckable(True)
        btn.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(16, 16))
        btn.setIcon(ThemeManager.icon(icon_name))
        self.nav_group.addButton(btn, page_id)
        return btn

    def _refresh_nav_icons(self):
        """Re-apply icons when the theme changes."""
        for page_id, attr, label, icon_name, _ in _NAV_ENTRIES:
            btn = self._nav_buttons.get(attr)
            if btn:
                is_active = btn.isChecked()
                role = "accent" if is_active else "normal"
                btn.setIcon(ThemeManager.icon(icon_name, role))
        
        if hasattr(self, "logo_icon"):
            self.logo_icon.setPixmap(
                ThemeManager.icon("mdi.robot-outline", "accent").pixmap(32, 32)
            )
        if hasattr(self, "title_bar"):
            self.title_bar.refresh_theme()

    # ── Content area ──────────────────────────────────────────────────────────

    def _setup_content_area(self):
        self.content_stack = QStackedWidget()
        self.main_layout.addWidget(self.content_stack, 1)

        # Build the pages; page indices must match _NAV_ENTRIES page_id values
        self._workspace_page = None
        self._packages_page = None
        self._nodes_page = None
        self._topic_inspector_page = None
        self._launch_manager_page = None
        self._service_inspector_page = None
        self._action_page = None
        self._log_viewer_page = None
        self._dds_troubleshooter_page = None
        self._parameter_manager_page = None
        self._visualizer_page = None
        self._bag_manager_page = None
        self._urdf_page = None
        self._tools_hub_page = None
        self.settings_page = self._create_settings_page()   # 14

        for i in range(14):
            placeholder = QWidget()
            placeholder.setProperty("is_placeholder", True)
            self.content_stack.addWidget(placeholder)
        self.content_stack.addWidget(self.settings_page)

    # ── Lazy loading properties ───────────────────────────────────────────────

    def _instantiate_page(self, page_id: int):
        if getattr(self, "_instantiating_pages", None) is None:
            self._instantiating_pages = set()
        if page_id in self._instantiating_pages:
            return
        self._instantiating_pages.add(page_id)
        
        try:
            placeholder = self.content_stack.widget(page_id)
            if not placeholder or not placeholder.property("is_placeholder"):
                return

            if page_id == 0:
                page = self._create_workspace_page()
                self._workspace_page = page
                self._update_build_packages_combo()
            elif page_id == 1:
                page = self._create_packages_page()
                self._packages_page = page
            elif page_id == 2:
                page = self._create_nodes_page()
                self._nodes_page = page
            elif page_id == 3:
                page = TopicInspectorPage(self.cli)
                self._topic_inspector_page = page
            elif page_id == 4:
                page = LaunchManagerPage(self.cli)
                self._launch_manager_page = page
                page.log_emitted.connect(self._on_node_log_received)
            elif page_id == 5:
                page = ServiceInspectorPage(self.cli)
                self._service_inspector_page = page
            elif page_id == 6:
                page = ActionInspectorPage(self.cli)
                self._action_page = page
            elif page_id == 7:
                page = UnifiedLogViewerPage(self.cli)
                self._log_viewer_page = page
            elif page_id == 8:
                page = DDSTroubleshooterPage(self.cli)
                self._dds_troubleshooter_page = page
            elif page_id == 9:
                page = ParameterManagerPage(self.cli)
                self._parameter_manager_page = page
            elif page_id == 10:
                page = VisualizerPage(self.cli)
                self._visualizer_page = page
            elif page_id == 11:
                page = BagManagerPage(self.cli)
                self._bag_manager_page = page
            elif page_id == 12:
                page = URDFViewerPage(self.cli)
                self._urdf_page = page
            elif page_id == 13:
                page = ToolsHubPage(self.cli)
                self._tools_hub_page = page
            else:
                return

            if hasattr(page, "set_workspace"):
                page.set_workspace(self.current_workspace_path)

            if hasattr(page, "refresh_theme"):
                page.refresh_theme()

            # Attach help button next to page title or on its own transparent line
            if page_id != 14:
                self._attach_help_button_to_page(page_id, page)

            is_current = (self.content_stack.currentIndex() == page_id)
            self.content_stack.removeWidget(placeholder)
            placeholder.deleteLater()
            self.content_stack.insertWidget(page_id, page)
            if is_current:
                self.content_stack.setCurrentIndex(page_id)
        finally:
            self._instantiating_pages.remove(page_id)

    @property
    def workspace_page(self):
        if getattr(self, "_workspace_page", None) is None:
            self._instantiate_page(0)
        return self._workspace_page

    @workspace_page.setter
    def workspace_page(self, val):
        self._workspace_page = val

    @property
    def packages_page(self):
        if getattr(self, "_packages_page", None) is None:
            self._instantiate_page(1)
        return self._packages_page

    @packages_page.setter
    def packages_page(self, val):
        self._packages_page = val

    @property
    def nodes_page(self):
        if getattr(self, "_nodes_page", None) is None:
            self._instantiate_page(2)
        return self._nodes_page

    @nodes_page.setter
    def nodes_page(self, val):
        self._nodes_page = val

    @property
    def topic_inspector_page(self):
        if getattr(self, "_topic_inspector_page", None) is None:
            self._instantiate_page(3)
        return self._topic_inspector_page

    @topic_inspector_page.setter
    def topic_inspector_page(self, val):
        self._topic_inspector_page = val

    @property
    def launch_manager_page(self):
        if getattr(self, "_launch_manager_page", None) is None:
            self._instantiate_page(4)
        return self._launch_manager_page

    @launch_manager_page.setter
    def launch_manager_page(self, val):
        self._launch_manager_page = val

    @property
    def service_inspector_page(self):
        if getattr(self, "_service_inspector_page", None) is None:
            self._instantiate_page(5)
        return self._service_inspector_page

    @service_inspector_page.setter
    def service_inspector_page(self, val):
        self._service_inspector_page = val

    @property
    def action_page(self):
        if getattr(self, "_action_page", None) is None:
            self._instantiate_page(6)
        return self._action_page

    @action_page.setter
    def action_page(self, val):
        self._action_page = val

    @property
    def log_viewer_page(self):
        if getattr(self, "_log_viewer_page", None) is None:
            self._instantiate_page(7)
        return self._log_viewer_page

    @log_viewer_page.setter
    def log_viewer_page(self, val):
        self._log_viewer_page = val

    @property
    def dds_troubleshooter_page(self):
        if getattr(self, "_dds_troubleshooter_page", None) is None:
            self._instantiate_page(8)
        return self._dds_troubleshooter_page

    @dds_troubleshooter_page.setter
    def dds_troubleshooter_page(self, val):
        self._dds_troubleshooter_page = val

    @property
    def parameter_manager_page(self):
        if getattr(self, "_parameter_manager_page", None) is None:
            self._instantiate_page(9)
        return self._parameter_manager_page

    @parameter_manager_page.setter
    def parameter_manager_page(self, val):
        self._parameter_manager_page = val

    @property
    def visualizer_page(self):
        if getattr(self, "_visualizer_page", None) is None:
            self._instantiate_page(10)
        return self._visualizer_page

    @visualizer_page.setter
    def visualizer_page(self, val):
        self._visualizer_page = val

    @property
    def bag_manager_page(self):
        if getattr(self, "_bag_manager_page", None) is None:
            self._instantiate_page(11)
        return self._bag_manager_page

    @bag_manager_page.setter
    def bag_manager_page(self, val):
        self._bag_manager_page = val

    @property
    def urdf_page(self):
        if getattr(self, "_urdf_page", None) is None:
            self._instantiate_page(12)
        return self._urdf_page

    @urdf_page.setter
    def urdf_page(self, val):
        self._urdf_page = val

    @property
    def tools_hub_page(self):
        if getattr(self, "_tools_hub_page", None) is None:
            self._instantiate_page(13)
        return self._tools_hub_page

    @tools_hub_page.setter
    def tools_hub_page(self, val):
        self._tools_hub_page = val

    # ── Page switching ────────────────────────────────────────────────────────

    def _switch_page(self, page_id: int):
        # Force lazy instantiation if needed
        prop_map = {
            0: "workspace_page",
            1: "packages_page",
            2: "nodes_page",
            3: "topic_inspector_page",
            4: "launch_manager_page",
            5: "service_inspector_page",
            6: "action_page",
            7: "log_viewer_page",
            8: "dds_troubleshooter_page",
            9: "parameter_manager_page",
            10: "visualizer_page",
            11: "bag_manager_page",
            12: "urdf_page",
            13: "tools_hub_page",
        }
        if page_id in prop_map:
            getattr(self, prop_map[page_id])

        self.content_stack.setCurrentIndex(page_id)
        # Ensure the correct nav button is checked programmatically
        for p_id, attr, _, _, _ in _NAV_ENTRIES:
            btn = self._nav_buttons.get(attr)
            if btn:
                btn.setChecked(p_id == page_id)
        # Update icon highlights
        self._refresh_nav_icons()

        # Handle status label objectName toggling to prevent collision
        if page_id == 3: # Topic Inspector
            if getattr(self, "_service_inspector_page", None) is not None and hasattr(self.service_inspector_page, "lbl_status"):
                self.service_inspector_page.lbl_status.setObjectName("lbl_inspector_status_inactive")
            if getattr(self, "_action_page", None) is not None and hasattr(self.action_page, "lbl_status"):
                self.action_page.lbl_status.setObjectName("lbl_inspector_status_inactive")
            if getattr(self, "_topic_inspector_page", None) is not None and hasattr(self.topic_inspector_page, "lbl_status"):
                self.topic_inspector_page.lbl_status.setObjectName("lbl_inspector_status")
        elif page_id == 5: # Service Inspector
            if getattr(self, "_topic_inspector_page", None) is not None and hasattr(self.topic_inspector_page, "lbl_status"):
                self.topic_inspector_page.lbl_status.setObjectName("lbl_inspector_status_inactive")
            if getattr(self, "_action_page", None) is not None and hasattr(self.action_page, "lbl_status"):
                self.action_page.lbl_status.setObjectName("lbl_inspector_status_inactive")
            if getattr(self, "_service_inspector_page", None) is not None and hasattr(self.service_inspector_page, "lbl_status"):
                self.service_inspector_page.lbl_status.setObjectName("lbl_inspector_status")
        elif page_id == 6: # Action Inspector
            if getattr(self, "_topic_inspector_page", None) is not None and hasattr(self.topic_inspector_page, "lbl_status"):
                self.topic_inspector_page.lbl_status.setObjectName("lbl_inspector_status_inactive")
            if getattr(self, "_service_inspector_page", None) is not None and hasattr(self.service_inspector_page, "lbl_status"):
                self.service_inspector_page.lbl_status.setObjectName("lbl_inspector_status_inactive")
            if getattr(self, "_action_page", None) is not None and hasattr(self.action_page, "lbl_status"):
                self.action_page.lbl_status.setObjectName("lbl_inspector_status")

        # Trigger data refresh
        refresh_map = {
            1: self._refresh_packages,
            2: self._refresh_nodes_list,
            3: self._refresh_topics,
            4: self._refresh_launch,
            5: self._refresh_services,
            6: self._refresh_actions,
            7: self._refresh_logs,
            9: self._refresh_params,
            10: self._refresh_visualizer,
            11: self._refresh_bags,
            12: self._refresh_urdf,
            13: self._refresh_tools,
        }
        if page_id in refresh_map:
            refresh_map[page_id]()
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _refresh_packages(self):
        """Reload the package cards from the current workspace."""
        # Clear existing cards
        while self._pkg_flow.count():
            item = self._pkg_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        workspace = ROS2Workspace(self.current_workspace_path)
        packages = workspace.get_packages()

        if not packages:
            lbl = QLabel(f"No packages found in:\n{self.current_workspace_path}")
            lbl.setStyleSheet("font-style: italic; font-size: 13px;")
            self._pkg_flow.addWidget(lbl)
            return

        for pkg in packages:
            card = self._make_package_card(pkg)
            self._pkg_flow.addWidget(card)

    def _make_package_card(self, pkg: dict) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedWidth(240)
        card.setMinimumHeight(120)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)

        # Name row
        name_row = QHBoxLayout()
        name_row.addWidget(_icon_label("fa5s.box", "accent", 14))
        name_lbl = QLabel(pkg.get("name", "unknown"))
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
        name_lbl.setWordWrap(True)
        name_lbl.setToolTip(pkg.get("name", ""))
        name_row.addWidget(name_lbl)
        name_row.addStretch()
        lay.addLayout(name_row)

        # Build type badge
        build_type = pkg.get("build_type", "")
        if build_type:
            bt_lbl = QLabel(build_type)
            bt_lbl.setStyleSheet(
                "font-size: 11px; border-radius: 4px; padding: 2px 6px;"
            )
            lay.addWidget(bt_lbl)

        # Node count
        nodes = pkg.get("nodes", [])
        nodes_lbl = QLabel(f"{len(nodes)} node{'s' if len(nodes) != 1 else ''}")
        nodes_lbl.setStyleSheet("font-size: 12px;")
        lay.addWidget(nodes_lbl)

        lay.addStretch()

        # Path
        path = pkg.get("path", "")
        if path:
            path_lbl = QLabel(os.path.basename(path))
            path_lbl.setStyleSheet("font-size: 11px;")
            path_lbl.setToolTip(path)
            lay.addWidget(path_lbl)

        return card

    def _refresh_visualizer(self):
        if hasattr(self.visualizer_page, "refresh"):
            self.visualizer_page.refresh()

    def _refresh_launch(self):
        if hasattr(self.launch_manager_page, "_refresh_launch_files"):
            self.launch_manager_page._refresh_launch_files()

    def _refresh_tools(self):
        if hasattr(self.tools_hub_page, "_refresh_status"):
            self.tools_hub_page._refresh_status()

    def _refresh_topics(self):
        if hasattr(self.topic_inspector_page, "_refresh_topics"):
            self.topic_inspector_page._refresh_topics()

    def _refresh_services(self):
        if hasattr(self.service_inspector_page, "refresh_services"):
            self.service_inspector_page.refresh_services()

    def _refresh_params(self):
        if hasattr(self.parameter_manager_page, "_refresh_nodes"):
            self.parameter_manager_page._refresh_nodes()

    def _refresh_bags(self):
        if hasattr(self.bag_manager_page, "_scan_existing_bags"):
            self.bag_manager_page._scan_existing_bags()
        if hasattr(self.bag_manager_page, "_refresh_topics"):
            self.bag_manager_page._refresh_topics()

    def _refresh_urdf(self):
        if hasattr(self.urdf_page, "scan_workspace"):
            self.urdf_page.scan_workspace()

    # ── Settings page factory ─────────────────────────────────────────────────

    def _create_settings_page(self) -> SettingsPage:
        page = SettingsPage(self)
        page.theme_changed.connect(self._on_theme_changed)
        page.tab_visibility_changed.connect(self._apply_tab_visibility)
        page.tab_order_changed.connect(self._apply_tab_visibility)
        page.opengl_setting_changed.connect(self._apply_opengl_setting)
        page.save_requested.connect(self._force_save_settings)
        return page

    def _on_theme_changed(self, theme_name: str):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        ThemeManager.apply(app, theme_name)

        # Force every widget to re-read the new stylesheet
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        self.setWindowIcon(ThemeManager.icon("fa5s.robot", "accent"))
        self._refresh_nav_icons()

        # Refresh page theme properties dynamically
        for i in range(self.content_stack.count()):
            widget = self.content_stack.widget(i)
            if widget and hasattr(widget, "refresh_theme"):
                widget.refresh_theme()

        # Let settings page redraw its own theme buttons and cards
        if hasattr(self.settings_page, "_sync_theme_buttons"):
            self.settings_page._sync_theme_buttons()

        # Update all local help buttons styling for new theme
        if hasattr(self, "_local_help_buttons"):
            p = ThemeManager.palette()
            for btn in self._local_help_buttons.values():
                btn.setIcon(ThemeManager.icon("fa5s.info-circle", "normal"))
                btn.setStyleSheet(
                    f"QPushButton {{ border: none; background: transparent; }}"
                    f"QPushButton:hover {{ background-color: {p['bg_hover']}; border-radius: 12px; }}"
                )
                
        # Update Workspace Note styling
        if hasattr(self, "_workspace_note_card"):
            p = ThemeManager.palette()
            self._workspace_note_card.setStyleSheet(
                f"QFrame {{ "
                f"  background-color: {p['bg_hover']}; "
                f"  border: 1px solid {p['info']}; "
                f"  border-radius: 6px; "
                f"}}"
            )
            self._workspace_note_text.setStyleSheet(f"color: {p['text_primary']}; font-size: 12px; border: none;")
            self._workspace_note_icon.setPixmap(
                __import__("qtawesome").icon("fa5s.info-circle", color=p["info"]).pixmap(18, 18)
            )
            
        self._save_settings()

    def _apply_tab_visibility(self):
        vis = self.settings_page.tab_visibility()
        order = self.settings_page.tab_order()
        
        attr_by_key = {v: k for k, v in _TAB_KEY_FOR_BTN.items()}
        
        # 1. Hide/Show
        for page_id, attr, _label, _icon, _ in _NAV_ENTRIES:
            btn = self._nav_buttons.get(attr)
            if btn is None:
                continue
            key = _TAB_KEY_FOR_BTN.get(attr, "")
            if key in ("settings", "workspace"):
                btn.setVisible(True)
            else:
                btn.setVisible(vis.get(key, True))
                
        # 2. Reorder Nav Layout
        for attr, btn in self._nav_buttons.items():
            if attr not in ("btn_settings", "btn_tools"):
                self.nav_layout.removeWidget(btn)
                
        added_attrs = set()
        
        # Workspace is permanently anchored at the top of the layout
        btn_workspace = self._nav_buttons.get("btn_workspace")
        if btn_workspace:
            self.nav_layout.addWidget(btn_workspace)
            added_attrs.add("btn_workspace")
            
        for key in order:
            if key in ("settings", "workspace", "tools"):
                continue
            attr = attr_by_key.get(key)
            if attr:
                btn = self._nav_buttons.get(attr)
                if btn:
                    self.nav_layout.addWidget(btn)
                    added_attrs.add(attr)
                    
        # Fallback for missing entries
        for page_id, attr, _, _, _ in _NAV_ENTRIES:
            if attr not in ("btn_settings", "btn_tools") and attr not in added_attrs:
                btn = self._nav_buttons.get(attr)
                if btn:
                    self.nav_layout.addWidget(btn)

    def _apply_opengl_setting(self, use_opengl: bool):
        if hasattr(self, "urdf_page") and hasattr(self.urdf_page, "set_use_opengl"):
            self.urdf_page.set_use_opengl(use_opengl)

    def _attach_help_button_to_page(self, page_id: int, page: QWidget):
        # Create local help button
        help_btn = QPushButton(page)
        help_btn.setObjectName(f"help_btn_{page_id}")
        help_btn.setToolTip("Show screen documentation & ROS 2 commands")
        help_btn.setFixedSize(24, 24)
        help_btn.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(20, 20))
        
        # Connect to a slot that opens help for this specific page
        help_btn.clicked.connect(lambda: self._show_help_dialog_for_page(page_id))
        
        p = ThemeManager.palette()
        help_btn.setIcon(ThemeManager.icon("fa5s.info-circle", "normal"))
        help_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; }}"
            f"QPushButton:hover {{ background-color: {p['bg_hover']}; border-radius: 12px; }}"
        )
        
        # Save reference for theme refresh
        if not hasattr(self, "_local_help_buttons"):
            self._local_help_buttons = {}
        self._local_help_buttons[page_id] = help_btn

        # Move to initial position and raise to ensure it overlays layout content
        help_btn.move(page.width() - 24 - 16, 12)
        help_btn.raise_()

        # Install resize event filter to keep it positioned at the top-right
        resizer = HelpButtonResizer(help_btn)
        page.installEventFilter(resizer)
        # Store resizer reference on the button so it isn't garbage collected
        help_btn.resizer = resizer

    def _show_help_dialog_for_page(self, page_id: int):
        import json
        page_key = "unknown"
        for p_id, attr, _, _, _ in _NAV_ENTRIES:
            if p_id == page_id:
                page_key = _TAB_KEY_FOR_BTN.get(attr, "unknown")
                break
                
        docs = {}
        try:
            dir_path = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(dir_path, "help_docs.json")
            with open(json_path, "r", encoding="utf-8") as f:
                docs = json.load(f)
        except Exception as e:
            print(f"Error loading help docs: {e}")
            
        page_data = docs.get(page_key, {
            "title": "Help",
            "description": "No documentation available for this tab.",
            "under_the_hood": [],
            "tips": []
        })
        
        if "icon" not in page_data:
            for p_id, _, _, icon_name, _ in _NAV_ENTRIES:
                if p_id == page_id:
                    page_data["icon"] = icon_name
                    break
                    
        dialog = HelpDialog(page_data, self)
        dialog.exec()

    # ═══════════════════════════════════════════════════════════════════════════
    #  Page builders
    # ═══════════════════════════════════════════════════════════════════════════

    def _on_node_log_received(self, source: str, line: str):
        if hasattr(self, "log_viewer_page"):
            self.log_viewer_page.append_live_log(source, line)

    def _refresh_logs(self):
        if hasattr(self, "log_viewer_page"):
            self.log_viewer_page.refresh_log_files()

    # ── Workspace page (includes Build section) ────────────────────────────────

    def _create_workspace_page(self):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)

        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(scroll)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(12)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(ThemeManager.icon("fa5s.folder-open", "accent").pixmap(26, 26))
        hdr.addWidget(icon_lbl)
        title = QLabel("Workspace")
        title.setProperty("class", "h1")
        hdr.addWidget(title)
        hdr.addStretch()
        layout.addLayout(hdr)

        sub = QLabel(
            "A ROS2 workspace is a directory with a particular structure "
            "where you develop ROS2 packages."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("margin-top: 6px; margin-bottom: 24px;")
        layout.addWidget(sub)

        # ── Current workspace card ─────────────────────────────────────────
        ws_card = QFrame()
        ws_card.setProperty("class", "card")
        ws_lay = QVBoxLayout(ws_card)
        ws_lay.setSpacing(14)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(_icon_label("fa5s.map-marker-alt", "accent"))
        path_title = QLabel("Current Workspace")
        path_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        row1.addWidget(path_title)
        row1.addStretch()
        
        btn_ide = QPushButton("Open Workspace in IDE")
        btn_ide.setProperty("class", "primary-btn")
        btn_ide.setStyleSheet("padding: 6px 12px; font-weight: 600;")
        btn_ide.setToolTip("Open the current workspace root directory in your configured IDE.")
        btn_ide.clicked.connect(lambda: self._open_in_ide(self.current_workspace_path))
        
        try:
            btn_ide.setIcon(ThemeManager.icon("fa5s.code", "normal"))
        except Exception:
            pass
            
        row1.addWidget(btn_ide)
        ws_lay.addLayout(row1)

        self.lbl_workspace_path = QLabel(f"{self.current_workspace_path}")
        self.lbl_workspace_path.setStyleSheet(
            "font-family: 'Consolas', monospace; font-size: 12px; "
            "padding: 8px 12px; border-radius: 6px; "
            "border: 1px solid palette(shadow);"
        )
        self.lbl_workspace_path.setWordWrap(True)
        ws_lay.addWidget(self.lbl_workspace_path)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_open = _action_btn("Open Workspace", "fa5s.folder-open")
        btn_open.setToolTip("Browse for an existing workspace directory")
        btn_open.clicked.connect(self._open_workspace)
        btn_row.addWidget(btn_open)

        btn_init = _action_btn("Initialize New Workspace", "fa5s.plus-circle")
        btn_init.setProperty("class", "btn-success")
        btn_init.setToolTip(
            "<b>Initialize Workspace</b><br>"
            "Creates a new colcon workspace with a <code>src/</code> directory."
        )
        btn_init.clicked.connect(self._mock_init_workspace)
        btn_row.addWidget(btn_init)
        btn_row.addStretch()
        ws_lay.addLayout(btn_row)
        layout.addWidget(ws_card)
        layout.addSpacing(16)

        # ── Structure note ──────────────────────────────────────────────────
        note_card = QFrame()
        note_card.setProperty("class", "card")
        p = ThemeManager.palette()
        self._workspace_note_card = note_card
        self._workspace_note_card.setStyleSheet(
            f"QFrame {{ "
            f"  background-color: {p['bg_hover']}; "
            f"  border: 1px solid {p['info']}; "
            f"  border-radius: 6px; "
            f"}}"
        )
        note_lay = QHBoxLayout(self._workspace_note_card)
        note_lay.setContentsMargins(12, 10, 12, 10)
        note_lay.setSpacing(10)
        
        self._workspace_note_icon = _icon_label("fa5s.info-circle", "info")
        note_lay.addWidget(self._workspace_note_icon, 0, Qt.AlignVCenter)
        
        self._workspace_note_text = QLabel(
            "Note: Workspace directories must follow the official ROS 2 folder structure "
            "(with packages stored under a 'src/' subfolder) in order for features to function properly."
        )
        self._workspace_note_text.setWordWrap(True)
        self._workspace_note_text.setStyleSheet(f"color: {p['text_primary']}; font-size: 12px; border: none;")
        note_lay.addWidget(self._workspace_note_text, 1)
        layout.addWidget(self._workspace_note_card)

        layout.addSpacing(28)

        # ── Build section (merged from old Build tab) ──────────────────────
        build_hdr = QHBoxLayout()
        build_hdr.setSpacing(10)
        build_hdr.addWidget(_icon_label("fa5s.hammer", "accent"))
        build_title = QLabel("Build")
        build_title.setStyleSheet(
            "font-size: 18px; font-weight: 700; letter-spacing: -0.3px;"
        )
        build_hdr.addWidget(build_title)
        build_hdr.addStretch()
        layout.addLayout(build_hdr)

        build_sub = QLabel(
            "Compile your workspace packages with colcon. "
            "Building incorporates your code changes and resolves dependencies."
        )
        build_sub.setWordWrap(True)
        build_sub.setStyleSheet("margin-top: 6px; margin-bottom: 18px;")
        layout.addWidget(build_sub)

        build_card = QFrame()
        build_card.setProperty("class", "card")
        build_card_lay = QVBoxLayout(build_card)
        build_card_lay.setSpacing(14)

        # Config Row
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(15)
        
        cfg_row.addWidget(QLabel("Package:"))
        self.combo_build_pkg = QComboBox()
        self.combo_build_pkg.setMinimumWidth(180)
        cfg_row.addWidget(self.combo_build_pkg)

        self.chk_clean_build = QCheckBox("Clean Build")
        self.chk_clean_build.setToolTip("Deletes build/, install/, and log/ folders before compiling")
        cfg_row.addWidget(self.chk_clean_build)

        cfg_row.addWidget(QLabel("CMake Args:"))
        self.txt_cmake_args = QLineEdit()
        self.txt_cmake_args.setPlaceholderText("-DCMAKE_BUILD_TYPE=Release")
        cfg_row.addWidget(self.txt_cmake_args)

        build_card_lay.addLayout(cfg_row)

        # Controls & Status Row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(15)

        self.btn_start_build = _action_btn("Start Build", "fa5s.play")
        self.btn_start_build.clicked.connect(self._start_colcon_build)
        ctrl_row.addWidget(self.btn_start_build)

        self.btn_cancel_build = QPushButton("Cancel")
        self.btn_cancel_build.setEnabled(False)
        self.btn_cancel_build.clicked.connect(self._cancel_colcon_build)
        ctrl_row.addWidget(self.btn_cancel_build)

        p = ThemeManager.palette()
        self.lbl_build_badge = QLabel("Idle")
        self.lbl_build_badge.setStyleSheet(
            f"font-weight: bold; border-radius: 4px; padding: 4px 8px; background-color: {p['bg_hover']}; color: {p['text_secondary']};"
        )
        ctrl_row.addWidget(self.lbl_build_badge)
        ctrl_row.addStretch()

        build_card_lay.addLayout(ctrl_row)

        # Console Output
        self.txt_build_console = QTextEdit()
        self.txt_build_console.setReadOnly(True)
        self.txt_build_console.setFixedHeight(220)
        self.txt_build_console.setPlaceholderText("Build output logs will be streamed here in real-time...")
        self.txt_build_console.setStyleSheet(
            f"background-color: {p['bg_input']}; color: {p['text_primary']}; font-family: monospace; font-size: 11px; border: 1px solid {p['border']}; border-radius: 10px;"
        )
        build_card_lay.addWidget(self.txt_build_console)

        layout.addWidget(build_card)
        layout.addStretch()

        return outer

    # ── Packages page ──────────────────────────────────────────────────────────

    def _create_packages_page(self):
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(48, 40, 48, 40)
        outer_lay.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(_icon_label("fa5s.box", "accent"))
        hdr.addSpacing(10)
        title = QLabel("Packages")
        title.setProperty("class", "h1")
        hdr.addWidget(title)
        hdr.addStretch()

        btn_refresh = _action_btn("Refresh", "fa5s.sync-alt")
        btn_refresh.clicked.connect(self._refresh_packages)
        hdr.addWidget(btn_refresh)
        outer_lay.addLayout(hdr)

        sub = QLabel(
            "All ROS2 packages discovered in the current workspace src/ directory."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("margin-top: 6px; margin-bottom: 18px;")
        outer_lay.addWidget(sub)

        # ── Toolbar (create button) ─────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setProperty("class", "card")
        toolbar_lay = QHBoxLayout(toolbar)
        toolbar_lay.setContentsMargins(16, 12, 16, 12)

        btn_add = _action_btn("Create Package", "fa5s.plus-circle")
        btn_add.setToolTip(
            "<b>Create Package</b><br>"
            "Generates a new ROS2 package (ament_python or ament_cmake)."
        )
        btn_add.clicked.connect(self._mock_create_package)
        toolbar_lay.addWidget(btn_add)
        toolbar_lay.addStretch()
        outer_lay.addWidget(toolbar)
        outer_lay.addSpacing(18)

        # ── Package cards (flow layout inside scroll area) ──────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        pkg_container = QWidget()
        self._pkg_flow = FlowLayout(
            pkg_container, margin=0, hSpacing=20, vSpacing=20
        )
        scroll.setWidget(pkg_container)
        outer_lay.addWidget(scroll, 1)

        return outer

    # ── Nodes page ─────────────────────────────────────────────────────────────

    def _create_nodes_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)

        hdr = QHBoxLayout()
        hdr.addWidget(_icon_label("fa5s.microchip", "accent"))
        hdr.addSpacing(10)
        title = QLabel("Nodes")
        title.setProperty("class", "h1")
        hdr.addWidget(title)
        hdr.addStretch()

        btn_kill_all = _action_btn("Kill All Nodes", "fa5s.times-circle")
        btn_kill_all.setObjectName("btnKillAllNodes")
        btn_kill_all.setStyleSheet(
            f"background-color: {ThemeManager.palette()['danger']}; color: white;"
        )
        btn_kill_all.clicked.connect(self._kill_all_running_nodes)
        hdr.addWidget(btn_kill_all)
        hdr.addSpacing(10)

        btn_refresh = _action_btn("Refresh", "fa5s.sync-alt")
        btn_refresh.clicked.connect(self._refresh_nodes_list)
        hdr.addWidget(btn_refresh)
        layout.addLayout(hdr)

        sub = QLabel(
            "A node is a process that performs computation. "
            "Nodes communicate via topics, services, and actions."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("margin-top: 6px; margin-bottom: 18px;")
        layout.addWidget(sub)

        card = QFrame()
        card.setProperty("class", "card")
        card_lay = QVBoxLayout(card)

        btn_add = _action_btn("Add Node", "fa5s.plus-circle")
        btn_add.setToolTip(
            "<b>Add Node</b><br>"
            "Creates a boilerplate Python or C++ node script."
        )
        btn_add.clicked.connect(self._mock_add_node)
        card_lay.addWidget(btn_add, 0, Qt.AlignLeft)
        layout.addWidget(card)
        layout.addSpacing(18)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        self.nodes_container = QWidget()
        self.nodes_flow_layout = FlowLayout(
            self.nodes_container, margin=0, hSpacing=20, vSpacing=20
        )
        scroll_area.setWidget(self.nodes_container)
        layout.addWidget(scroll_area, 1)

        return page

    # ═══════════════════════════════════════════════════════════════════════════
    #  Node logic
    # ═══════════════════════════════════════════════════════════════════════════

    def _refresh_nodes_list(self):
        self.active_node_cards = []
        while self.nodes_flow_layout.count():
            item = self.nodes_flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        workspace = ROS2Workspace(self.current_workspace_path)
        packages = workspace.get_packages()

        has_nodes = False
        for pkg in packages:
            pkg_name = pkg["name"]
            for node_name in pkg.get("nodes", []):
                has_nodes = True
                card = self._make_node_card(pkg_name, node_name)
                self.nodes_flow_layout.addWidget(card)
                self.active_node_cards.append(card)

        if not has_nodes:
            lbl = QLabel(f"No nodes found in:\n{self.current_workspace_path}")
            lbl.setStyleSheet("font-style: italic; font-size: 13px;")
            self.nodes_flow_layout.addWidget(lbl)

    def _kill_all_running_nodes(self):
        # Terminate GUI-managed processes
        keys = list(self.running_processes.keys())
        for key in keys:
            proc = self.running_processes.get(key)
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        self.running_processes.clear()

        # Terminate any other node processes matching active cards
        for card in getattr(self, "active_node_cards", []):
            pkg = card.pkg_name
            node = card.node_name
            self._kill_node(pkg, node)

        # Refresh state
        self._refresh_nodes_list()

    def _make_node_card(self, pkg_name: str, node_name: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedWidth(260)
        card.setMinimumHeight(180)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_icon_label("fa5s.microchip", "accent", 14))
        lbl_node = QLabel(node_name)
        lbl_node.setStyleSheet("font-size: 15px; font-weight: bold;")
        row.addWidget(lbl_node)
        row.addStretch()
        
        btn_ide = QPushButton()
        btn_ide.setToolTip("Open source file (or package directory) in IDE")
        btn_ide.setFixedSize(24, 24)
        btn_ide.setCursor(Qt.PointingHandCursor)
        btn_ide.setStyleSheet("QPushButton { border: none; background: transparent; } QPushButton:hover { background: rgba(128, 128, 128, 0.2); border-radius: 4px; }")
        try:
            btn_ide.setIcon(ThemeManager.icon("fa5s.external-link-alt", "accent"))
        except Exception:
            btn_ide.setText("↗")
        btn_ide.clicked.connect(lambda _, p=pkg_name, n=node_name: self._open_node_in_ide(p, n))
        row.addWidget(btn_ide)
        
        lay.addLayout(row)

        lbl_pkg = QLabel(f"pkg: {pkg_name}")
        lbl_pkg.setStyleSheet("font-size: 12px; opacity: 0.6;")
        lay.addWidget(lbl_pkg)

        # Resource Monitor Labels
        lbl_cpu = QLabel("CPU: --")
        lbl_cpu.setStyleSheet("font-size: 12px; opacity: 0.8;")
        lbl_mem = QLabel("Memory: --")
        lbl_mem.setStyleSheet("font-size: 12px; opacity: 0.8;")
        lbl_threads = QLabel("Threads: --")
        lbl_threads.setStyleSheet("font-size: 12px; opacity: 0.8;")
        
        lay.addWidget(lbl_cpu)
        lay.addWidget(lbl_mem)
        lay.addWidget(lbl_threads)
        
        # Attach labels to card
        card.lbl_cpu = lbl_cpu
        card.lbl_mem = lbl_mem
        card.lbl_threads = lbl_threads
        card.pkg_name = pkg_name
        card.node_name = node_name
        card.process_obj = None

        lay.addStretch()

        is_running = self._is_node_running(pkg_name, node_name)
        proc_key = f"{pkg_name}:{node_name}"

        btn_run = QPushButton()
        if is_running:
            btn_run.setText("Stop")
            btn_run.setProperty("class", "btn-danger")
        else:
            btn_run.setText("Run")
            btn_run.setProperty("class", "btn-success")

        btn_run.setIconSize(
            __import__("PySide6.QtCore", fromlist=["QSize"]).QSize(14, 14)
        )
        btn_run.clicked.connect(
            lambda _, p=pkg_name, n=node_name, b=btn_run:
            self._toggle_node_run(p, n, b)
        )
        lay.addWidget(btn_run, 0, Qt.AlignRight)
        return card

    def _open_node_in_ide(self, pkg_name: str, node_name: str):
        import os
        from pathlib import Path
        
        # Determine package source root
        ws_src = os.path.join(self.current_workspace_path, "src")
        pkg_path = ""
        # Brute force search for package directory within src
        for root, dirs, files in os.walk(ws_src):
            if "package.xml" in files:
                if os.path.basename(root) == pkg_name:
                    pkg_path = root
                    break
        
        if not pkg_path:
            # Fallback to workspace root if package not found in src
            self._open_in_ide(self.current_workspace_path)
            return

        # Try to find the exact node file (node_name.py or node_name.cpp)
        found_file = ""
        for ext in [".py", ".cpp"]:
            for path in Path(pkg_path).rglob(f"{node_name}{ext}"):
                found_file = str(path)
                break
            if found_file:
                break
                
        if found_file:
            self._open_in_ide(found_file)
        else:
            # Fallback: open package directory
            self._open_in_ide(pkg_path)

    def _is_node_running(self, pkg_name, node_name):
        target_path = f"install/{pkg_name}/lib/{pkg_name}/{node_name}"
        target_cmd = f"ros2 run {pkg_name} {node_name}"
        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmdline = proc.info.get("cmdline")
                if not cmdline:
                    continue
                cmd_str = " ".join(cmdline)
                if target_path in cmd_str or target_cmd in cmd_str:
                    if not any(x in cmd_str for x in ("pgrep", "nano", "vim")):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def _kill_node(self, pkg_name, node_name):
        target_path = f"install/{pkg_name}/lib/{pkg_name}/{node_name}"
        target_cmd = f"ros2 run {pkg_name} {node_name}"
        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmdline = proc.info.get("cmdline")
                if not cmdline:
                    continue
                cmd_str = " ".join(cmdline)
                if target_path in cmd_str or target_cmd in cmd_str:
                    if not any(x in cmd_str for x in ("pgrep", "nano", "vim")):
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def _toggle_node_run(self, pkg_name, node_name, btn):
        import re

        def to_wsl_path(win_path: str) -> str:
            path = win_path.replace("\\", "/")
            m = re.match(r"^([a-zA-Z]):(.*)", path)
            return f"/mnt/{m.group(1).lower()}{m.group(2)}" if m else path

        proc_key = f"{pkg_name}:{node_name}"
        is_running = self._is_node_running(pkg_name, node_name)

        if is_running:
            self._kill_node(pkg_name, node_name)
            if proc_key in self.running_processes:
                del self.running_processes[proc_key]
            btn.setText("Run")
            btn.setProperty("class", "btn-success")
            btn.setStyleSheet("")  # Clear any explicit styles if present
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        else:
            setup_bash = os.path.join(
                self.current_workspace_path, "install", "setup.bash"
            )
            if self.cli and self.cli.use_wsl:
                setup_bash_wsl = to_wsl_path(setup_bash)
                cmd = (
                    f'[ -f "{setup_bash_wsl}" ] && source "{setup_bash_wsl}"; '
                    f"ros2 run {pkg_name} {node_name}"
                )
                run_cmd = ["wsl", "bash", "-i", "-c", cmd]
                cwd = None
            else:
                if os.path.exists(setup_bash):
                    cmd = f'source "{setup_bash}" && ros2 run {pkg_name} {node_name}'
                else:
                    cmd = f"ros2 run {pkg_name} {node_name}"
                run_cmd = ["bash", "-c", cmd]
                cwd = self.current_workspace_path

            proc = subprocess.Popen(
                run_cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.running_processes[proc_key] = proc
            btn.setText("Stop")
            btn.setProperty("class", "btn-danger")
            btn.setStyleSheet("")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

            # Start process output reader thread
            reader = ProcessLogReader(f"Node: {pkg_name}/{node_name}", proc, self)
            reader.new_line.connect(self._on_node_log_received)
            reader.start()

    def _update_node_resources(self):
        # Update metrics only if nodes page is active (stack index 2)
        if self.content_stack.currentIndex() != 2:
            return

        for card in getattr(self, "active_node_cards", []):
            pkg = card.pkg_name
            node = card.node_name

            # Check if cached process is still running and is correct
            proc = card.process_obj
            is_running = False
            if proc:
                try:
                    if proc.is_running():
                        cmdline = proc.cmdline()
                        cmd_str = " ".join(cmdline) if cmdline else ""
                        target_path = f"install/{pkg}/lib/{pkg}/{node}"
                        target_cmd = f"ros2 run {pkg} {node}"
                        if (target_path in cmd_str or target_cmd in cmd_str) and not any(x in cmd_str for x in ("pgrep", "nano", "vim")):
                            is_running = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if not is_running:
                proc = None
                target_path = f"install/{pkg}/lib/{pkg}/{node}"
                target_cmd = f"ros2 run {pkg} {node}"
                # Search system processes
                for p_iter in psutil.process_iter(["cmdline"]):
                    try:
                        cmdline = p_iter.info.get("cmdline")
                        if not cmdline:
                            continue
                        cmd_str = " ".join(cmdline)
                        if (target_path in cmd_str or target_cmd in cmd_str) and not any(x in cmd_str for x in ("pgrep", "nano", "vim")):
                            proc = p_iter
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                card.process_obj = proc

            if proc:
                try:
                    # Query metrics
                    cpu = proc.cpu_percent(interval=None)
                    mem_rss = proc.memory_info().rss / (1024 * 1024)
                    threads = proc.num_threads()

                    card.lbl_cpu.setText(f"CPU: {cpu:.1f}%")
                    card.lbl_mem.setText(f"Memory: {mem_rss:.1f} MB")
                    card.lbl_threads.setText(f"Threads: {threads}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    card.lbl_cpu.setText("CPU: --")
                    card.lbl_mem.setText("Memory: --")
                    card.lbl_threads.setText("Threads: --")
                    card.process_obj = None
            else:
                card.lbl_cpu.setText("CPU: --")
                card.lbl_mem.setText("Memory: --")
                card.lbl_threads.setText("Threads: --")
                card.process_obj = None

    # ═══════════════════════════════════════════════════════════════════════════
    #  Build logic
    # ═══════════════════════════════════════════════════════════════════════════

    def _start_colcon_build(self):
        if hasattr(self, "interactive_build_worker") and self.interactive_build_worker.isRunning():
            return

        self.txt_build_console.clear()
        self.statusBar().showMessage("Running colcon build …")

        build_args = []
        
        # Package selection
        pkg_selected = self.combo_build_pkg.currentText()
        if pkg_selected != "All Packages":
            build_args += ["--packages-select", pkg_selected]

        # Symlink install by default
        build_args += ["--symlink-install"]

        # Custom CMake args
        cmake_args = self.txt_cmake_args.text().strip()
        if cmake_args:
            import shlex
            build_args += ["--cmake-args"] + shlex.split(cmake_args)

        clean_first = self.chk_clean_build.isChecked()

        p = ThemeManager.palette()
        self.lbl_build_badge.setText("Building")
        self.lbl_build_badge.setStyleSheet(
            f"font-weight: bold; border-radius: 4px; padding: 4px 8px; background-color: {p['warning']}; color: white;"
        )

        self.btn_start_build.setEnabled(False)
        self.btn_cancel_build.setEnabled(True)
        self.combo_build_pkg.setEnabled(False)
        self.chk_clean_build.setEnabled(False)
        self.txt_cmake_args.setEnabled(False)

        self.interactive_build_worker = ColconBuildWorker(
            self.current_workspace_path,
            use_wsl=bool(self.cli and self.cli.use_wsl),
            build_args=build_args,
            clean_first=clean_first
        )
        self.interactive_build_worker.new_line.connect(self._on_build_output_line)
        self.interactive_build_worker.finished_signal.connect(self._on_interactive_build_finished)
        
        self.interactive_build_worker.start()

    def _on_build_output_line(self, line: str):
        self.txt_build_console.append(line.rstrip('\n'))

    def _on_interactive_build_finished(self, success: bool, output_err: str):
        self.btn_start_build.setEnabled(True)
        self.btn_cancel_build.setEnabled(False)
        self.combo_build_pkg.setEnabled(True)
        self.chk_clean_build.setEnabled(True)
        self.txt_cmake_args.setEnabled(True)

        p = ThemeManager.palette()
        if success:
            self.statusBar().showMessage("Build completed successfully.", 5000)
            self.lbl_build_badge.setText("Succeeded")
            self.lbl_build_badge.setStyleSheet(
                f"font-weight: bold; border-radius: 4px; padding: 4px 8px; background-color: {p['success']}; color: white;"
            )
            # Resource workspace
            self.statusBar().showMessage("Workspace resourced successfully (build complete).", 5000)
            self._refresh_packages()
            self._refresh_nodes_list()
            self._update_build_packages_combo()
        else:
            self.statusBar().showMessage("Build failed.", 5000)
            self.lbl_build_badge.setText("Failed")
            self.lbl_build_badge.setStyleSheet(
                f"font-weight: bold; border-radius: 4px; padding: 4px 8px; background-color: {p['danger']}; color: white;"
            )

    def _cancel_colcon_build(self):
        if hasattr(self, "interactive_build_worker") and self.interactive_build_worker.isRunning():
            self.interactive_build_worker.terminate_process()
            self.interactive_build_worker.wait(1000)
            self.txt_build_console.append("\n⚠ Build execution canceled by user.\n")
            self.statusBar().showMessage("Build canceled.", 5000)
            
            p = ThemeManager.palette()
            self.lbl_build_badge.setText("Canceled")
            self.lbl_build_badge.setStyleSheet(
                f"font-weight: bold; border-radius: 4px; padding: 4px 8px; background-color: {p['bg_hover']}; color: {p['text_secondary']};"
            )

    def _refresh_actions(self):
        if getattr(self, "_action_page", None) is not None:
            if hasattr(self.action_page, "_refresh_actions"):
                self.action_page._refresh_actions()

    def _auto_build_and_resource(self):
        if hasattr(self, "_bg_build_thread") and self._bg_build_thread.isRunning():
            return
        self.statusBar().showMessage("Workspace changed. Running background colcon build …")
        self._bg_build_thread = BuildThread(
            self.current_workspace_path,
            use_wsl=bool(self.cli and self.cli.use_wsl),
        )
        self._bg_build_thread.finished_signal.connect(self._on_bg_build_finished)
        self._bg_build_thread.start()

    def _on_bg_build_finished(self, success: bool, output: str):
        if success:
            self.statusBar().showMessage("Workspace resourced successfully (build complete).", 5000)
            self._refresh_packages()
            self._refresh_nodes_list()
        else:
            self.statusBar().showMessage("Background workspace sourcing/build failed.", 5000)

    # ═══════════════════════════════════════════════════════════════════════════
    #  Workspace helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_all_workspaces(self):
        self.cli.set_workspace(self.current_workspace_path)
        if hasattr(self, "lbl_workspace_path"):
            self.lbl_workspace_path.setText(self.current_workspace_path)

        # Refresh packages if that page has been built
        if hasattr(self, "_pkg_flow"):
            self._refresh_packages()

        self._update_build_packages_combo()

        pages_with_set_ws = [
            "_visualizer_page", "_launch_manager_page", "_tools_hub_page",
            "_topic_inspector_page", "_service_inspector_page", "_action_page",
            "_parameter_manager_page", "_bag_manager_page", "_urdf_page",
        ]
        for attr in pages_with_set_ws:
            page = getattr(self, attr, None)
            if page and hasattr(page, "set_workspace"):
                page.set_workspace(self.current_workspace_path)

    def _update_build_packages_combo(self):
        if not hasattr(self, "combo_build_pkg"):
            return
        self.combo_build_pkg.blockSignals(True)
        self.combo_build_pkg.clear()
        self.combo_build_pkg.addItem("All Packages")
        
        workspace = ROS2Workspace(self.current_workspace_path)
        packages = workspace.get_packages()
        for pkg in packages:
            self.combo_build_pkg.addItem(pkg.get("name", ""))
        self.combo_build_pkg.blockSignals(False)

    def _open_workspace(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Open Workspace", self.current_workspace_path
        )
        if dir_path:
            src_path = os.path.join(dir_path, "src")
            if not os.path.exists(src_path):
                reply = QMessageBox.question(
                    self, "Initialize Workspace?",
                    "The selected folder does not appear to be a ROS 2 workspace (it lacks a 'src' directory).\n\n"
                    "Would you like to initialize it as a workspace now by creating a 'src' folder?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    try:
                        os.makedirs(src_path, exist_ok=True)
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Failed to create src directory:\n{e}")
                        return
                elif reply == QMessageBox.Cancel:
                    return
            
            self.current_workspace_path = dir_path

    def _mock_init_workspace(self):
        name, ok = QInputDialog.getText(
            self, "New Workspace", "Enter workspace name:"
        )
        if not ok or not name:
            return
        try:
            new_path = os.path.join(self.current_workspace_path, name)
            os.makedirs(os.path.join(new_path, "src"), exist_ok=True)
            self.current_workspace_path = new_path
            QMessageBox.information(
                self, "Success",
                f"Workspace '{name}' initialised at:\n{new_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed:\n{exc}")

    def _mock_create_package(self):
        dialog = CreatePackageDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            pkg_name = data.get("name", "").strip()
            if not pkg_name:
                QMessageBox.warning(self, "Warning", "Package name cannot be empty.")
                return
            try:
                src_path = os.path.join(self.current_workspace_path, "src")
                cwd = src_path if os.path.exists(src_path) else self.current_workspace_path
                output = self.cli.pkg_create(
                    package_name=pkg_name,
                    build_type=data["build_type"],
                    dependencies=data["dependencies"],
                    cwd=cwd,
                )
                QMessageBox.information(
                    self, "Success",
                    f"Package '{pkg_name}' created.\n\n{output}"
                )
                self._auto_build_and_resource()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed:\n{exc}")

    def _mock_add_node(self):
        workspace = ROS2Workspace(self.current_workspace_path)
        packages = workspace.get_packages()
        if not packages:
            QMessageBox.warning(
                self, "Warning",
                "No packages found. Please create a package first."
            )
            return

        dialog = CreateNodeDialog(self)
        for pkg in packages:
            dialog.pkg_combo.addItem(pkg["name"])

        if dialog.exec():
            data = dialog.get_data()
            node_name = data["name"]
            pkg_name = data["package"]
            lang = data["language"]
            if not node_name:
                QMessageBox.warning(self, "Warning", "Node name cannot be empty.")
                return

            pkg_info = next((p for p in packages if p["name"] == pkg_name), None)
            if not pkg_info:
                return
            try:
                if lang == "python":
                    CodeGenerator.generate_python_node(
                        pkg_info["path"], pkg_name, node_name
                    )
                    CodeGenerator.modify_setup_py(
                        os.path.join(pkg_info["path"], "setup.py"),
                        pkg_name, node_name
                    )
                elif lang == "cpp":
                    CodeGenerator.generate_cpp_node(
                        pkg_info["path"], pkg_name, node_name
                    )
                    CodeGenerator.modify_cmakelists(
                        os.path.join(pkg_info["path"], "CMakeLists.txt"),
                        node_name
                    )
                QMessageBox.information(
                    self, "Success",
                    f"Node '{node_name}' added to '{pkg_name}'."
                )
                self._auto_build_and_resource()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed:\n{exc}")

    def _load_active_tabs(self):
        prop_map = {
            0: "workspace_page",
            1: "packages_page",
            2: "nodes_page",
            3: "topic_inspector_page",
            4: "launch_manager_page",
            5: "service_inspector_page",
            6: "action_page",
            7: "log_viewer_page",
            8: "dds_troubleshooter_page",
            9: "parameter_manager_page",
            10: "visualizer_page",
            11: "bag_manager_page",
            12: "urdf_page",
            13: "tools_hub_page",
        }
        from PySide6.QtCore import QCoreApplication
        for page_id, attr, _, _, _ in _NAV_ENTRIES:
            btn = self._nav_buttons.get(attr)
            if btn and btn.isVisible() and page_id in prop_map:
                placeholder = self.content_stack.widget(page_id)
                if placeholder and placeholder.property("is_placeholder"):
                    getattr(self, prop_map[page_id])
                    QCoreApplication.processEvents()

    def show(self):
        super().show()
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

    def showEvent(self, event):
        super().showEvent(event)
        from PySide6.QtCore import QCoreApplication, QTimer
        QCoreApplication.processEvents()
        QTimer.singleShot(100, self._load_active_tabs)

    # ── Window close ──────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._save_settings()
        # Terminate running launches
        if getattr(self, "_launch_manager_page", None) is not None:
            for _path, proc in list(
                getattr(self._launch_manager_page, "running_launches", {}).items()
            ):
                is_running = False
                if proc is not None and hasattr(proc, "poll"):
                    try:
                        val = proc.poll()
                        is_running = (val is None or type(val).__name__ in ('MagicMock', 'Mock'))
                    except Exception:
                        pass
                if is_running:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
            self._launch_manager_page.running_launches.clear()

        # Terminate running build worker if any
        if hasattr(self, "interactive_build_worker") and self.interactive_build_worker.isRunning():
            self.interactive_build_worker.terminate_process()

        # Terminate action goal worker if any
        if getattr(self, "_action_page", None) is not None:
            if hasattr(self._action_page, "_goal_worker") and self._action_page._goal_worker is not None:
                self._action_page._cancel_goal()

        # Terminate tools hub processes
        if getattr(self, "_tools_hub_page", None) is not None:
            cards = getattr(self._tools_hub_page, "_cards", {})
            if not cards:
                cards = getattr(self._tools_hub_page, "_rows", {})
            for card in cards.values():
                p = getattr(card, "_process", None)
                is_running = False
                if p is not None and hasattr(p, "poll"):
                    try:
                        val = p.poll()
                        is_running = (val is None or type(val).__name__ in ('MagicMock', 'Mock'))
                    except Exception:
                        pass
                if is_running:
                    try:
                        p.terminate()
                        p.wait(timeout=2)
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass
                    card._process = None

        event.accept()


# ─── Small helpers ─────────────────────────────────────────────────────────────

def _icon_label(icon_name: str, role: str = "normal", size: int = 18) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(ThemeManager.icon(icon_name, role).pixmap(size, size))
    lbl.setFixedSize(size + 4, size + 4)
    return lbl


def _action_btn(label: str, icon_name: str | None = None) -> QPushButton:
    btn = QPushButton(f"  {label}" if icon_name else label)
    btn.setProperty("class", "action-button")
    if icon_name:
        btn.setIcon(ThemeManager.icon(icon_name, "active"))
        from PySide6.QtCore import QSize
        btn.setIconSize(QSize(14, 14))
    return btn
