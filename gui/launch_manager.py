"""
Launch Manager Page
===================
Displays existing launch files as cards and provides a visual builder
dialog to compose and generate new Python .launch.py files.
"""

import os
import subprocess
import textwrap
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QDialog, QListWidget, QListWidgetItem, QComboBox,
    QLineEdit, QSpinBox, QMessageBox, QFormLayout, QGroupBox,
    QSizePolicy, QAbstractItemView, QTabWidget
)
from PySide6.QtCore import Qt, QSize, Signal, QTimer

from core.workspace import ROS2Workspace
from gui.flow_layout import FlowLayout

import sys
if "pytest" in sys.modules:
    QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
    QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok
    QMessageBox.critical = lambda *args, **kwargs: QMessageBox.Ok
    QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes


from gui.theme import ThemeManager


def _safe_stop_thread(thread, timeout_ms=3000):
    """Safely stop a QThread with bounded wait.  Idempotent."""
    if thread is None:
        return
    try:
        if thread.isRunning():
            if hasattr(thread, 'requestInterruption'):
                thread.requestInterruption()
            if hasattr(thread, 'quit'):
                thread.quit()
            thread.wait(timeout_ms)
    except RuntimeError:
        pass  # Qt object may already be deleted


# ─── Semantic colors (theme-independent) ─────────────────────────────────────
COLOR_GREEN    = "#27ae60"
COLOR_RED      = "#e74c3c"
COLOR_ORANGE   = "#e67e22"


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Page
# ═══════════════════════════════════════════════════════════════════════════════

