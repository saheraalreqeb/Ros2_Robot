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
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
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
from gui.visualizer import VisualizerPage


# ─── Thread helpers ────────────────────────────────────────────────────────────

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
                    cmd, capture_output=True, text=True
                )
            else:
                result = subprocess.run(
                    "colcon build", capture_output=True, text=True,
                    shell=True, cwd=self.workspace_path
                )
            if result.returncode == 0:
                self.finished_signal.emit(True, result.stdout)
            else:
                self.finished_signal.emit(False, result.stderr or result.stdout)
        except Exception as exc:
            self.finished_signal.emit(False, str(exc))


# ─── Sidebar nav entry definition ─────────────────────────────────────────────

_NAV_ENTRIES = [
    # (page_id, attr_name,   label,            icon_name,             refresh_method_or_None)
    (0, "btn_workspace",  "Workspace",       "fa5s.folder-open",    None),
    (1, "btn_packages",   "Packages",        "fa5s.box",            None),
    (2, "btn_nodes",      "Nodes",           "fa5s.microchip",      "_refresh_nodes_list"),
    (3, "btn_topics",     "Topic Inspector", "fa5s.satellite-dish", "_refresh_topics"),
    (4, "btn_launch",     "Launch Manager",  "fa5s.rocket",         "_refresh_launch"),
    (5, "btn_params",     "Parameters",      "fa5s.sliders-h",      "_refresh_params"),
    (6, "btn_visualizer", "Visualizer",      "fa5s.project-diagram","_refresh_visualizer"),
    (7, "btn_bags",       "Bag Manager",     "fa5s.database",       "_refresh_bags"),
    (8, "btn_tools",      "Tools Hub",       "fa5s.tools",          "_refresh_tools"),
    (9, "btn_settings",   "Settings",        "fa5s.cog",            None),
]

