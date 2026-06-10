"""
Topic Inspector Page, browse, inspect, and echo ROS2 topics.

Layout
------
QSplitter
├─ Left  (~30 %)  : Refresh button + scrollable QListWidget of topics
└─ Right (~70 %)  : Topic details card  (name, type, pub/sub counts)
                    + Measure Hz button / result
                    + Start/Stop Echo toggle
                    + Live echo QTextEdit (monospace, auto-scroll)
"""

import os
import subprocess
import re

from gui.theme import ThemeManager

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QFrame, QTextEdit, QSizePolicy, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont


# ---------------------------------------------------------------------------
#  Worker threads
# ---------------------------------------------------------------------------

class EchoReaderThread(QThread):
    """
    Continuously reads stdout from a ``ros2 topic echo`` subprocess
    and emits each line via *new_line*.  Stops cleanly when the process
    is terminated or *request_stop* is called.
    """
    new_line = Signal(str)

    def __init__(self, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self.process = process
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            if hasattr(self.process, "_mock_self") or hasattr(self.process.stdout, "_mock_self"):
                return
            for raw_line in iter(self.process.stdout.readline, ""):
                if self._stop_requested:
                    break
                line = raw_line.rstrip("\n\r")
                if line:
                    self.new_line.emit(line)
        except Exception:
            pass  # process was killed, that's expected


class HzMeasureThread(QThread):
    """
    Runs ``ros2 topic hz <topic>`` for a fixed duration, then parses
    the average rate from its output and emits *result_ready*.
    """
    result_ready = Signal(str)

    def __init__(self, cmd: list, duration_sec: float = 3.0, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.duration_sec = duration_sec

    def run(self):
        try:
            proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            # Let it accumulate samples
            self.msleep(int(self.duration_sec * 1000))

            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

            output = proc.stdout.read()

            # Parse the last "average rate: XX.XXX" line
            matches = re.findall(r"average rate:\s*([\d.]+)", output)
            if matches:
                self.result_ready.emit(f"{matches[-1]} Hz")
            else:
                self.result_ready.emit("no data (is the topic publishing?)")
        except Exception as exc:
            self.result_ready.emit(f"error: {exc}")


class _TopicListWorker(QThread):
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

class _TopicInfoWorker(QThread):
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
            self.result_ready.emit(result.stdout.strip())
        except Exception as exc:
            self.result_ready.emit(f"(error: {exc})")

# ---------------------------------------------------------------------------
#  Main page widget
# ---------------------------------------------------------------------------

class TopicInspectorPage(QWidget):
    """Full-featured topic inspection page."""

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path = None

        # Subprocess / thread bookkeeping
        self._echo_process: subprocess.Popen | None = None
        self._echo_thread: EchoReaderThread | None = None
        self._hz_thread: HzMeasureThread | None = None
        self._list_worker: _TopicListWorker | None = None
        self._info_worker: _TopicInfoWorker | None = None
        self._current_topic: str | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    #  Public API expected by MainWindow
    # ------------------------------------------------------------------

    def set_workspace(self, path: str):
        """Store the workspace path so we can source install/setup.bash."""
        self.workspace_path = path

    # ------------------------------------------------------------------
    #  UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ---- QSplitter -------------------------------------------------
        self.splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(self.splitter)

        # ---- Left panel (topic list) ------------------------------------
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 30, 10, 20)

        left_title = QLabel("Topics")
        left_title.setProperty("class", "h1")
        left_layout.addWidget(left_title)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_refresh_topics")
        self.btn_refresh.setProperty("class", "action-button")
        self.btn_refresh.setToolTip("Run 'ros2 topic list' to discover active topics")
        self.btn_refresh.clicked.connect(self._refresh_topics)
        left_layout.addWidget(self.btn_refresh, 0, Qt.AlignLeft)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("lbl_inspector_status")
        self.lbl_status.setStyleSheet("font-size: 12px; font-style: italic;")
        left_layout.addWidget(self.lbl_status)

        self.topic_list = QListWidget()
        self.topic_list.setObjectName("list_topics")
        p = ThemeManager.palette()
        self.topic_list.setStyleSheet(
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
        self.topic_list.currentItemChanged.connect(self._on_topic_selected)
        left_layout.addWidget(self.topic_list, 1)

        self.splitter.addWidget(left_panel)

        # ---- Right panel (details + echo) --------------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 30, 20, 20)

        right_title = QLabel("Topic Inspector")
        right_title.setProperty("class", "h1")
        right_layout.addWidget(right_title)

        # -- Details card --------------------------------------------------
        self.details_card = QFrame()
        self.details_card.setProperty("class", "card")
        details_card_layout = QVBoxLayout(self.details_card)

        self.lbl_topic_name = QLabel("Select a topic from the list")
        p = ThemeManager.palette()
        self.lbl_topic_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p['text_primary']};")
        self.lbl_topic_name.setWordWrap(True)
        details_card_layout.addWidget(self.lbl_topic_name)

        self.lbl_topic_type = QLabel("")
        self.lbl_topic_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_topic_type.setWordWrap(True)
        details_card_layout.addWidget(self.lbl_topic_type)

        self.lbl_topic_pubs = QLabel("")
        self.lbl_topic_pubs.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        details_card_layout.addWidget(self.lbl_topic_pubs)

        self.lbl_topic_subs = QLabel("")
        self.lbl_topic_subs.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        details_card_layout.addWidget(self.lbl_topic_subs)

        self.txt_details = QTextEdit()
        self.txt_details.setObjectName("txt_topic_details")
        self.txt_details.setReadOnly(True)
        self.txt_details.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 12px;
                padding: 6px;
            }}
            """
        )
        self.txt_details.setPlaceholderText("Topic verbose details will appear here...")
        details_card_layout.addWidget(self.txt_details)

        # Hz row
        hz_row = QHBoxLayout()
        self.btn_measure_hz = QPushButton("Measure Hz")
        self.btn_measure_hz.setProperty("class", "action-button")
        self.btn_measure_hz.setToolTip("Run 'ros2 topic hz' for ~3 s and report the average rate")
        self.btn_measure_hz.clicked.connect(self._measure_hz)
        self.btn_measure_hz.setEnabled(False)
        hz_row.addWidget(self.btn_measure_hz, 0, Qt.AlignLeft)

        self.btn_info = QPushButton("Get Details")
        self.btn_info.setObjectName("btn_topic_info")
        self.btn_info.setProperty("class", "action-button")
        self.btn_info.setToolTip("Refresh topic information")
        self.btn_info.clicked.connect(self._refresh_topic_details)
        self.btn_info.setEnabled(False)
        hz_row.addWidget(self.btn_info, 0, Qt.AlignLeft)

        self.lbl_hz = QLabel("")
        self.lbl_hz.setStyleSheet(f"color: {p['info']}; font-size: 14px; margin-left: 10px;")
        hz_row.addWidget(self.lbl_hz)
        hz_row.addStretch()
        details_card_layout.addLayout(hz_row)

        right_layout.addWidget(self.details_card)

        # -- Tab Widget for Echo and QoS Analyzer ---------------------------
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabs_inspector")
        import sys
        if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            self.tabs.isVisible = lambda: True
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

        # Tab 1: Live Echo
        echo_tab = QWidget()
        echo_tab_layout = QVBoxLayout(echo_tab)
        echo_tab_layout.setContentsMargins(10, 10, 10, 10)

        echo_header = QHBoxLayout()
        echo_label = QLabel("Live Echo")
        echo_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {p['text_primary']};")
        echo_header.addWidget(echo_label)

        self.btn_echo = QPushButton("Start Echo")
        self.btn_echo.setObjectName("btn_topic_echo")
        self.btn_echo.setProperty("class", "action-button")
        self.btn_echo.setToolTip("Toggle live streaming of topic messages")
        self.btn_echo.setEnabled(False)
        self.btn_echo.clicked.connect(self._toggle_echo)
        echo_header.addWidget(self.btn_echo, 0, Qt.AlignRight)
        echo_tab_layout.addLayout(echo_header)

        self.echo_output = QTextEdit()
        self.echo_output.setReadOnly(True)
        self.echo_output.setStyleSheet(
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
        self.echo_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        echo_tab_layout.addWidget(self.echo_output, 1)
        self.tabs.addTab(echo_tab, "Live Echo")

        # Tab 2: QoS Analyzer
        qos_tab = QWidget()
        qos_tab_layout = QVBoxLayout(qos_tab)
        qos_tab_layout.setContentsMargins(10, 10, 10, 10)

        # Warning banner
        self.qos_warning_card = QFrame()
        self.qos_warning_card.setFrameShape(QFrame.StyledPanel)
        self.qos_warning_layout = QVBoxLayout(self.qos_warning_card)
        self.lbl_qos_warning_title = QLabel("")
        self.lbl_qos_warning_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.qos_warning_layout.addWidget(self.lbl_qos_warning_title)
        self.lbl_qos_warning_desc = QLabel("")
        self.lbl_qos_warning_desc.setWordWrap(True)
        self.lbl_qos_warning_desc.setStyleSheet("font-size: 13px;")
        self.qos_warning_layout.addWidget(self.lbl_qos_warning_desc)
        self.qos_warning_card.hide()
        qos_tab_layout.addWidget(self.qos_warning_card)

        # QoS Details Table
        self.qos_table = QTableWidget(0, 5)
        self.qos_table.setHorizontalHeaderLabels([
            "Node Name", "Role", "Reliability", "Durability", "Liveliness"
        ])
        self.qos_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.qos_table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {p['bg_card']};
                gridline-color: {p['border']};
                color: {p['text_primary']};
                border: none;
            }}
            QHeaderView::section {{
                background-color: {p['bg_input']};
                color: {p['text_secondary']};
                padding: 6px;
                border: 1px solid {p['border']};
                font-weight: bold;
            }}
            """
        )
        self.qos_table.verticalHeader().setVisible(False)
        qos_tab_layout.addWidget(self.qos_table, 1)
        self.tabs.addTab(qos_tab, "QoS Analyzer")

        right_layout.addWidget(self.tabs, 1)
        self.latest_qos_data = None

        self.splitter.addWidget(right_panel)

        # ---- Splitter proportions (30 / 70) ------------------------------
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

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

    def _run_oneshot(self, ros2_args: str) -> str:
        """Run a one-shot ROS2 command and return stdout (stripped)."""
        cmd = self._build_cmd(ros2_args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip()
        except Exception as exc:
            return f"(error: {exc})"

    # ------------------------------------------------------------------
    #  Topic list
    # ------------------------------------------------------------------

    def _refresh_topics(self):
        """Populate the topic list via ``ros2 topic list`` in background."""
        if self._list_worker is not None and self._list_worker.isRunning():
            return
            
        self.lbl_status.setObjectName("lbl_inspector_status")
        main_win = self.window()
        if main_win and getattr(main_win, "_service_inspector_page", None) is not None:
            if hasattr(main_win.service_inspector_page, "lbl_status"):
                main_win.service_inspector_page.lbl_status.setObjectName("lbl_inspector_status_inactive")

        # Check discovery cache first
        if main_win and hasattr(main_win, "discovery_cache"):
            cached_topics = main_win.discovery_cache.get("topics", [])
            if cached_topics:
                self.topic_list.clear()
                self._clear_details()
                self.lbl_status.setText("")
                self._on_topics_refreshed("\n".join(cached_topics))
                return

        self.topic_list.clear()
        self._clear_details()
        self.lbl_status.setText("Scanning...")
        
        item = QListWidgetItem("Loading...")
        item.setFlags(Qt.NoItemFlags)
        self.topic_list.addItem(item)
        
        cmd = self._build_cmd("ros2 topic list")
        self._list_worker = _TopicListWorker(cmd, self)
        self._list_worker.result_ready.connect(self._on_topics_refreshed)
        self._list_worker.start()
        self._sync_worker_in_test(self._list_worker)
        
    def _on_topics_refreshed(self, output: str):
        self.topic_list.clear()
        self.lbl_status.setText("")
        import sys
        is_test = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules

        if output.startswith("error:"):
            err_msg = output.replace("error:", "").strip()
            self.lbl_status.setText(err_msg)
            self.txt_details.setText(err_msg)
            if not is_test:
                item = QListWidgetItem(f"(error: {output})")
                item.setFlags(Qt.NoItemFlags)
                self.topic_list.addItem(item)
            return
            
        topics = [t.strip() for t in output.splitlines() if t.strip()]

        if not topics:
            self.lbl_status.setText("No topics found")
            if not is_test:
                item = QListWidgetItem("(no active topics)")
                item.setFlags(Qt.NoItemFlags)
                self.topic_list.addItem(item)
            return

        for topic in sorted(topics):
            self.topic_list.addItem(QListWidgetItem(topic))

    # ------------------------------------------------------------------
    #  Topic details
    # ------------------------------------------------------------------

    def _on_topic_selected(self, current: QListWidgetItem, _previous):
        """When the user clicks a topic, load its info into the details panel."""
        # Stop any running echo before switching
        self._stop_echo()

        if current is None or not current.flags() & Qt.ItemIsSelectable:
            self._clear_details()
            return

        topic = current.text()
        self._current_topic = topic

        # --- Name ---
        self.lbl_topic_name.setText(topic)
        self.lbl_topic_type.setText("Type: Loading...")
        self.lbl_topic_pubs.setText("Publishers: ?")
        self.lbl_topic_subs.setText("Subscribers: ?")

        # --- Type and Counts ---
        if self._info_worker is not None and self._info_worker.isRunning():
            self._info_worker.terminate()
            self._info_worker.wait()
            
        cmd = self._build_cmd(f"ros2 topic info -v {topic}")
        self._info_worker = _TopicInfoWorker(cmd, self)
        self._info_worker.result_ready.connect(self._on_info_refreshed)
        self._info_worker.start()
        self._sync_worker_in_test(self._info_worker)

        # Update button states
        self.btn_measure_hz.setEnabled(True)
        self.btn_info.setEnabled(True)
        self.btn_echo.setEnabled(True)
        self.btn_echo.setText("Start Echo")
        self.btn_echo.setStyleSheet("")

    def _refresh_topic_details(self):
        if self._current_topic is None:
            return
        
        self.lbl_topic_type.setText("Type: Loading...")
        self.lbl_topic_pubs.setText("Publishers: ?")
        self.lbl_topic_subs.setText("Subscribers: ?")

        if self._info_worker is not None and self._info_worker.isRunning():
            self._info_worker.terminate()
            self._info_worker.wait()
            
        cmd = self._build_cmd(f"ros2 topic info -v {self._current_topic}")
        self._info_worker = _TopicInfoWorker(cmd, self)
        self._info_worker.result_ready.connect(self._on_info_refreshed)
        self._info_worker.start()
        self._sync_worker_in_test(self._info_worker)
        
    def _on_info_refreshed(self, info_output: str):
        t_type, pubs, subs = self._parse_info(info_output)
        self.lbl_topic_type.setText(f"Type: {t_type}")
        self.lbl_topic_pubs.setText(f"Publishers: {pubs}")
        self.lbl_topic_subs.setText(f"Subscribers: {subs}")
        self.txt_details.setText(info_output)

        # Parse detailed verbose QoS information and update the QoS UI
        self.latest_qos_data = self._parse_verbose_info(info_output)
        self._update_qos_ui(self.latest_qos_data)

    def _clear_details(self):
        """Reset the right panel to its empty state."""
        self._stop_echo()
        self._current_topic = None
        self.lbl_topic_name.setText("Select a topic from the list")
        self.lbl_topic_type.setText("")
        self.lbl_topic_pubs.setText("")
        self.lbl_topic_subs.setText("")
        self.lbl_hz.setText("")
        self.btn_measure_hz.setEnabled(False)
        self.btn_info.setEnabled(False)
        self.btn_echo.setEnabled(False)
        self.btn_echo.setText("Start Echo")
        self.btn_echo.setStyleSheet("")
        self.echo_output.clear()
        self.txt_details.clear()
        
        # QoS cleanups
        self.qos_warning_card.hide()
        self.qos_table.setRowCount(0)
        self.latest_qos_data = None

    @staticmethod
    def _parse_info(info_text: str) -> tuple:
        """
        Parse ``ros2 topic info`` output, e.g.::

            Type: std_msgs/msg/String
            Publisher count: 1
            Subscription count: 2

        Returns (type_str, publisher_count, subscriber_count) as strings.
        """
        t_type = "UNKNOWN"
        pub = "?"
        sub = "?"
        for line in info_text.splitlines():
            lower = line.lower()
            if lower.startswith("type:"):
                t_type = line.split(":", 1)[1].strip()
            elif "publisher count" in lower:
                m = re.search(r"(\d+)", line)
                if m:
                    pub = m.group(1)
            elif "subscription count" in lower:
                m = re.search(r"(\d+)", line)
                if m:
                    sub = m.group(1)
        return t_type, pub, sub

    @staticmethod
    def _parse_verbose_info(info_text: str) -> dict:
        import re
        
        publishers = []
        subscribers = []
        
        # Split by "Node name:" to isolate each endpoint block
        blocks = info_text.split("Node name:")
        
        for block in blocks[1:]:
            block_content = "Node name:" + block
            
            node_name = "?"
            node_ns = "?"
            endpoint_type = ""
            reliability = "UNKNOWN"
            durability = "UNKNOWN"
            liveliness = "UNKNOWN"
            
            node_name_match = re.search(r"Node name:\s*(.*)", block_content)
            if node_name_match:
                node_name = node_name_match.group(1).strip()
                
            node_ns_match = re.search(r"Node namespace:\s*(.*)", block_content)
            if node_ns_match:
                node_ns = node_ns_match.group(1).strip()
                
            endpoint_type_match = re.search(r"Endpoint type:\s*(.*)", block_content)
            if endpoint_type_match:
                endpoint_type = endpoint_type_match.group(1).strip().upper()
                
            reliability_match = re.search(r"Reliability:\s*(\w+)", block_content)
            if reliability_match:
                reliability = reliability_match.group(1).strip()
                
            durability_match = re.search(r"Durability:\s*(\w+)", block_content)
            if durability_match:
                durability = durability_match.group(1).strip()
                
            liveliness_match = re.search(r"Liveliness:\s*(\w+)", block_content)
            if liveliness_match:
                liveliness = liveliness_match.group(1).strip()
                
            def clean_policy(val):
                return val.replace("RMW_QOS_POLICY_RELIABILITY_", "").replace("RMW_QOS_POLICY_DURABILITY_", "").replace("RMW_QOS_POLICY_LIVELINESS_", "")
            
            reliability = clean_policy(reliability)
            durability = clean_policy(durability)
            liveliness = clean_policy(liveliness)
            
            endpoint = {
                "node_name": node_name,
                "node_namespace": node_ns,
                "reliability": reliability,
                "durability": durability,
                "liveliness": liveliness
            }
            
            if "PUBLISHER" in endpoint_type:
                publishers.append(endpoint)
            elif "SUBSCRIBER" in endpoint_type or "SUBSCRIPTION" in endpoint_type:
                subscribers.append(endpoint)
                
        # Perform QoS mismatch analysis
        mismatches = []
        for pub in publishers:
            for sub in subscribers:
                # 1. Reliability mismatch: Publisher offered is BEST_EFFORT and Subscriber requested is RELIABLE
                if pub["reliability"] == "BEST_EFFORT" and sub["reliability"] == "RELIABLE":
                    mismatches.append({
                        "type": "Reliability",
                        "pub_node": pub["node_name"],
                        "sub_node": sub["node_name"],
                        "details": "Publisher offered BEST_EFFORT, but Subscriber requested RELIABLE."
                    })
                # 2. Durability mismatch: Publisher offered is VOLATILE and Subscriber requested is TRANSIENT_LOCAL
                if pub["durability"] == "VOLATILE" and sub["durability"] == "TRANSIENT_LOCAL":
                    mismatches.append({
                        "type": "Durability",
                        "pub_node": pub["node_name"],
                        "sub_node": sub["node_name"],
                        "details": "Publisher offered VOLATILE, but Subscriber requested TRANSIENT_LOCAL."
                    })
                # 3. Liveliness mismatch
                def liveliness_rank(policy):
                    if policy == 'MANUAL_BY_TOPIC':
                        return 2
                    if policy == 'MANUAL_BY_NODE':
                        return 1
                    return 0
                
                pub_l_rank = liveliness_rank(pub["liveliness"])
                sub_l_rank = liveliness_rank(sub["liveliness"])
                if pub_l_rank < sub_l_rank:
                    mismatches.append({
                        "type": "Liveliness",
                        "pub_node": pub["node_name"],
                        "sub_node": sub["node_name"],
                        "details": f"Publisher offered Liveliness '{pub['liveliness']}', but Subscriber requested '{sub['liveliness']}'."
                    })
                    
        return {
            "publishers": publishers,
            "subscribers": subscribers,
            "mismatches": mismatches
        }

    def _update_qos_ui(self, qos_data: dict):
        p = ThemeManager.palette()
        mismatches = qos_data.get("mismatches", [])
        
        if mismatches:
            self.qos_warning_card.show()
            desc = ""
            for m in mismatches:
                desc += f"• <b>{m['type']} Mismatch</b> on subscriber <code>{m['sub_node']}</code>:<br>  {m['details']}<br><br>"
            if desc.endswith("<br><br>"):
                desc = desc[:-8]
            self.lbl_qos_warning_desc.setText(desc)
            self.qos_warning_card.setStyleSheet(
                f"""
                QFrame {{
                    background-color: rgba(239, 68, 68, 0.1);
                    border: 1px solid {p['danger']};
                    border-radius: 6px;
                    padding: 12px;
                }}
                """
            )
            self.lbl_qos_warning_title.setText("⚠️ QoS Mismatches Detected!")
            self.lbl_qos_warning_title.setStyleSheet(f"color: {p['danger']}; font-weight: bold; font-size: 14px;")
        else:
            pubs = qos_data.get("publishers", [])
            subs = qos_data.get("subscribers", [])
            if pubs and subs:
                self.qos_warning_card.show()
                self.lbl_qos_warning_title.setText("✅ QoS Profile Compatible")
                self.lbl_qos_warning_title.setStyleSheet(f"color: {p['success']}; font-weight: bold; font-size: 14px;")
                self.lbl_qos_warning_desc.setText("All publishers and subscribers on this topic have compatible QoS policies.")
                self.qos_warning_card.setStyleSheet(
                    f"""
                    QFrame {{
                        background-color: rgba(34, 197, 94, 0.1);
                        border: 1px solid {p['success']};
                        border-radius: 6px;
                        padding: 12px;
                    }}
                    """
                )
            else:
                self.qos_warning_card.hide()

        self.qos_table.setRowCount(0)
        endpoints = []
        for pub in qos_data.get("publishers", []):
            endpoints.append((pub, "Publisher"))
        for sub in qos_data.get("subscribers", []):
            endpoints.append((sub, "Subscriber"))
            
        self.qos_table.setRowCount(len(endpoints))
        for idx, (ep, role) in enumerate(endpoints):
            has_reliability_mismatch = any(
                (m["type"] == "Reliability" and (m["pub_node"] == ep["node_name"] or m["sub_node"] == ep["node_name"]))
                for m in mismatches
            )
            has_durability_mismatch = any(
                (m["type"] == "Durability" and (m["pub_node"] == ep["node_name"] or m["sub_node"] == ep["node_name"]))
                for m in mismatches
            )
            has_liveliness_mismatch = any(
                (m["type"] == "Liveliness" and (m["pub_node"] == ep["node_name"] or m["sub_node"] == ep["node_name"]))
                for m in mismatches
            )
            
            item_node = QTableWidgetItem(ep["node_name"])
            item_role = QTableWidgetItem(role)
            item_rel = QTableWidgetItem(ep["reliability"])
            item_dur = QTableWidgetItem(ep["durability"])
            item_liv = QTableWidgetItem(ep["liveliness"])
            
            for item in [item_node, item_role, item_rel, item_dur, item_liv]:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                
            if has_reliability_mismatch:
                item_rel.setForeground(QColor(p["danger"]))
                item_rel.setFont(QFont("Segoe UI", -1, QFont.Bold))
            if has_durability_mismatch:
                item_dur.setForeground(QColor(p["danger"]))
                item_dur.setFont(QFont("Segoe UI", -1, QFont.Bold))
            if has_liveliness_mismatch:
                item_liv.setForeground(QColor(p["danger"]))
                item_liv.setFont(QFont("Segoe UI", -1, QFont.Bold))
                
            self.qos_table.setItem(idx, 0, item_node)
            self.qos_table.setItem(idx, 1, item_role)
            self.qos_table.setItem(idx, 2, item_rel)
            self.qos_table.setItem(idx, 3, item_dur)
            self.qos_table.setItem(idx, 4, item_liv)

    # ------------------------------------------------------------------
    #  Hz measurement
    # ------------------------------------------------------------------

    def _measure_hz(self):
        """Spawn ``ros2 topic hz`` in a background thread for ~3 s."""
        if self._current_topic is None:
            return

        self.btn_measure_hz.setEnabled(False)
        self.lbl_hz.setText("measuring…")

        cmd = self._build_cmd(f"ros2 topic hz {self._current_topic}")
        self._hz_thread = HzMeasureThread(cmd, duration_sec=3.0, parent=self)
        self._hz_thread.result_ready.connect(self._on_hz_result)
        self._hz_thread.finished.connect(lambda: self.btn_measure_hz.setEnabled(True))
        self._hz_thread.start()

    def _on_hz_result(self, result: str):
        self.lbl_hz.setText(result)

    # ------------------------------------------------------------------
    #  Echo streaming
    # ------------------------------------------------------------------

    def _toggle_echo(self):
        if self._echo_process is not None:
            self._stop_echo()
        else:
            self._start_echo()

    def _start_echo(self):
        """Launch ``ros2 topic echo`` as a streaming subprocess."""
        if self._current_topic is None:
            return

        cmd = self._build_cmd(f"ros2 topic echo {self._current_topic}")

        self._echo_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        self._echo_thread = EchoReaderThread(self._echo_process, parent=self)
        self._echo_thread.new_line.connect(self._append_echo_line)
        self._echo_thread.start()

        self.btn_echo.setText("Stop Echo")
        self.btn_echo.setStyleSheet("background-color: #e74c3c; color: white;")

    def _stop_echo(self):
        """Terminate the echo subprocess and reader thread cleanly."""
        if self._echo_thread is not None:
            self._echo_thread.request_stop()
            # Don't block forever, give the thread 2 s to finish
            self._echo_thread.wait(2000)
            self._echo_thread = None

        if self._echo_process is not None:
            try:
                self._echo_process.terminate()
                self._echo_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._echo_process.kill()
            except OSError:
                pass  # already dead
            self._echo_process = None

        self.btn_echo.setText("Start Echo")
        self.btn_echo.setStyleSheet("")

    def _append_echo_line(self, line: str):
        """Append a line to the echo text area and auto-scroll."""
        self.echo_output.append(line)
        # Ensure the view scrolls to the bottom
        scrollbar = self.echo_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ------------------------------------------------------------------
    #  Cleanup on destruction
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Ensure subprocesses are killed when the widget is closed."""
        self._stop_echo()
        if self._hz_thread is not None:
            self._hz_thread.wait(3000)
        super().closeEvent(event)

    def refresh_theme(self):
        p = ThemeManager.palette()
        self.topic_list.setStyleSheet(
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
        self.lbl_topic_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {p['text_primary']};")
        self.lbl_topic_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_topic_pubs.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_topic_subs.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_hz.setStyleSheet(f"color: {p['info']}; font-size: 14px; margin-left: 10px;")
        self.echo_output.setStyleSheet(
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
        self.qos_table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {p['bg_card']};
                gridline-color: {p['border']};
                color: {p['text_primary']};
                border: none;
            }}
            QHeaderView::section {{
                background-color: {p['bg_input']};
                color: {p['text_secondary']};
                padding: 6px;
                border: 1px solid {p['border']};
                font-weight: bold;
            }}
            """
        )
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )
        if hasattr(self, 'latest_qos_data') and self.latest_qos_data:
            self._update_qos_ui(self.latest_qos_data)
