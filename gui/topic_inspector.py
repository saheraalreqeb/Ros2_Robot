"""
Topic Inspector Page — browse, inspect, and echo ROS2 topics.

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
    QFrame, QTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer


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
            for raw_line in iter(self.process.stdout.readline, ""):
                if self._stop_requested:
                    break
                line = raw_line.rstrip("\n\r")
                if line:
                    self.new_line.emit(line)
        except Exception:
            pass  # process was killed — that's expected


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
            result = subprocess.run(
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
            result = subprocess.run(
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
        self.btn_refresh.setProperty("class", "action-button")
        self.btn_refresh.setToolTip("Run 'ros2 topic list' to discover active topics")
        self.btn_refresh.clicked.connect(self._refresh_topics)
        left_layout.addWidget(self.btn_refresh, 0, Qt.AlignLeft)

        self.topic_list = QListWidget()
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

        self.lbl_msg_type = QLabel("")
        self.lbl_msg_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_msg_type.setWordWrap(True)
        details_card_layout.addWidget(self.lbl_msg_type)

        self.lbl_pub_count = QLabel("")
        self.lbl_pub_count.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        details_card_layout.addWidget(self.lbl_pub_count)

        self.lbl_sub_count = QLabel("")
        self.lbl_sub_count.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        details_card_layout.addWidget(self.lbl_sub_count)

        # Hz row
        hz_row = QHBoxLayout()
        self.btn_measure_hz = QPushButton("Measure Hz")
        self.btn_measure_hz.setProperty("class", "action-button")
        self.btn_measure_hz.setToolTip("Run 'ros2 topic hz' for ~3 s and report the average rate")
        self.btn_measure_hz.clicked.connect(self._measure_hz)
        self.btn_measure_hz.setEnabled(False)
        hz_row.addWidget(self.btn_measure_hz, 0, Qt.AlignLeft)

        self.lbl_hz = QLabel("")
        self.lbl_hz.setStyleSheet(f"color: {p['info']}; font-size: 14px; margin-left: 10px;")
        hz_row.addWidget(self.lbl_hz)
        hz_row.addStretch()
        details_card_layout.addLayout(hz_row)

        right_layout.addWidget(self.details_card)

        # -- Echo controls -------------------------------------------------
        echo_header = QHBoxLayout()
        echo_label = QLabel("Live Echo")
        echo_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {p['text_primary']}; margin-top: 12px;")
        echo_header.addWidget(echo_label)

        self.btn_echo = QPushButton("Start Echo")
        self.btn_echo.setProperty("class", "action-button")
        self.btn_echo.setToolTip("Toggle live streaming of topic messages")
        self.btn_echo.setEnabled(False)
        self.btn_echo.clicked.connect(self._toggle_echo)
        echo_header.addWidget(self.btn_echo, 0, Qt.AlignRight)
        right_layout.addLayout(echo_header)

        # -- Echo output area -----------------------------------------------
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
        right_layout.addWidget(self.echo_output, 1)

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
        """
        Build a shell command list.  If a workspace with install/setup.bash
        is available, source it first.
        """
        ws = self.workspace_path or (self.cli.workspace_path if self.cli else None)
        if ws:
            setup = os.path.join(ws, "install", "setup.bash")
            if os.path.exists(setup):
                return ["bash", "-c", f'source "{setup}" && {ros2_args}']
        return ["bash", "-c", ros2_args]

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
            
        self.topic_list.clear()
        self._clear_details()
        
        item = QListWidgetItem("Loading...")
        item.setFlags(Qt.NoItemFlags)
        self.topic_list.addItem(item)
        
        cmd = self._build_cmd("ros2 topic list")
        self._list_worker = _TopicListWorker(cmd, self)
        self._list_worker.result_ready.connect(self._on_topics_refreshed)
        self._list_worker.start()
        
    def _on_topics_refreshed(self, output: str):
        self.topic_list.clear()
        if output.startswith("error:"):
            item = QListWidgetItem(f"(error: {output})")
            item.setFlags(Qt.NoItemFlags)
            self.topic_list.addItem(item)
            return
            
        topics = [t.strip() for t in output.splitlines() if t.strip()]

        if not topics:
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
            
        cmd = self._build_cmd(f"ros2 topic info {topic}")
        self._info_worker = _TopicInfoWorker(cmd, self)
        self._info_worker.result_ready.connect(self._on_info_refreshed)
        self._info_worker.start()

        # Update button states
        self.btn_measure_hz.setEnabled(True)
        self.btn_echo.setEnabled(True)
        self.btn_echo.setText("Start Echo")
        self.btn_echo.setStyleSheet("")
        
    def _on_info_refreshed(self, info_output: str):
        t_type, pubs, subs = self._parse_info(info_output)
        self.lbl_topic_type.setText(f"Type: {t_type}")
        self.lbl_topic_pubs.setText(f"Publishers: {pubs}")
        self.lbl_topic_subs.setText(f"Subscribers: {subs}")

    def _clear_details(self):
        """Reset the right panel to its empty state."""
        self._stop_echo()
        self._current_topic = None
        self.lbl_topic_name.setText("Select a topic from the list")
        self.lbl_msg_type.setText("")
        self.lbl_pub_count.setText("")
        self.lbl_sub_count.setText("")
        self.lbl_hz.setText("")
        self.btn_measure_hz.setEnabled(False)
        self.btn_echo.setEnabled(False)
        self.btn_echo.setText("Start Echo")
        self.btn_echo.setStyleSheet("")
        self.echo_output.clear()

    @staticmethod
    def _parse_info(info_text: str) -> tuple:
        """
        Parse ``ros2 topic info`` output, e.g.::

            Type: std_msgs/msg/String
            Publisher count: 1
            Subscription count: 2

        Returns (publisher_count, subscriber_count) as strings.
        """
        pub = "?"
        sub = "?"
        for line in info_text.splitlines():
            lower = line.lower()
            if "publisher count" in lower:
                m = re.search(r"(\d+)", line)
                if m:
                    pub = m.group(1)
            elif "subscription count" in lower:
                m = re.search(r"(\d+)", line)
                if m:
                    sub = m.group(1)
        return pub, sub

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
            # Don't block forever — give the thread 2 s to finish
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
        self.lbl_msg_type.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_pub_count.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
        self.lbl_sub_count.setStyleSheet(f"color: {p['text_secondary']}; font-size: 14px;")
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
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )
