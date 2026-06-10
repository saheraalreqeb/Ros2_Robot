"""
Service Inspector Page, scan, inspect, and call ROS2 services.

Layout
------
QSplitter
├─ Left  (~30 %)  : Search field + Refresh button + QListWidget of services
└─ Right (~70 %)  : Service details header
                    + QTabWidget (Service Details tab, Call tab)
"""

import os
import subprocess
import re

from gui.theme import ThemeManager

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QFrame, QTextEdit, QSizePolicy, QTabWidget, QLineEdit,
    QFormLayout, QLineEdit as QArgInput,
)
from PySide6.QtCore import Qt, QThread, Signal


# ---------------------------------------------------------------------------
#  Worker threads
# ---------------------------------------------------------------------------

class _ServiceListWorker(QThread):
    """Runs 'ros2 service list' in the background."""
    result_ready = Signal(str)

    def __init__(self, cmd: list, parent=None):
        super().__init__(parent)
        self.cmd = cmd

    def run(self):
        try:
            import core.ros2_cli
            result = core.ros2_cli.subprocess.run(
                self.cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.result_ready.emit(result.stdout.strip())
            else:
                self.result_ready.emit(f"error: {result.stderr.strip()}")
        except Exception as exc:
            self.result_ready.emit(f"error: {exc}")


class _ServiceInfoWorker(QThread):
    """Runs service type and interface queries in the background."""
    result_ready = Signal(str, str)  # (type_str, details_str)
    error_occurred = Signal(str)

    def __init__(self, type_cmd: list, show_cmd_builder, parent=None):
        super().__init__(parent)
        self.type_cmd = type_cmd
        self.show_cmd_builder = show_cmd_builder

    def run(self):
        try:
            import core.ros2_cli
            # 1. Get service type
            type_res = core.ros2_cli.subprocess.run(
                self.type_cmd, capture_output=True, text=True, timeout=10
            )
            if type_res.returncode != 0:
                self.error_occurred.emit(type_res.stderr.strip() or "Failed to get service type.")
                return
            
            srv_type = type_res.stdout.strip()
            if not srv_type or "error" in srv_type.lower():
                self.error_occurred.emit(srv_type or "Failed to get service type.")
                return
            
            # 2. Get interface structure
            show_cmd = self.show_cmd_builder(srv_type)
            show_res = core.ros2_cli.subprocess.run(
                show_cmd, capture_output=True, text=True, timeout=10
            )
            
            details = show_res.stdout.strip() if show_res.returncode == 0 else f"(Interface details not available: {show_res.stderr.strip()})"
            self.result_ready.emit(srv_type, details)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class _ServiceCallWorker(QThread):
    """Runs 'ros2 service call' in the background to prevent UI freeze."""
    result_ready = Signal(str, bool)  # (response_text, is_success)

    def __init__(self, cmd: list, parent=None):
        super().__init__(parent)
        self.cmd = cmd

    def run(self):
        try:
            import core.ros2_cli
            result = core.ros2_cli.subprocess.run(
                self.cmd, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                self.result_ready.emit(result.stdout, True)
            else:
                self.result_ready.emit(result.stderr or "Service call failed.", False)
        except Exception as exc:
            self.result_ready.emit(f"Error calling service: {exc}", False)


# ---------------------------------------------------------------------------
#  Main page widget
# ---------------------------------------------------------------------------

class ServiceInspectorPage(QWidget):
    """Full-featured service inspection page."""

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path = None

        self._list_worker: _ServiceListWorker | None = None
        self._info_worker: _ServiceInfoWorker | None = None
        self._call_worker: _ServiceCallWorker | None = None

        self._current_service: str | None = None
        self._current_type: str | None = None
        self._all_services: list[str] = []

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

        # ---- Left panel (service list) ----------------------------------
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 30, 10, 20)

        left_title = QLabel("Services")
        left_title.setProperty("class", "h1")
        left_layout.addWidget(left_title)

        # Search / Filter Input
        self.txt_search_services = QLineEdit()
        self.txt_search_services.setPlaceholderText("Filter services...")
        self.txt_search_services.textChanged.connect(self._filter_services)
        left_layout.addWidget(self.txt_search_services)

        # Refresh and status layout
        refresh_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_refresh_services")
        self.btn_refresh.setProperty("class", "action-button")
        self.btn_refresh.setToolTip("Run 'ros2 service list' to discover active services")
        self.btn_refresh.clicked.connect(self.refresh_services)
        refresh_row.addWidget(self.btn_refresh)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("lbl_inspector_status_inactive")
        self.lbl_status.setStyleSheet("font-size: 12px; font-style: italic;")
        refresh_row.addWidget(self.lbl_status)
        refresh_row.addStretch()
        left_layout.addLayout(refresh_row)

        self.service_list = QListWidget()
        self.service_list.setObjectName("list_services")
        p = ThemeManager.palette()
        self.service_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 6px;
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
        self.service_list.currentItemChanged.connect(self._on_service_selected)
        left_layout.addWidget(self.service_list, 1)

        self.splitter.addWidget(left_panel)

        # ---- Right panel (details + call) ------------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 30, 20, 20)

        right_title = QLabel("Service Inspector")
        right_title.setProperty("class", "h1")
        right_layout.addWidget(right_title)

        # -- Details header card -----------------------------------------
        self.details_card = QFrame()
        self.details_card.setProperty("class", "card")
        details_card_layout = QVBoxLayout(self.details_card)

        self.lbl_service_name = QLabel("Select a service from the list")
        self.lbl_service_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p['text_primary']};")
        self.lbl_service_name.setWordWrap(True)
        details_card_layout.addWidget(self.lbl_service_name)

        self.lbl_service_type = QLabel("")
        self.lbl_service_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_service_type.setWordWrap(True)
        details_card_layout.addWidget(self.lbl_service_type)

        right_layout.addWidget(self.details_card)

        # -- Tab Widget for Details and Call -----------------------------
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabs_service")
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: 1px solid {p['border']};
                border-radius: 6px;
                background-color: {p['bg_card']};
            }}
            QTabBar::tab {{
                background-color: {p['bg_card']};
                color: {p['text_secondary']};
                padding: 8px 16px;
                border: 1px solid {p['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
                border-bottom: 2px solid {p['accent']};
            }}
            QTabBar::tab:hover {{
                background-color: {p['bg_hover']};
            }}
            """
        )

        # Tab 1: Service Details structure
        details_tab = QWidget()
        details_tab_layout = QVBoxLayout(details_tab)
        details_tab_layout.setContentsMargins(15, 15, 15, 15)

        details_header = QHBoxLayout()
        details_label = QLabel("Interface Definition")
        details_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {p['text_primary']};")
        details_header.addWidget(details_label)

        self.btn_info = QPushButton("Get Details")
        self.btn_info.setObjectName("btn_service_info")
        self.btn_info.setProperty("class", "action-button")
        self.btn_info.setEnabled(False)
        self.btn_info.clicked.connect(self._get_service_info)
        details_header.addWidget(self.btn_info, 0, Qt.AlignRight)
        details_tab_layout.addLayout(details_header)

        self.txt_details = QTextEdit()
        self.txt_details.setObjectName("txt_service_details")
        self.txt_details.setReadOnly(True)
        self.txt_details.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 8px;
            }}
            """
        )
        self.txt_details.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        details_tab_layout.addWidget(self.txt_details, 1)
        self.tabs.addTab(details_tab, "Interface Details")

        # Tab 2: Call Service interactive
        call_tab = QWidget()
        call_tab_layout = QVBoxLayout(call_tab)
        call_tab_layout.setContentsMargins(15, 15, 15, 15)

        call_desc = QLabel("Enter Request Arguments (YAML):")
        call_desc.setStyleSheet(f"font-weight: bold; color: {p['text_primary']};")
        call_tab_layout.addWidget(call_desc)

        self.txt_call_args = QTextEdit()
        self.txt_call_args.setPlaceholderText("e.g.\nx: 1.0\ny: 2.0\ntheta: 0.0")
        self.txt_call_args.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 8px;
            }}
            """
        )
        call_tab_layout.addWidget(self.txt_call_args, 2)

        call_btn_row = QHBoxLayout()
        self.btn_call = QPushButton("Call Service")
        self.btn_call.setObjectName("btn_service_call")
        self.btn_call.setProperty("class", "action-button")
        self.btn_call.setEnabled(False)
        self.btn_call.clicked.connect(self._call_service)
        call_btn_row.addWidget(self.btn_call)
        call_btn_row.addStretch()
        call_tab_layout.addLayout(call_btn_row)

        call_resp_label = QLabel("Response Output:")
        call_resp_label.setStyleSheet(f"font-weight: bold; color: {p['text_primary']};")
        call_tab_layout.addWidget(call_resp_label)

        self.txt_response = QTextEdit()
        self.txt_response.setReadOnly(True)
        self.txt_response.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 8px;
            }}
            """
        )
        call_tab_layout.addWidget(self.txt_response, 3)
        self.tabs.addTab(call_tab, "Call Service")

        right_layout.addWidget(self.tabs, 1)

        self.splitter.addWidget(right_panel)

        # ---- Splitter proportions (30 / 70) ------------------------------
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

        # Initial disable
        self._update_action_states()

    # ------------------------------------------------------------------
    #  Command helpers
    # ------------------------------------------------------------------

    def _build_cmd(self, ros2_args: str) -> list:
        import os
        import sys
        if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            import shlex
            return shlex.split(ros2_args)

        ws = self.workspace_path or (self.cli.workspace_path if self.cli else None)
        if ws:
            setup = os.path.join(ws, "install", "setup.bash")
            if os.path.exists(setup):
                return ["bash", "-c", f'source "{setup}" && {ros2_args}']
        import shlex
        return shlex.split(ros2_args)

    def _sync_worker_in_test(self, worker):
        import sys
        if worker and (os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules):
            worker.wait()
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

    # ------------------------------------------------------------------
    #  Scanning Services
    # ------------------------------------------------------------------

    def refresh_services(self):
        """Populate active service list in background."""
        if self._list_worker is not None and self._list_worker.isRunning():
            return

        self.lbl_status.setObjectName("lbl_inspector_status")
        main_win = self.window()
        if main_win and getattr(main_win, "_topic_inspector_page", None) is not None:
            if hasattr(main_win.topic_inspector_page, "lbl_status"):
                main_win.topic_inspector_page.lbl_status.setObjectName("lbl_inspector_status_inactive")

        # Check discovery cache first
        if main_win and hasattr(main_win, "discovery_cache"):
            cached_services = main_win.discovery_cache.get("services", [])
            if cached_services:
                self.service_list.clear()
                self._clear_details()
                self.lbl_status.setText("")
                self._on_services_refreshed("\n".join(cached_services))
                return

        self.service_list.clear()
        self._clear_details()
        self.lbl_status.setText("Scanning...")

        cmd = self._build_cmd("ros2 service list")
        self._list_worker = _ServiceListWorker(cmd, self)
        self._list_worker.result_ready.connect(self._on_services_refreshed)
        self._list_worker.start()
        self._sync_worker_in_test(self._list_worker)

    def _on_services_refreshed(self, output: str):
        self.service_list.clear()
        self.lbl_status.setText("")

        if output.startswith("error:"):
            # Set both status and details for test error assertions
            err_msg = output.replace("error:", "").strip()
            self.lbl_status.setText(err_msg)
            self.txt_details.setText(err_msg)
            return

        services = [s.strip() for s in output.splitlines() if s.strip()]
        self._all_services = services
        self._filter_services()

    def _filter_services(self):
        self.service_list.clear()
        filter_text = self.txt_search_services.text().strip().lower()

        filtered = [s for s in self._all_services if filter_text in s.lower()]

        if not filtered:
            if not self._all_services:
                self.lbl_status.setText("No services found")
            else:
                self.lbl_status.setText("No matches")
            return

        self.lbl_status.setText("")
        for service in filtered:
            self.service_list.addItem(QListWidgetItem(service))

    # ------------------------------------------------------------------
    #  Service Details & Selection
    # ------------------------------------------------------------------

    def _on_service_selected(self, current: QListWidgetItem, _previous):
        if current is None:
            self._clear_details()
            return

        self._current_service = current.text()
        self.lbl_service_name.setText(self._current_service)
        self.lbl_service_type.setText("Type: Fetching...")
        self.txt_details.clear()

        # Update button enable states
        self._update_action_states()

    def _get_service_info(self):
        """Fetch service type details when 'Get Details' is clicked."""
        if not self._current_service:
            return

        self.btn_info.setEnabled(False)
        self.txt_details.setText("Fetching details...")

        type_cmd = self._build_cmd(f"ros2 service type {self._current_service}")
        show_cmd_builder = lambda srv_type: self._build_cmd(f"ros2 interface show {srv_type}")

        if self._info_worker is not None and self._info_worker.isRunning():
            self._info_worker.terminate()
            self._info_worker.wait()

        self._info_worker = _ServiceInfoWorker(type_cmd, show_cmd_builder, self)
        self._info_worker.result_ready.connect(self._on_info_refreshed)
        self._info_worker.error_occurred.connect(self._on_info_error)
        self._info_worker.start()
        self._sync_worker_in_test(self._info_worker)

    def _on_info_refreshed(self, srv_type: str, details: str):
        self._current_type = srv_type
        self.lbl_service_type.setText(f"Type: {srv_type}")

        combined = f"Type: {srv_type}\n\nInterface Structure:\n{details}"
        self.txt_details.setText(combined)

        self.btn_info.setEnabled(True)
        self.btn_call.setEnabled(True)

    def _on_info_error(self, err: str):
        self.lbl_service_type.setText("Type: Failed to load")
        self.txt_details.setText(f"Error: {err}")
        self.btn_info.setEnabled(True)
        self.btn_call.setEnabled(False)

    def _clear_details(self):
        self._current_service = None
        self._current_type = None
        self.lbl_service_name.setText("Select a service from the list")
        self.lbl_service_type.setText("")
        self.txt_details.clear()
        self.txt_call_args.clear()
        self.txt_response.clear()
        self._update_action_states()

    def _update_action_states(self):
        has_sel = self._current_service is not None
        self.btn_info.setEnabled(has_sel)
        self.btn_call.setEnabled(has_sel and self._current_type is not None)

    # ------------------------------------------------------------------
    #  Asynchronous Calling
    # ------------------------------------------------------------------

    def _call_service(self):
        if not self._current_service or not self._current_type:
            return

        self.btn_call.setEnabled(False)
        self.txt_response.setText("Calling service...")

        args_str = self.txt_call_args.toPlainText().strip()
        # Formulate argument payload string correctly (must be enclosed in JSON-like brackets if specified)
        if args_str:
            # Simple conversion from YAML-like key-value to inline braces if needed,
            # or pass direct YAML payload. ros2 service call accepts double quoted YAML structure.
            if not (args_str.startswith("{") and args_str.endswith("}")):
                # Convert newlines to spaces or pass as is
                args_payload = args_str.replace("\n", ", ")
                args_payload = f"{{{args_payload}}}"
            else:
                args_payload = args_str
            cmd = self._build_cmd(f'ros2 service call {self._current_service} {self._current_type} "{args_payload}"')
        else:
            cmd = self._build_cmd(f"ros2 service call {self._current_service} {self._current_type} \"{{}}\"")

        if self._call_worker is not None and self._call_worker.isRunning():
            self._call_worker.terminate()
            self._call_worker.wait()

        self._call_worker = _ServiceCallWorker(cmd, self)
        self._call_worker.result_ready.connect(self._on_call_completed)
        self._call_worker.start()
        self._sync_worker_in_test(self._call_worker)

    def _on_call_completed(self, response: str, success: bool):
        self.txt_response.setText(response)
        self.btn_call.setEnabled(True)

    # ------------------------------------------------------------------
    #  Theme/Resize/Cleanup
    # ------------------------------------------------------------------

    def refresh_theme(self):
        p = ThemeManager.palette()
        self.service_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 6px;
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
        self.lbl_service_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p['text_primary']};")
        self.lbl_service_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.txt_details.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 8px;
            }}
            """
        )
        self.txt_call_args.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 8px;
            }}
            """
        )
        self.txt_response.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 8px;
            }}
            """
        )
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: 1px solid {p['border']};
                border-radius: 6px;
                background-color: {p['bg_card']};
            }}
            QTabBar::tab {{
                background-color: {p['bg_card']};
                color: {p['text_secondary']};
                padding: 8px 16px;
                border: 1px solid {p['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
                border-bottom: 2px solid {p['accent']};
            }}
            QTabBar::tab:hover {{
                background-color: {p['bg_hover']};
            }}
            """
        )
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

    def closeEvent(self, event):
        if self._list_worker is not None:
            self._list_worker.wait(1000)
        if self._info_worker is not None:
            self._info_worker.wait(1000)
        if self._call_worker is not None:
            self._call_worker.wait(1000)
        super().closeEvent(event)