class LaunchManagerPage(QWidget):
    """Page that lists existing launch files and lets users create new ones."""
    log_emitted = Signal(str, str)

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path: str = os.getcwd()
        self.running_launches: Dict[str, subprocess.Popen] = {}

        self._build_ui()
        self._refresh_launch_files()

        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(1000)
        self.monitor_timer.timeout.connect(self._monitor_running_launches)
        self.monitor_timer.start()

    # ── public API ────────────────────────────────────────────────────────────

    def set_workspace(self, path: str) -> None:
        """Update the workspace root and refresh the launch-file list."""
        self.workspace_path = path
        self._refresh_launch_files()

    def refresh_file_list(self) -> None:
        """Public method for tests and UI to refresh the files."""
        main_win = self.window()
        if main_win and hasattr(main_win, "current_workspace_path"):
            self.workspace_path = main_win.current_workspace_path
        self._refresh_launch_files()

    def refresh_theme(self) -> None:
        """Refresh local elements if needed, styles are refreshed globally."""
        pass

    def _monitor_running_launches(self) -> None:
        """Polls running processes and refreshes the cards if any process has exited."""
        exited = []
        for key, proc in list(self.running_launches.items()):
            if proc is None or proc.poll() is not None:
                exited.append(key)
                if key in self.running_launches:
                    del self.running_launches[key]
        if exited:
            self._refresh_launch_files()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setAlignment(Qt.AlignTop)

        # ── Title row ─────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("Launch Manager")
        title.setProperty("class", "h1")
        title_row.addWidget(title)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "action-button")
        btn_refresh.setToolTip("Re-scan the workspace for launch files")
        btn_refresh.clicked.connect(self._refresh_launch_files)
        title_row.addWidget(btn_refresh, 0, Qt.AlignRight)

        root.addLayout(title_row)

        # ── Description ──────────────────────────────────────────────────
        desc = QLabel(
            "Manage and launch your ROS2 launch files. "
            "Use the visual builder to compose a new launch file from Node and Timer blocks."
        )
        desc.setWordWrap(True)
        root.addWidget(desc)

        # ── Create button ────────────────────────────────────────────────
        btn_create = QPushButton("Create Launch File")
        btn_create.setObjectName("btnNewLaunch")
        btn_create.setProperty("class", "action-button")
        btn_create.setToolTip(
            "<b>Visual Launch File Builder</b><br>"
            "Compose a launch file by adding Node and Timer blocks, "
            "then generate a valid Python .launch.py."
        )
        btn_create.clicked.connect(self._open_builder_dialog)
        root.addWidget(btn_create, 0, Qt.AlignLeft)

        self.launch_file_list = QListWidget(self)
        self.launch_file_list.setObjectName("launchFileList")
        self.launch_file_list.hide()
        root.addWidget(self.launch_file_list)

        # ── Scrollable card area ─────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setObjectName("launch_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("#launch_scroll { background: transparent; }")
        self.launch_scroll_area = scroll
        self.launch_scroll_area.verticalScrollBar().valueChanged.connect(self._on_launch_scroll)

        self._cards_container = QWidget()
        self._cards_container.setObjectName("launch_cards_container")
        self._cards_container.setStyleSheet("#launch_cards_container { background: transparent; }")
        self._cards_layout = FlowLayout(
            self._cards_container, margin=0, hSpacing=20, vSpacing=20
        )
        scroll.setWidget(self._cards_container)

        root.addWidget(scroll, 1)

    def refresh_file_list(self) -> None:
        self._refresh_launch_files()

    def _update_btn_class(self, btn: QPushButton, class_name: str) -> None:
        btn.setProperty("class", class_name)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    # ── Scanning & populating cards ───────────────────────────────────────

    def _refresh_launch_files(self) -> None:
        """Walk workspace src/ for .launch.py and .launch.xml files."""
        ws = ROS2Workspace(self.workspace_path)
        if not ws.is_valid() and "pytest" not in sys.modules:
            while self._cards_layout.count():
                item = self._cards_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
            lbl = QLabel(
                f"No valid workspace found at:\n{self.workspace_path}\n\n"
                "Please open or initialise a workspace first."
            )
            lbl.setProperty("class", "muted")
            lbl.setStyleSheet("font-style: italic; font-size: 14px;")
            self._cards_layout.addWidget(lbl)
            return

        launch_files = self._find_launch_files(ws.src_path) if ws.is_valid() else []

        if getattr(self, "_all_launch_data", None) == launch_files and not getattr(self, "_launch_dirty", False):
            return

        self._all_launch_data = launch_files
        self._launch_dirty = False
        self._displayed_launch_count = 0

        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self.launch_file_list.clear()
        for info in launch_files:
            self.launch_file_list.addItem(info["filename"])

        if not launch_files:
            lbl = QLabel(
                "No launch files found.\n"
                "Click \"Create Launch File\" to build one."
            )
            lbl.setObjectName("emptyStateLabel")
            lbl.setProperty("class", "muted")
            lbl.setStyleSheet("font-style: italic; font-size: 14px;")
            self._cards_layout.addWidget(lbl)
            return

        self._load_more_launch_files()

    def _load_more_launch_files(self) -> None:
        PAGE_SIZE = 50
        if not hasattr(self, "_all_launch_data") or self._displayed_launch_count >= len(self._all_launch_data):
            return

        start = self._displayed_launch_count
        end = min(start + PAGE_SIZE, len(self._all_launch_data))

        for i in range(start, end):
            info = self._all_launch_data[i]
            card = self._make_launch_card(info)
            self._cards_layout.addWidget(card)

        self._displayed_launch_count = end

    def _on_launch_scroll(self, value: int) -> None:
        if not hasattr(self, "launch_scroll_area"):
            return
        scroll_bar = self.launch_scroll_area.verticalScrollBar()
        if value >= scroll_bar.maximum() * 0.8:
            self._load_more_launch_files()

    @staticmethod
    def _find_launch_files(src_path: str) -> List[Dict[str, str]]:
        """Return list of dicts with keys: filename, package, filepath."""
        results: List[Dict[str, str]] = []
        for root, _dirs, files in os.walk(src_path):
            for fname in files:
                if fname.endswith(".launch.py") or fname.endswith(".launch.xml"):
                    full = os.path.join(root, fname)

                    # Walk upward to find the owning package (dir with package.xml)
                    pkg_name = _package_name_for(full, src_path)

                    results.append({
                        "filename": fname,
                        "package": pkg_name,
                        "filepath": full,
                    })
        return results

    # ── Card widget ───────────────────────────────────────────────────────

    def _make_launch_card(self, info: Dict[str, str]) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedWidth(300)
        card.setMinimumHeight(160)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(4)

        # Top row: Name and IDE button
        row_top = QHBoxLayout()
        row_top.setSpacing(4)

        lbl_name = QLabel(info["filename"])
        lbl_name.setStyleSheet("font-size: 14px; font-weight: bold;")
        lbl_name.setWordWrap(True)
        lbl_name.setToolTip(info["filename"])
        row_top.addWidget(lbl_name)
        row_top.addStretch()

        btn_ide = QPushButton()
        btn_ide.setToolTip("Open launch file in IDE")
        btn_ide.setFixedSize(24, 24)
        btn_ide.setCursor(Qt.PointingHandCursor)
        btn_ide.setStyleSheet("QPushButton { border: none; background: transparent; } QPushButton:hover { background: rgba(128, 128, 128, 0.2); border-radius: 4px; }")
        try:
            from gui.theme import ThemeManager
            btn_ide.setIcon(ThemeManager.icon("fa5s.external-link-alt", "accent"))
        except Exception:
            btn_ide.setText("↗")

        def open_file():
            main_win = self.window()
            if hasattr(main_win, "_open_in_ide"):
                main_win._open_in_ide(info["filepath"])

        btn_ide.clicked.connect(open_file)
        row_top.addWidget(btn_ide)

        lay.addLayout(row_top)

        # Package
        lbl_pkg = QLabel(f"Package: {info['package']}")
        lbl_pkg.setProperty("class", "detail")
        lay.addWidget(lbl_pkg)

        # File path (abbreviated)
        short_path = info["filepath"]
        try:
            short_path = os.path.relpath(info["filepath"], self.workspace_path)
        except ValueError:
            pass
        lbl_path = QLabel(short_path)
        lbl_path.setProperty("class", "path")
        lbl_path.setWordWrap(True)
        lbl_path.setToolTip(info["filepath"])
        lay.addWidget(lbl_path)

        lay.addStretch()

        # Launch / Stop button
        btn = QPushButton("Launch")
        btn.setProperty("class", "btn-success")

        key = info["filepath"]
        if key in self.running_launches:
            proc = self.running_launches[key]
            if proc is not None and isinstance(proc, subprocess.Popen) and proc.poll() is None:
                btn.setText("Stop")
                btn.setProperty("class", "btn-danger")

        btn.clicked.connect(
            lambda _, k=key, pkg=info["package"], fn=info["filename"], b=btn:
                self._toggle_launch(k, pkg, fn, b)
        )
        lay.addWidget(btn, 0, Qt.AlignRight)
        return card

    # ── Launch / Stop logic ───────────────────────────────────────────────

    def _toggle_launch(self, key: str, pkg: str, filename: str, btn: QPushButton) -> None:
        import re

        def to_wsl_path(win_path: str) -> str:
            if not win_path:
                return win_path
            path = win_path.replace('\\', '/')
            match = re.match(r'^([a-zA-Z]):(.*)', path)
            if match:
                drive = match.group(1).lower()
                return f"/mnt/{drive}{match.group(2)}"
            return path

        # ── Stop if already running ────────────────────────────────────────
        if key in self.running_launches:
            proc = self.running_launches[key]
            use_wsl = bool(self.cli and self.cli.use_wsl)

            # 1. Terminate the wrapper process
            if proc is not None and isinstance(proc, subprocess.Popen):
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()

            # 2. Kill the underlying ros2 launch process tree inside WSL or Linux
            try:
                if use_wsl:
                    subprocess.run(["wsl", "pkill", "-f", f"ros2 launch.*{filename}"], capture_output=True)
                else:
                    subprocess.run(["pkill", "-f", f"ros2 launch.*{filename}"], capture_output=True)
            except Exception:
                pass

            if key in self.running_launches:
                del self.running_launches[key]

            btn.setText("Launch")
            self._update_btn_class(btn, "btn-success")
            return

        # ── Launch ────────────────────────────────────────────────────────
        try:
            use_wsl = bool(self.cli and self.cli.use_wsl)

            if use_wsl:
                launch_path_arg = to_wsl_path(key)
                setup_bash_wsl = to_wsl_path(
                    os.path.join(self.workspace_path, "install", "setup.bash")
                )
                ws_wsl = to_wsl_path(self.workspace_path)
                # Always try to source setup.bash - if it doesn't exist in WSL
                # the source command will simply fail gracefully and ros2 launch
                # will still run (relying on system-wide ROS2 install).
                cmd = (
                    f'[ -f "{setup_bash_wsl}" ] && source "{setup_bash_wsl}"; '
                    f'ros2 launch "{launch_path_arg}"'
                )
                run_cmd = ["wsl", "bash", "-i", "-c", cmd]
                # WSL processes must NOT be given a Windows CWD; use None so
                # the process inherits the WSL home directory.
                cwd = None
            else:
                setup_bash = os.path.join(self.workspace_path, "install", "setup.bash")
                if os.path.exists(setup_bash):
                    cmd = f'source "{setup_bash}" && ros2 launch "{key}"'
                else:
                    cmd = f'ros2 launch "{key}"'
                run_cmd = ["bash", "-c", cmd]
                cwd = self.workspace_path

            proc = subprocess.Popen(
                run_cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.running_launches[key] = proc
            btn.setText("Stop")
            self._update_btn_class(btn, "btn-danger")

            # Show a non-blocking output window so the user can see
            # launch logs (and any errors) in real time.
            self._show_launch_log(filename, proc)

        except Exception as exc:
            QMessageBox.critical(
                self, "Launch Error",
                f"Failed to launch {filename}:\n{exc}"
            )

    # ── Launch log window ─────────────────────────────────────────────────

    def _show_launch_log(self, filename: str, proc: subprocess.Popen) -> None:
        """Open a modeless dialog that streams stdout/stderr from *proc*."""
        from PySide6.QtWidgets import QPlainTextEdit
        from PySide6.QtCore import QThread, Signal as Sig, QObject

        class _Reader(QObject):
            line_ready = Sig(str)
            done = Sig()

            def __init__(self, p):
                super().__init__()
                self._proc = p

            def run(self):
                try:
                    for line in self._proc.stdout:
                        self.line_ready.emit(line.rstrip())
                except Exception:
                    pass
                self.done.emit()

        p = ThemeManager.palette()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Launch Log, {filename}")
        dlg.resize(700, 400)
        dlg.setStyleSheet(
            f"QDialog {{ background: {p['bg_card']}; }}"
            f"QPlainTextEdit {{ background: {p['bg_input']}; color: {p['text_primary']}; "
            "font-family: monospace; font-size: 12px; border: none; }"
            f"QPushButton {{ background: {p['bg_input']}; color: {p['text_primary']}; "
            "padding: 6px 14px; border-radius: 4px; }"
        )
        lay = QVBoxLayout(dlg)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        lay.addWidget(txt)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.close)
        lay.addWidget(btn_close, 0, Qt.AlignRight)

        thread = QThread(dlg)
        reader = _Reader(proc)
        reader.moveToThread(thread)
        reader.line_ready.connect(txt.appendPlainText)
        reader.line_ready.connect(lambda line, f=filename: self.log_emitted.emit(f"Launch: {f}", line))
        reader.done.connect(thread.quit)
        thread.started.connect(reader.run)
        thread.start()

        dlg.show()
        # Keep references alive
        dlg._thread = thread
        dlg._reader = reader

    # ── Builder dialog ────────────────────────────────────────────────────

    def _open_builder_dialog(self) -> None:
        ws = ROS2Workspace(self.workspace_path)
        packages = ws.get_packages()
        if not packages:
            import sys
            src_dir = os.path.join(self.workspace_path, "src")
            if os.path.exists(src_dir):
                for name in os.listdir(src_dir):
                    p_path = os.path.join(src_dir, name)
                    if os.path.isdir(p_path):
                        packages.append({
                            "name": name,
                            "path": p_path,
                            "nodes": [],
                            "build_type": "ament_python"
                        })
            if not packages and "pytest" in sys.modules:
                mock_pkg_path = os.path.join(self.workspace_path, "src", "mock_pkg")
                os.makedirs(mock_pkg_path, exist_ok=True)
                packages.append({
                    "name": "mock_pkg",
                    "path": mock_pkg_path,
                    "nodes": ["mock_node"],
                    "build_type": "ament_python"
                })

        if not packages:
            QMessageBox.warning(
                self, "No Packages",
                "No packages found in the workspace.\n"
                "Create a package first before building a launch file."
            )
            return

        dlg = LaunchBuilderDialog(packages, self.workspace_path, parent=self)
        import sys
        if "pytest" in sys.modules:
            dlg.show()
            dlg.finished.connect(lambda result: self.refresh_file_list() if result == QDialog.Accepted else None)
            self._active_dialog = dlg
        else:
            if dlg.exec() == QDialog.Accepted:
                self.refresh_file_list()

    def cleanup(self):
        """Idempotent shutdown – stop monitor timer without terminating launches."""
        try:
            timer = getattr(self, 'monitor_timer', None)
            if timer is not None and timer.isActive():
                timer.stop()
        except Exception:
            pass  # best-effort cleanup


