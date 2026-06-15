import os
import sys
import shlex
import subprocess
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QTextEdit, QLineEdit, QFrame, QScrollArea
)
from gui.theme import ThemeManager

# ---------------------------------------------------------------------------
#  Workers
# ---------------------------------------------------------------------------

class _ActionListWorker(QThread):
    result_ready = Signal(str)

    def __init__(self, cmd: list, parent=None):
        super().__init__(parent)
        self.cmd = cmd

    def run(self):
        try:
            result = subprocess.run(
                self.cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
            )
            if result.returncode == 0:
                self.result_ready.emit(result.stdout.strip())
            else:
                self.result_ready.emit(f"error: {result.stderr.strip()}")
        except Exception as exc:
            self.result_ready.emit(f"error: {exc}")

class _ActionInfoWorker(QThread):
    result_ready = Signal(str)

    def __init__(self, cmd: list, parent=None):
        super().__init__(parent)
        self.cmd = cmd

    def run(self):
        try:
            result = subprocess.run(
                self.cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
            )
            self.result_ready.emit(result.stdout.strip())
        except Exception as exc:
            self.result_ready.emit(f"(error: {exc})")

class _GoalSenderWorker(QThread):
    new_line = Signal(str)
    finished = Signal(bool)

    def __init__(self, cmd: list, cwd: str = None, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = cwd
        self.process = None

    def run(self):
        try:
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.cwd,
                bufsize=1
            )
            for line in iter(self.process.stdout.readline, ""):
                self.new_line.emit(line)
            self.process.stdout.close()
            return_code = self.process.wait()
            self.finished.emit(return_code == 0)
        except Exception as exc:
            self.new_line.emit(f"Error executing goal call: {exc}\n")
            self.finished.emit(False)

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

# ---------------------------------------------------------------------------
#  Main page widget
# ---------------------------------------------------------------------------