# Keys that map to SettingsPage._TAB_DEFS keys
_TAB_KEY_FOR_BTN = {
    "btn_workspace":  "workspace",
    "btn_packages":   "packages",
    "btn_nodes":      "nodes",
    "btn_visualizer": "visualizer",
    "btn_launch":     "launch",
    "btn_tools":      "tools",
    "btn_topics":     "topics",
    "btn_params":     "params",
    "btn_bags":       "bags",
    "btn_settings":   "settings",
}


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

    # ── init ──────────────────────────────────────────────────────────────────

    def __init__(self):
        super().__init__()
        self._current_workspace_path_val = os.getcwd()
        self.setWindowTitle("Ros2 Robot")
        self.setWindowIcon(ThemeManager.icon("fa5s.robot", "accent"))
        self.resize(1180, 780)
        self.setMinimumSize(900, 600)

        self.cli = ROS2CLI()
        if os.name == "nt":
            self.cli.use_wsl = True
        self.running_processes: dict = {}

        # Apply default dark theme (replaces styles.qss)
        from PySide6.QtWidgets import QApplication
        ThemeManager.apply(QApplication.instance(), "dark")

        # Central layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_sidebar()
        self._setup_content_area()
        self._update_all_workspaces()
        self.statusBar().showMessage("Ready  ·  Ros2 Robot")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _setup_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(230)

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

        logo_icon = QLabel()
        logo_icon.setPixmap(
            ThemeManager.icon("fa5s.robot", "accent").pixmap(22, 22)
        )
        logo_lay.addWidget(logo_icon)

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

        for page_id, attr, label, icon_name, _ in _NAV_ENTRIES:
            btn = self._create_nav_button(page_id, label, icon_name)
            setattr(self, attr, btn)
            self._nav_buttons[attr] = btn

            # Tools Hub & Settings get pushed to bottom
            if attr == "btn_tools":
                sb_lay.addStretch()
                # thin divider
                div = QFrame()
                div.setFixedHeight(1)
                div.setStyleSheet(
                    "background-color: palette(shadow); margin: 0 16px;"
                )
                sb_lay.addWidget(div)
                sb_lay.addSpacing(4)

            sb_lay.addWidget(btn)

        sb_lay.addSpacing(8)
        self.main_layout.addWidget(self.sidebar)

        self.nav_group.idClicked.connect(self._switch_page)
        self.btn_workspace.setChecked(True)

    def _create_nav_button(self, page_id: int, label: str,
                           icon_name: str) -> QPushButton:
        btn = QPushButton(f"  {label}")
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

    # ── Content area ──────────────────────────────────────────────────────────

    def _setup_content_area(self):
        self.content_stack = QStackedWidget()
        self.main_layout.addWidget(self.content_stack, 1)

        # Build the pages; page indices must match _NAV_ENTRIES page_id values
        self.workspace_page    = self._create_workspace_page()   # 0
        self.packages_page     = self._create_packages_page()    # 1
        self.nodes_page        = self._create_nodes_page()       # 2
        self.topic_inspector_page = TopicInspectorPage(self.cli) # 3
        self.launch_manager_page  = LaunchManagerPage(self.cli)  # 4
        self.parameter_manager_page = ParameterManagerPage(self.cli)  # 5
        self.visualizer_page   = VisualizerPage(self.cli)        # 6
        self.bag_manager_page  = BagManagerPage(self.cli)        # 7
        self.tools_hub_page    = ToolsHubPage(self.cli)          # 8
        self.settings_page     = self._create_settings_page()   # 9

        for page in [
            self.workspace_page,   # 0
            self.packages_page,    # 1
            self.nodes_page,       # 2
            self.topic_inspector_page,  # 3
            self.launch_manager_page,   # 4
            self.parameter_manager_page,  # 5
            self.visualizer_page,  # 6
            self.bag_manager_page, # 7
            self.tools_hub_page,   # 8
            self.settings_page,    # 9
        ]:
            self.content_stack.addWidget(page)

    # ── Page switching ────────────────────────────────────────────────────────

    def _switch_page(self, page_id: int):
        self.content_stack.setCurrentIndex(page_id)
        # Update icon highlights
        self._refresh_nav_icons()
        # Trigger data refresh
        refresh_map = {
            1: self._refresh_packages,
            2: self._refresh_nodes_list,
            3: self._refresh_topics,
            4: self._refresh_launch,
            5: self._refresh_params,
            6: self._refresh_visualizer,
            7: self._refresh_bags,
            8: self._refresh_tools,
        }
        if page_id in refresh_map:
            refresh_map[page_id]()

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

    def _refresh_params(self):
        if hasattr(self.parameter_manager_page, "_refresh_nodes"):
            self.parameter_manager_page._refresh_nodes()

    def _refresh_bags(self):
        if hasattr(self.bag_manager_page, "_scan_existing_bags"):
            self.bag_manager_page._scan_existing_bags()
        if hasattr(self.bag_manager_page, "_refresh_topics"):
            self.bag_manager_page._refresh_topics()

    # ── Settings page factory ─────────────────────────────────────────────────

    def _create_settings_page(self) -> SettingsPage:
        page = SettingsPage(self)
        page.theme_changed.connect(self._on_theme_changed)
        page.tab_visibility_changed.connect(self._apply_tab_visibility)
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

    def _apply_tab_visibility(self):
        vis = self.settings_page.tab_visibility()
        for page_id, attr, _label, _icon, _ in _NAV_ENTRIES:
            btn = self._nav_buttons.get(attr)
            if btn is None:
                continue
            key = _TAB_KEY_FOR_BTN.get(attr, "")
            # Settings and Workspace are always visible
            if key in ("settings", "workspace"):
                btn.setVisible(True)
            else:
                btn.setVisible(vis.get(key, True))

    # ═══════════════════════════════════════════════════════════════════════════
    #  Page builders
    # ═══════════════════════════════════════════════════════════════════════════

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
        btn_init.setToolTip(
            "<b>Initialize Workspace</b><br>"
            "Creates a new colcon workspace with a <code>src/</code> directory."
        )
        btn_init.clicked.connect(self._mock_init_workspace)
        btn_row.addWidget(btn_init)
        btn_row.addStretch()
        ws_lay.addLayout(btn_row)
        layout.addWidget(ws_card)
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

        build_btn_row = QHBoxLayout()
        build_btn_row.setSpacing(10)

        btn_build = _action_btn("Colcon Build", "fa5s.cog")
        btn_build.setToolTip(
            "<b>Colcon Build</b><br>"
            "Runs <code>colcon build</code> in the workspace root."
        )
        btn_build.clicked.connect(self._mock_build)
        build_btn_row.addWidget(btn_build)
        build_btn_row.addStretch()
        build_card_lay.addLayout(build_btn_row)

        # Build output label
        self.lbl_build_status = QLabel("")
        self.lbl_build_status.setWordWrap(True)
        self.lbl_build_status.hide()
        build_card_lay.addWidget(self.lbl_build_status)

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

        if not has_nodes:
            lbl = QLabel(f"No nodes found in:\n{self.current_workspace_path}")
            lbl.setStyleSheet("font-style: italic; font-size: 13px;")
            self.nodes_flow_layout.addWidget(lbl)

    def _make_node_card(self, pkg_name: str, node_name: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedWidth(260)
        card.setMinimumHeight(140)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_icon_label("fa5s.microchip", "accent", 14))
        lbl_node = QLabel(node_name)
        lbl_node.setStyleSheet("font-size: 15px; font-weight: bold;")
        row.addWidget(lbl_node)
        lay.addLayout(row)

        lbl_pkg = QLabel(f"pkg: {pkg_name}")
        lbl_pkg.setStyleSheet("font-size: 12px; opacity: 0.6;")
        lay.addWidget(lbl_pkg)
        lay.addStretch()

        is_running = self._is_node_running(pkg_name, node_name)
        proc_key = f"{pkg_name}:{node_name}"

        btn_run = QPushButton()
        if is_running:
            btn_run.setText("  Stop")
            btn_run.setIcon(ThemeManager.icon("fa5s.stop-circle", "danger"))
            btn_run.setStyleSheet(
                f"background-color: {ThemeManager.palette()['danger']}; color: white;"
            )
        else:
            btn_run.setText("  Run")
            btn_run.setIcon(ThemeManager.icon("fa5s.play-circle", "success"))
            btn_run.setStyleSheet(
                f"background-color: {ThemeManager.palette()['success']}; color: white;"
            )

        btn_run.setIconSize(
            __import__("PySide6.QtCore", fromlist=["QSize"]).QSize(14, 14)
        )
        btn_run.clicked.connect(
            lambda _, p=pkg_name, n=node_name, b=btn_run:
            self._toggle_node_run(p, n, b)
        )
        lay.addWidget(btn_run, 0, Qt.AlignRight)
        return card

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
            btn.setText("  Run")
            btn.setIcon(ThemeManager.icon("fa5s.play-circle", "success"))
            btn.setStyleSheet(
                f"background-color: {ThemeManager.palette()['success']}; color: white;"
            )
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

            proc = subprocess.Popen(run_cmd, cwd=cwd)
            self.running_processes[proc_key] = proc
            btn.setText("  Stop")
            btn.setIcon(ThemeManager.icon("fa5s.stop-circle", "danger"))
            btn.setStyleSheet(
                f"background-color: {ThemeManager.palette()['danger']}; color: white;"
            )

    # ═══════════════════════════════════════════════════════════════════════════
    #  Build logic
    # ═══════════════════════════════════════════════════════════════════════════

    def _mock_build(self):
        self.statusBar().showMessage("Running colcon build …")
        self.lbl_build_status.hide()

        self.progress_dialog = QProgressDialog(
            "Building workspace with colcon …", "Cancel", 0, 0, self
        )
        self.progress_dialog.setWindowTitle("Building")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()

        self.build_thread = BuildThread(
            self.current_workspace_path,
            use_wsl=bool(self.cli and self.cli.use_wsl),
        )
        self.build_thread.finished_signal.connect(self._on_build_finished)
        self.build_thread.start()

    def _on_build_finished(self, success: bool, output: str):
        self.progress_dialog.close()
        p = ThemeManager.palette()
        if success:
            self.statusBar().showMessage("Build completed successfully.", 5000)
            self.lbl_build_status.setStyleSheet(
                f"color: {p['success']}; font-size: 12px;"
            )
            self.lbl_build_status.setText("✓  Build succeeded.")
            self.lbl_build_status.show()
        else:
            self.statusBar().showMessage("Build failed.", 5000)
            self.lbl_build_status.setStyleSheet(
                f"color: {p['danger']}; font-size: 12px;"
            )
            short = output[:400] + ("…" if len(output) > 400 else "")
            self.lbl_build_status.setText(f"✗  Build failed:\n{short}")
            self.lbl_build_status.show()
            QMessageBox.critical(self, "Build Error", f"colcon build failed:\n{output}")

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

        pages_with_set_ws = [
            "visualizer_page", "launch_manager_page", "tools_hub_page",
            "topic_inspector_page", "parameter_manager_page", "bag_manager_page",
        ]
        for attr in pages_with_set_ws:
            page = getattr(self, attr, None)
            if page and hasattr(page, "set_workspace"):
                page.set_workspace(self.current_workspace_path)

    def _open_workspace(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Open Workspace", self.current_workspace_path
        )
        if dir_path:
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

    # ── Window close ──────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Terminate running launches
        if hasattr(self, "launch_manager_page"):
            for _path, proc in list(
                getattr(self.launch_manager_page, "running_launches", {}).items()
            ):
                if isinstance(proc, subprocess.Popen) and proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
            self.launch_manager_page.running_launches.clear()

        # Terminate tools hub processes
        if hasattr(self, "tools_hub_page"):
            for card in getattr(self.tools_hub_page, "_cards", {}).values():
                p = getattr(card, "_process", None)
                if p is not None and isinstance(p, subprocess.Popen) and p.poll() is None:
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