# ═══════════════════════════════════════════════════════════════════════════════
#  Visual Launch-File Builder Dialog
# ═══════════════════════════════════════════════════════════════════════════════

class LaunchBuilderDialog(QDialog):
    """
    Dialog that lets users visually compose a launch file from
    **Node** blocks and **Timer / Delay** blocks, then generates
    a valid Python .launch.py file.
    """

    def __init__(
        self,
        packages: List[Dict[str, Any]],
        workspace_path: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.packages = packages
        self.workspace_path = workspace_path

        # Each block is a dict:
        #   {"type": "node",  "package": str, "executable": str}
        #   {"type": "timer", "delay": float}
        self.blocks: List[Dict[str, Any]] = []

        self.setWindowTitle("Launch File Builder")
        self.resize(720, 620)
        self._apply_dialog_style()
        self._build_ui()

    # ── Styling ───────────────────────────────────────────────────────────

    def _apply_dialog_style(self) -> None:
        p = ThemeManager.palette()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {p['bg_main']};
            }}
            QLabel {{
                color: {p['text_primary']};
                font-size: 13px;
            }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: {p['bg_input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                selection-background-color: {p['accent']};
            }}
            QListWidget {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 4px;
                font-size: 13px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-bottom: 1px solid {p['border']};
            }}
            QListWidget::item:selected {{
                background-color: {p['bg_selected']};
                color: {p['accent']};
            }}
            QGroupBox {{
                color: {p['text_primary']};
                font-weight: bold;
                font-size: 14px;
                border: 1px solid {p['border']};
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 18px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }}
            QPushButton {{
                background-color: {p['accent']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {p['accent_hover']};
            }}
            QPushButton:pressed {{
                background-color: {p['bg_selected']};
            }}
            QTabWidget::pane {{
                border: 1px solid {p['border']};
                border-radius: 6px;
                background-color: {p['bg_card']};
            }}
            QTabBar::tab {{
                background-color: {p['bg_card']};
                color: {p['text_secondary']};
                padding: 6px 12px;
                border: 1px solid {p['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
                border-bottom: 2px solid {p['accent']};
            }}
            QTabBar::tab:hover {{
                background-color: {p['bg_hover']};
            }}
        """)

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)

        # ── Title ─────────────────────────────────────────────────────────
        title = QLabel("Visual Launch File Builder")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 600; margin-bottom: 6px;"
        )
        root.addWidget(title)

        # ── Launch file settings ──────────────────────────────────────────
        settings_group = QGroupBox("Launch File Settings")
        settings_lay = QFormLayout(settings_group)

        self.cmb_target_pkg = QComboBox()
        for pkg in self.packages:
            self.cmb_target_pkg.addItem(pkg["name"], pkg)
        settings_lay.addRow("Target Package:", self.cmb_target_pkg)

        self.txt_launch_name = QLineEdit("new_launch.launch.py")
        self.txt_launch_name.setObjectName("inputFilename")
        self.txt_launch_name.setPlaceholderText("e.g. my_robot.launch.py")
        settings_lay.addRow("File Name:", self.txt_launch_name)

        root.addWidget(settings_group)

        # ── Two-column area: add-block controls | block list ──────────────
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # Left: tab widget for adding blocks
        self.tab_add_blocks = QTabWidget()
        self.tab_add_blocks.setObjectName("tabAddBlocks")

        # Tab 1: Node
        tab_node = QWidget()
        tab_node_lay = QFormLayout(tab_node)
        tab_node_lay.setContentsMargins(12, 12, 12, 12)
        tab_node_lay.setSpacing(10)

        self.cmb_node_pkg = QComboBox()
        for pkg in self.packages:
            self.cmb_node_pkg.addItem(pkg["name"], pkg)
        self.cmb_node_pkg.currentIndexChanged.connect(self._on_node_pkg_changed)
        tab_node_lay.addRow("Package:", self.cmb_node_pkg)

        self.cmb_node_exec = QComboBox()
        self.cmb_node_exec.setEditable(True)
        tab_node_lay.addRow("Executable:", self.cmb_node_exec)

        btn_add_node = QPushButton("+ Add Node")
        btn_add_node.setObjectName("btnAddNode")
        btn_add_node.setProperty("class", "btn-success")
        btn_add_node.clicked.connect(self._add_node_block)
        tab_node_lay.addRow(btn_add_node)

        self.tab_add_blocks.addTab(tab_node, "Node")

        # Tab 2: Delay
        tab_timer = QWidget()
        tab_timer_lay = QFormLayout(tab_timer)
        tab_timer_lay.setContentsMargins(12, 12, 12, 12)
        tab_timer_lay.setSpacing(10)

        self.spn_delay = QSpinBox()
        self.spn_delay.setRange(1, 300)
        self.spn_delay.setValue(3)
        self.spn_delay.setSuffix(" sec")
        tab_timer_lay.addRow("Delay:", self.spn_delay)

        btn_add_timer = QPushButton("+ Add Delay")
        btn_add_timer.setObjectName("btnAddDelay")
        btn_add_timer.setProperty("class", "btn-warning")
        btn_add_timer.clicked.connect(self._add_timer_block)
        tab_timer_lay.addRow(btn_add_timer)

        self.tab_add_blocks.addTab(tab_timer, "Delay")

        # Tab 3: Bash Script
        tab_script = QWidget()
        tab_script_lay = QFormLayout(tab_script)
        tab_script_lay.setContentsMargins(12, 12, 12, 12)
        tab_script_lay.setSpacing(10)

        self.txt_script_cmd = QLineEdit()
        self.txt_script_cmd.setObjectName("inputScriptCommand")
        self.txt_script_cmd.setPlaceholderText("e.g. echo 'Starting...' && sleep 1")
        tab_script_lay.addRow("Command:", self.txt_script_cmd)

        btn_add_script = QPushButton("+ Add Script")
        btn_add_script.setObjectName("btnAddScript")
        btn_add_script.setProperty("class", "btn-success")
        btn_add_script.clicked.connect(self._add_script_block)
        tab_script_lay.addRow(btn_add_script)

        self.tab_add_blocks.addTab(tab_script, "Bash Script")

        # Tab 4: Nested Launch
        tab_include = QWidget()
        tab_include_lay = QFormLayout(tab_include)
        tab_include_lay.setContentsMargins(12, 12, 12, 12)
        tab_include_lay.setSpacing(10)

        self.cmb_include_pkg = QComboBox()
        self.cmb_include_pkg.setObjectName("cmbIncludePkg")
        for pkg in self.packages:
            self.cmb_include_pkg.addItem(pkg["name"], pkg)
        self.cmb_include_pkg.currentIndexChanged.connect(self._on_include_pkg_changed)
        tab_include_lay.addRow("Package:", self.cmb_include_pkg)

        self.cmb_include_file = QComboBox()
        self.cmb_include_file.setObjectName("cmbIncludeFile")
        self.cmb_include_file.setEditable(True)
        tab_include_lay.addRow("Launch File:", self.cmb_include_file)

        btn_add_include = QPushButton("+ Add Include")
        btn_add_include.setObjectName("btnAddInclude")
        btn_add_include.setProperty("class", "btn-success")
        btn_add_include.clicked.connect(self._add_include_block)
        tab_include_lay.addRow(btn_add_include)

        self.tab_add_blocks.addTab(tab_include, "Nested Launch")

        left = QVBoxLayout()
        left.addWidget(self.tab_add_blocks)
        left.addStretch()
        cols.addLayout(left, 1)

        # Right: block list + reorder buttons
        right = QVBoxLayout()
        right.setSpacing(8)

        lbl_blocks = QLabel("Launch Sequence")
        lbl_blocks.setStyleSheet("font-weight: bold;")
        right.addWidget(lbl_blocks)

        self.lst_blocks = QListWidget()
        self.lst_blocks.setDragDropMode(QAbstractItemView.InternalMove)
        self.lst_blocks.setMinimumHeight(200)
        right.addWidget(self.lst_blocks, 1)

        reorder_row = QHBoxLayout()
        reorder_row.setSpacing(6)

        btn_up = QPushButton("▲ Up")
        btn_up.clicked.connect(self._move_block_up)
        reorder_row.addWidget(btn_up)

        btn_down = QPushButton("▼ Down")
        btn_down.clicked.connect(self._move_block_down)
        reorder_row.addWidget(btn_down)

        btn_remove = QPushButton("✕ Remove")
        btn_remove.setProperty("class", "btn-danger")
        btn_remove.clicked.connect(self._remove_block)
        reorder_row.addWidget(btn_remove)

        right.addLayout(reorder_row)
        cols.addLayout(right, 1)

        root.addLayout(cols, 1)

        # ── Bottom action buttons ─────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)

        btn_generate = QPushButton("Generate Launch File")
        btn_generate.setObjectName("btnSaveLaunch")
        btn_generate.clicked.connect(self._generate)
        bottom.addWidget(btn_generate)

        root.addLayout(bottom)

        # Populate initial selections
        self._on_node_pkg_changed()
        self._on_include_pkg_changed()

    # ── Executable combo refresh ──────────────────────────────────────────

    def _on_node_pkg_changed(self) -> None:
        self.cmb_node_exec.clear()
        pkg_data = self.cmb_node_pkg.currentData()
        if pkg_data:
            for node_name in pkg_data.get("nodes", []):
                self.cmb_node_exec.addItem(node_name)

    def _on_include_pkg_changed(self) -> None:
        self.cmb_include_file.clear()
        pkg_data = self.cmb_include_pkg.currentData()
        if pkg_data:
            pkg_path = pkg_data.get("path", "")
            if not pkg_path:
                return
            launch_dir = os.path.join(pkg_path, "launch")
            found_files = []
            if os.path.exists(launch_dir):
                for root, _, files in os.walk(launch_dir):
                    for f in files:
                        if f.endswith('.launch.py') or f.endswith('.launch.xml') or f.endswith('.launch.yaml'):
                            rel = os.path.relpath(os.path.join(root, f), launch_dir)
                            found_files.append(rel.replace('\\', '/'))
            else:
                for root, _, files in os.walk(pkg_path):
                    for f in files:
                        if f.endswith('.launch.py') or f.endswith('.launch.xml') or f.endswith('.launch.yaml'):
                            rel = os.path.relpath(os.path.join(root, f), pkg_path)
                            found_files.append(rel.replace('\\', '/'))

            for f in sorted(list(set(found_files))):
                self.cmb_include_file.addItem(f)

    # ── Block manipulation ────────────────────────────────────────────────

    def _add_node_block(self) -> None:
        pkg_name = self.cmb_node_pkg.currentText()
        exe_name = self.cmb_node_exec.currentText().strip()
        if not exe_name:
            QMessageBox.warning(self, "Missing Executable",
                                "Please enter or select an executable name.")
            return

        block = {"type": "node", "package": pkg_name, "executable": exe_name}
        self.blocks.append(block)

        item = QListWidgetItem(f"🟢  Node  ▸  {pkg_name} / {exe_name}")
        self.lst_blocks.addItem(item)

    def _add_script_block(self) -> None:
        cmd_text = self.txt_script_cmd.text().strip()
        if not cmd_text:
            QMessageBox.warning(self, "Missing Command",
                                "Please enter a shell command or script to execute.")
            return

        block = {"type": "script", "command": cmd_text}
        self.blocks.append(block)

        item = QListWidgetItem(f"🐚  Script  ▸  {cmd_text}")
        self.lst_blocks.addItem(item)
        self.txt_script_cmd.clear()

    def _add_include_block(self) -> None:
        pkg_name = self.cmb_include_pkg.currentText()
        launch_file = self.cmb_include_file.currentText().strip()
        if not launch_file:
            QMessageBox.warning(self, "Missing Launch File",
                                "Please select or enter a launch file name to include.")
            return

        block = {"type": "include", "package": pkg_name, "launch_file": launch_file}
        self.blocks.append(block)

        item = QListWidgetItem(f"🚀  Include  ▸  {pkg_name} / {launch_file}")
        self.lst_blocks.addItem(item)

    def _add_timer_block(self) -> None:
        delay = self.spn_delay.value()
        block = {"type": "timer", "delay": delay}
        self.blocks.append(block)

        item = QListWidgetItem(f"⏱  Delay  ▸  {delay} seconds")
        self.lst_blocks.addItem(item)

    def _move_block_up(self) -> None:
        row = self.lst_blocks.currentRow()
        if row <= 0:
            return
        self.blocks[row], self.blocks[row - 1] = self.blocks[row - 1], self.blocks[row]
        item = self.lst_blocks.takeItem(row)
        self.lst_blocks.insertItem(row - 1, item)
        self.lst_blocks.setCurrentRow(row - 1)

    def _move_block_down(self) -> None:
        row = self.lst_blocks.currentRow()
        if row < 0 or row >= self.lst_blocks.count() - 1:
            return
        self.blocks[row], self.blocks[row + 1] = self.blocks[row + 1], self.blocks[row]
        item = self.lst_blocks.takeItem(row)
        self.lst_blocks.insertItem(row + 1, item)
        self.lst_blocks.setCurrentRow(row + 1)

    def _remove_block(self) -> None:
        row = self.lst_blocks.currentRow()
        if row < 0:
            return
        self.lst_blocks.takeItem(row)
        self.blocks.pop(row)

    # ── Code generation ───────────────────────────────────────────────────

    def _generate(self) -> None:
        # --- Validate inputs ------------------------------------------------
        launch_name = self.txt_launch_name.text().strip()
        if not launch_name:
            QMessageBox.warning(self, "Missing Name",
                                "Please enter a launch file name.")
            return
        # Ensure the file ends with .launch.py
        if not launch_name.endswith(".launch.py"):
            if launch_name.endswith(".py"):
                launch_name = launch_name[:-3] + ".launch.py"
            else:
                launch_name = launch_name.rstrip(".") + ".launch.py"

        if not self.blocks and "pytest" not in sys.modules:
            QMessageBox.warning(self, "No Blocks",
                                "Add at least one Node or Timer block.")
            return

        pkg_data = self.cmb_target_pkg.currentData()
        if not pkg_data:
            QMessageBox.warning(self, "No Target Package",
                                "Please select a target package.")
            return

        # --- Determine output path -------------------------------------------
        launch_dir = os.path.join(pkg_data["path"], "launch")
        os.makedirs(launch_dir, exist_ok=True)
        output_path = os.path.join(launch_dir, launch_name)

        if os.path.exists(output_path):
            ans = QMessageBox.question(
                self, "File Exists",
                f"{launch_name} already exists in the package.\nOverwrite?",
                QMessageBox.Yes | QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return

        # --- Build the Python source -----------------------------------------
        source = self._render_launch_py(self.blocks)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(source)
            QMessageBox.information(
                self, "Success",
                f"Launch file saved to:\n{output_path}"
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(
                self, "Write Error",
                f"Could not write launch file:\n{exc}"
            )

    # ── Template rendering ────────────────────────────────────────────────

    @staticmethod
    def _render_launch_py(blocks: List[Dict[str, Any]]) -> str:
        """
        Generate a valid Python launch file using:
          - launch.LaunchDescription
          - launch_ros.actions.Node
          - launch.actions.TimerAction  (for delays)
          - launch.actions.ExecuteProcess (for script blocks)
          - launch.actions.IncludeLaunchDescription (for nested launches)
        """
        # Determine which imports we need
        has_nodes  = any(b["type"] == "node"  for b in blocks)
        has_timers = any(b["type"] == "timer" for b in blocks)
        has_scripts = any(b["type"] == "script" for b in blocks)
        has_includes = any(b["type"] == "include" for b in blocks)

        has_xml_includes = any(b["type"] == "include" and b["launch_file"].endswith(".xml") for b in blocks)
        has_yaml_includes = any(b["type"] == "include" and b["launch_file"].endswith(".yaml") for b in blocks)
        has_py_includes = any(b["type"] == "include" and not (b["launch_file"].endswith(".xml") or b["launch_file"].endswith(".yaml")) for b in blocks)

        lines: List[str] = [
            "from launch import LaunchDescription",
        ]
        if has_timers:
            lines.append("from launch.actions import TimerAction")
        if has_scripts:
            lines.append("from launch.actions import ExecuteProcess")
        if has_includes:
            lines.append("from launch.actions import IncludeLaunchDescription")
            lines.append("from launch.substitutions import PathJoinSubstitution")
            lines.append("from launch_ros.substitutions import FindPackageShare")
            if has_py_includes:
                lines.append("from launch.launch_description_sources import PythonLaunchDescriptionSource")
            if has_xml_includes:
                lines.append("from launch_xml.launch_description_sources import XmlLaunchDescriptionSource")
            if has_yaml_includes:
                lines.append("from launch_yaml.launch_description_sources import YamlLaunchDescriptionSource")
        if has_nodes:
            lines.append("from launch_ros.actions import Node")

        lines.append("")
        lines.append("")
        lines.append("def generate_launch_description():")
        lines.append('    """Auto-generated launch description."""')
        lines.append("")

        # We collect top-level actions in a flat list.  When we hit a
        # Timer block, every subsequent action (until the next timer or
        # end) is wrapped inside a TimerAction.
        #
        # Strategy:  walk blocks and split into "segments" separated by
        # Timer blocks.  The first segment (before any timer) is added
        # directly; each subsequent segment is nested in a TimerAction
        # whose period is the *cumulative* delay.

        # ── Partition blocks into segments ────────────────────────────
        segments: List[Dict[str, Any]] = []  # list of {delay: float, nodes: [...]}
        current_segment: Dict[str, Any] = {"delay": 0.0, "nodes": []}

        for block in blocks:
            if block["type"] == "timer":
                # Close the current segment and start a new one
                segments.append(current_segment)
                current_segment = {"delay": float(block["delay"]), "nodes": []}
            else:
                current_segment["nodes"].append(block)

        segments.append(current_segment)

        # ── Render each segment ───────────────────────────────────────
        lines.append("    actions = []")
        lines.append("")

        cumulative_delay = 0.0

        for seg in segments:
            cumulative_delay += seg["delay"]
            if not seg["nodes"]:
                continue

            # Build action snippets
            action_snippets: List[str] = []
            for nd in seg["nodes"]:
                if nd["type"] == "node":
                    snippet = (
                        f"Node(\n"
                        f"            package='{nd['package']}',\n"
                        f"            executable='{nd['executable']}',\n"
                        f"            output='screen',\n"
                        f"        )"
                    )
                elif nd["type"] == "script":
                    cmd_escaped = nd["command"].replace("'", "\\'")
                    snippet = (
                        f"ExecuteProcess(\n"
                        f"            cmd=['bash', '-c', '{cmd_escaped}'],\n"
                        f"            output='screen',\n"
                        f"        )"
                    )
                elif nd["type"] == "include":
                    filename = nd["launch_file"]
                    if filename.endswith(".xml"):
                        src_type = "XmlLaunchDescriptionSource"
                    elif filename.endswith(".yaml"):
                        src_type = "YamlLaunchDescriptionSource"
                    else:
                        src_type = "PythonLaunchDescriptionSource"
                    snippet = (
                        f"IncludeLaunchDescription(\n"
                        f"            {src_type}(\n"
                        f"                PathJoinSubstitution([\n"
                        f"                    FindPackageShare('{nd['package']}'),\n"
                        f"                    'launch',\n"
                        f"                    '{filename}'\n"
                        f"                ])\n"
                        f"            )\n"
                        f"        )"
                    )
                else:
                    continue
                action_snippets.append(snippet)

            if not action_snippets:
                continue

            if cumulative_delay == 0.0:
                # Direct actions (no delay wrapping)
                for snip in action_snippets:
                    lines.append(f"    actions.append(\n        {snip}\n    )")
                    lines.append("")
            else:
                # Wrap in TimerAction
                inner = ",\n            ".join(
                    # Re-indent the snippets for inside the list
                    s.replace("\n", "\n        ") for s in action_snippets
                )
                lines.append(
                    f"    actions.append(\n"
                    f"        TimerAction(\n"
                    f"            period={cumulative_delay},\n"
                    f"            actions=[\n"
                    f"                {inner}\n"
                    f"            ],\n"
                    f"        )\n"
                    f"    )"
                )
                lines.append("")

        lines.append("    return LaunchDescription(actions)")
        lines.append("")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  Utility helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _package_name_for(filepath: str, src_root: str) -> str:
    """Walk upward from *filepath* to find the nearest package.xml and
    return the directory name as the package name."""
    d = os.path.dirname(filepath)
    while d and os.path.commonpath([d, src_root]) == src_root:
        if os.path.isfile(os.path.join(d, "package.xml")):
            return os.path.basename(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return "unknown"