class ActionInspectorPage(QWidget):
    """Full-featured action inspection page."""

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path = None

        # Subprocess / thread bookkeeping
        self._list_worker = None
        self._info_worker = None
        self._goal_worker = None
        self._current_action = None
        self._action_types = {}

        self._build_ui()

    def set_workspace(self, path: str):
        """Store the workspace path so we can source install/setup.bash."""
        self.workspace_path = path

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ---- QSplitter -------------------------------------------------
        self.splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(self.splitter)

        # ---- Left panel (action list) ------------------------------------
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 30, 10, 20)

        left_title = QLabel("Actions")
        left_title.setProperty("class", "h1")
        left_layout.addWidget(left_title)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_refresh_actions")
        self.btn_refresh.setProperty("class", "action-button")
        self.btn_refresh.setToolTip("Run 'ros2 action list' to discover active actions")
        self.btn_refresh.clicked.connect(self._refresh_actions)
        left_layout.addWidget(self.btn_refresh, 0, Qt.AlignLeft)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("lbl_inspector_status")
        self.lbl_status.setStyleSheet("font-size: 12px; font-style: italic;")
        left_layout.addWidget(self.lbl_status)

        self.action_list = QListWidget()
        self.action_list.setObjectName("list_actions")
        p = ThemeManager.palette()
        self.action_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 10px;
                color: {p['text_primary']};
                font-size: 14px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-bottom: 1px solid {p['border']};
            }}
            QListWidget::item:selected {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
            }}
            QListWidget::item:hover {{
                background-color: {p['bg_hover']};
            }}
            """
        )
        self.action_list.currentItemChanged.connect(self._on_action_selected)
        left_layout.addWidget(self.action_list, 1)

        self.splitter.addWidget(left_panel)

        # ---- Right panel (details + goal sender) ------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 30, 20, 20)

        right_title = QLabel("Action Inspector")
        right_title.setProperty("class", "h1")
        right_layout.addWidget(right_title)

        # -- Details card --------------------------------------------------
        self.details_card = QFrame()
        self.details_card.setProperty("class", "card")
        details_card_layout = QVBoxLayout(self.details_card)

        self.lbl_action_name = QLabel("Select an action from the list")
        self.lbl_action_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p['text_primary']};")
        self.lbl_action_name.setWordWrap(True)
        details_card_layout.addWidget(self.lbl_action_name)

        self.lbl_action_type = QLabel("")
        self.lbl_action_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_action_type.setWordWrap(True)
        details_card_layout.addWidget(self.lbl_action_type)

        self.txt_details = QTextEdit()
        self.txt_details.setObjectName("txt_action_details")
        self.txt_details.setReadOnly(True)
        self.txt_details.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 10px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 12px;
                padding: 6px;
            }}
            """
        )
        details_card_layout.addWidget(self.txt_details, 1)
        right_layout.addWidget(self.details_card, 1)

        # -- Goal Sender card -----------------------------------------------
        self.goal_card = QFrame()
        self.goal_card.setProperty("class", "card")
        goal_lay = QVBoxLayout(self.goal_card)
        
        goal_title = QLabel("Send Goal")
        goal_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        goal_lay.addWidget(goal_title)

        self.txt_goal_payload = QTextEdit()
        self.txt_goal_payload.setObjectName("txt_goal_payload")
        self.txt_goal_payload.setPlaceholderText(
            "# Enter your goal payload in YAML format\n# Example:\n# order: 5\n{}"
        )
        self.txt_goal_payload.setFixedHeight(80)
        self.txt_goal_payload.setStyleSheet(
            f"background-color: {p['bg_card']}; color: {p['text_primary']}; border: 1px solid {p['border']}; font-family: monospace;"
        )
        goal_lay.addWidget(self.txt_goal_payload)

        btn_row = QHBoxLayout()
        self.btn_send_goal = QPushButton("Send Goal")
        self.btn_send_goal.setProperty("class", "action-button")
        self.btn_send_goal.setStyleSheet(f"background-color: {p['accent']}; color: white; font-weight: bold;")
        self.btn_send_goal.clicked.connect(self._send_goal)
        btn_row.addWidget(self.btn_send_goal)

        self.btn_cancel_goal = QPushButton("Cancel")
        self.btn_cancel_goal.setEnabled(False)
        self.btn_cancel_goal.clicked.connect(self._cancel_goal)
        btn_row.addWidget(self.btn_cancel_goal)
        btn_row.addStretch()
        goal_lay.addLayout(btn_row)

        self.txt_goal_output = QTextEdit()
        self.txt_goal_output.setObjectName("txt_goal_output")
        self.txt_goal_output.setReadOnly(True)
        self.txt_goal_output.setPlaceholderText("Goal execution output will be displayed here...")
        self.txt_goal_output.setFixedHeight(120)
        self.txt_goal_output.setStyleSheet(
            f"background-color: {p['bg_input']}; color: {p['text_primary']}; border: 1px solid {p['border']}; font-family: monospace; font-size: 11px; border-radius: 10px;"
        )
        goal_lay.addWidget(self.txt_goal_output)
        
        right_layout.addWidget(self.goal_card, 1)
        self.splitter.addWidget(right_panel)

        self.splitter.setSizes([300, 700])

    def refresh_theme(self):
        """Update styles dynamically when theme changes."""
        p = ThemeManager.palette()
        self.action_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 10px;
                color: {p['text_primary']};
                font-size: 14px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-bottom: 1px solid {p['border']};
            }}
            QListWidget::item:selected {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
            }}
            QListWidget::item:hover {{
                background-color: {p['bg_hover']};
            }}
            """
        )
        self.lbl_action_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p['text_primary']};")
        self.lbl_action_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.txt_details.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 10px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 12px;
                padding: 6px;
            }}
            """
        )
        self.txt_goal_payload.setStyleSheet(
            f"background-color: {p['bg_card']}; color: {p['text_primary']}; border: 1px solid {p['border']}; font-family: monospace;"
        )
        self.btn_send_goal.setStyleSheet(f"background-color: {p['accent']}; color: white; font-weight: bold;")
        self.txt_goal_output.setStyleSheet(
            f"background-color: {p['bg_input']}; color: {p['text_primary']}; border: 1px solid {p['border']}; font-family: monospace; font-size: 11px; border-radius: 10px;"
        )
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

    # ------------------------------------------------------------------
    #  Command helpers
    # ------------------------------------------------------------------

    def _build_cmd(self, ros2_args: str) -> list:
        if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            return shlex.split(ros2_args)

        ws = self.workspace_path or (self.cli.workspace_path if self.cli else None)
        use_wsl = bool(self.cli and getattr(self.cli, "use_wsl", False))

        if use_wsl:
            import re
            def to_wsl_path(p):
                p = p.replace('\\', '/')
                m = re.match(r'^([a-zA-Z]):(.*)', p)
                return f"/mnt/{m.group(1).lower()}{m.group(2)}" if m else p
            
            cmd_str = ros2_args
            if ws:
                setup_bash_wsl = to_wsl_path(os.path.join(ws, 'install', 'setup.bash'))
                shell_cmd = f'[ -f "{setup_bash_wsl}" ] && source "{setup_bash_wsl}"; {cmd_str}'
            else:
                shell_cmd = cmd_str
            return ['wsl', 'bash', '-i', '-c', shell_cmd]
        else:
            if ws:
                setup = os.path.join(ws, "install", "setup.bash")
                if os.path.exists(setup):
                    return ["bash", "-c", f'source "{setup}" && {ros2_args}']
            return shlex.split(ros2_args)

    def _sync_worker_in_test(self, worker):
        if worker and (os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules):
            worker.wait()
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

    # ------------------------------------------------------------------
    #  Scanning Actions
    # ------------------------------------------------------------------

    def _refresh_actions(self):
        """Populate active action list in background."""
        if self._list_worker is not None and self._list_worker.isRunning():
            return

        self.action_list.clear()
        self._clear_details()
        self.lbl_status.setText("Scanning...")

        main_win = self.window()
        if main_win and hasattr(main_win, "discovery_cache"):
            cached_actions = main_win.discovery_cache.get("actions", [])
            if cached_actions:
                self.lbl_status.setText("")
                self._on_actions_refreshed("\n".join(cached_actions))
                return

        # Fallback to background runner
        cmd = self._build_cmd("ros2 action list -t")
        self._list_worker = _ActionListWorker(cmd, self)
        self._list_worker.result_ready.connect(self._on_actions_refreshed)
        self._list_worker.start()
        self._sync_worker_in_test(self._list_worker)

    def _on_actions_refreshed(self, output: str):
        self.action_list.clear()
        self.lbl_status.setText("")

        if output.startswith("error:"):
            err_msg = output.replace("error:", "").strip()
            self.lbl_status.setText(err_msg)
            self.txt_details.setText(err_msg)
            return

        self._action_types.clear()
        names = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if '[' in line and ']' in line:
                parts = line.split('[')
                name = parts[0].strip()
                type_str = parts[1].replace(']', '').strip()
                self._action_types[name] = type_str
                names.append(name)
            else:
                self._action_types[line] = "Unknown"
                names.append(line)

        if not names:
            self.lbl_status.setText("No actions found")
            return

        for name in sorted(names):
            self.action_list.addItem(QListWidgetItem(name))

    def _clear_details(self):
        self.lbl_action_name.setText("Select an action from the list")
        self.lbl_action_type.setText("")
        self.txt_details.clear()
        self._current_action = None

    # ------------------------------------------------------------------
    #  Action Details Selection
    # ------------------------------------------------------------------

    def _on_action_selected(self, current: QListWidgetItem, _previous):
        if self._goal_worker and self._goal_worker.isRunning():
            self._cancel_goal()

        if current is None:
            self._clear_details()
            return

        name = current.text()
        self._current_action = name
        self.lbl_action_name.setText(name)
        
        act_type = self._action_types.get(name, "Unknown")
        self.lbl_action_type.setText(f"Type: {act_type}")

        self.txt_details.setText("Loading details...")

        cmd = self._build_cmd(f"ros2 action info {name}")
        self._info_worker = _ActionInfoWorker(cmd, self)
        self._info_worker.result_ready.connect(self._on_info_ready)
        self._info_worker.start()
        self._sync_worker_in_test(self._info_worker)

    def _on_info_ready(self, info: str):
        self.txt_details.setText(info)

    # ------------------------------------------------------------------
    #  Goal Sender
    # ------------------------------------------------------------------

    def _send_goal(self):
        if not self._current_action:
            self.txt_goal_output.setText("Please select an active action first.\n")
            return

        act_type = self._action_types.get(self._current_action, "Unknown")
        if act_type == "Unknown":
            self.txt_goal_output.setText("Cannot send goal: Action type is unknown.\n")
            return

        goal_payload = self.txt_goal_payload.toPlainText().strip()
        if not goal_payload:
            goal_payload = "{}"

        self.txt_goal_output.clear()
        self.txt_goal_output.append(f"Sending goal to action '{self._current_action}'...\n")
        self.btn_send_goal.setEnabled(False)
        self.btn_cancel_goal.setEnabled(True)

        ros2_cmd = f"ros2 action send_goal {self._current_action} {act_type} {shlex.quote(goal_payload)}"
        cmd = self._build_cmd(ros2_cmd)
        
        self._goal_worker = _GoalSenderWorker(cmd, parent=self)
        self._goal_worker.new_line.connect(self._on_goal_output_line)
        self._goal_worker.finished.connect(self._on_goal_finished)
        self._goal_worker.start()

    def _on_goal_output_line(self, line: str):
        self.txt_goal_output.append(line.rstrip('\n'))

    def _on_goal_finished(self, success: bool):
        self.btn_send_goal.setEnabled(True)
        self.btn_cancel_goal.setEnabled(False)
        if success:
            self.txt_goal_output.append("\n✓ Goal succeeded.")
        else:
            self.txt_goal_output.append("\n✗ Goal failed or canceled.")

    def _cancel_goal(self):
        if self._goal_worker and self._goal_worker.isRunning():
            self._goal_worker.terminate_process()
            self._goal_worker.wait(1000)
            self.txt_goal_output.append("\n⚠ Goal execution canceled by user.")
        self.btn_send_goal.setEnabled(True)
        self.btn_cancel_goal.setEnabled(False)
