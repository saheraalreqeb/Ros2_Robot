"""
Unified Log Viewer Page — consolidate live terminal output and tail ~/.ros/log files.
"""

import os
import glob
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QLineEdit, QLabel, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from gui.theme import ThemeManager


class LogTailerThread(QThread):
    """Tails a ROS 2 log file in the background and emits new lines."""
    new_line = Signal(str)

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        if not os.path.exists(self.filepath):
            self.new_line.emit(f"❌ Log file not found: {self.filepath}")
            return

        try:
            # Read last 500 lines first
            with open(self.filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                initial_chunk = lines[-500:]
                for line in initial_chunk:
                    self.new_line.emit(line.rstrip("\n\r"))

                # Seek to end and tail
                f.seek(0, 2)
                while not self._stop_requested:
                    line = f.readline()
                    if line:
                        self.new_line.emit(line.rstrip("\n\r"))
                    else:
                        self.msleep(100)
        except Exception as e:
            self.new_line.emit(f"❌ [Log Tailer Error]: {e}")


class LogHighlighter(QSyntaxHighlighter):
    """Formats log lines in the text area based on severity level tags."""

    def __init__(self, document, palette):
        super().__init__(document)
        self.formats = {}

        # ERROR / FATAL -> red
        err_fmt = QTextCharFormat()
        err_fmt.setForeground(QColor(palette["danger"]))
        err_fmt.setFontWeight(QFont.Bold)
        self.formats["ERROR"] = err_fmt
        self.formats["FATAL"] = err_fmt

        # WARN / WARNING -> amber
        warn_fmt = QTextCharFormat()
        warn_fmt.setForeground(QColor(palette["warning"]))
        warn_fmt.setFontWeight(QFont.Bold)
        self.formats["WARN"] = warn_fmt
        self.formats["WARNING"] = warn_fmt

        # INFO -> green
        info_fmt = QTextCharFormat()
        info_fmt.setForeground(QColor(palette["success"]))
        self.formats["INFO"] = info_fmt

        # DEBUG -> cyan
        debug_fmt = QTextCharFormat()
        debug_fmt.setForeground(QColor(palette["info"]))
        self.formats["DEBUG"] = debug_fmt

    def highlightBlock(self, text):
        upper_text = text.upper()
        for level, fmt in self.formats.items():
            # Match formats like [ERROR], [INFO], or standalone words like "ERROR:"
            if f"[{level}]" in upper_text or f" {level} " in upper_text or upper_text.startswith(f"{level}:"):
                self.setFormat(0, len(text), fmt)
                break


class UnifiedLogViewerPage(QWidget):
    """Aggregated live log console and ~/.ros/log browser."""

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.tailer_thread = None
        self._live_logs = []  # List of dicts: {"source": str, "message": str}
        self._active_file = None

        self._build_ui()
        self.refresh_log_files()

    def _build_ui(self):
        p = ThemeManager.palette()
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(48, 40, 48, 40)
        root_lay.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(self._icon_label("fa5s.file-alt", "accent", 28))
        hdr.addSpacing(12)
        title = QLabel("Unified Log Viewer")
        title.setProperty("class", "h1")
        hdr.addWidget(title)
        hdr.addStretch()

        btn_refresh = QPushButton(" Refresh Files")
        btn_refresh.setIcon(ThemeManager.icon("fa5s.sync-alt", "accent"))
        btn_refresh.setProperty("class", "action-button")
        btn_refresh.clicked.connect(self.refresh_log_files)
        hdr.addWidget(btn_refresh)
        root_lay.addLayout(hdr)

        sub = QLabel("Aggregate live stdout console output or browse recent ROS 2 log files.")
        sub.setStyleSheet("margin-top: 6px; margin-bottom: 24px;")
        root_lay.addWidget(sub)

        # Splitter Layout
        self.splitter = QSplitter(Qt.Horizontal)
        root_lay.addWidget(self.splitter, 1)

        # Left panel: files list
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 10, 0)
        left_lay.setSpacing(8)

        lbl_list_title = QLabel("LOG SOURCES")
        lbl_list_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {p['text_secondary']};")
        left_lay.addWidget(lbl_list_title)

        self.list_sources = QListWidget()
        self.list_sources.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                color: {p['text_primary']};
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
            """
        )
        self.list_sources.currentItemChanged.connect(self._on_source_selected)
        left_lay.addWidget(self.list_sources)
        self.splitter.addWidget(left_panel)

        # Right panel: console and toolbar
        right_panel = QWidget()
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(10, 0, 0, 0)
        right_lay.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # Search filter
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter logs...")
        self.txt_search.textChanged.connect(self._apply_text_filter)
        toolbar.addWidget(self.txt_search, 1)

        # Level Filters
        self.btn_err = QPushButton("ERR")
        self.btn_err.setCheckable(True)
        self.btn_err.clicked.connect(self._apply_text_filter)
        toolbar.addWidget(self.btn_err)

        self.btn_warn = QPushButton("WARN")
        self.btn_warn.setCheckable(True)
        self.btn_warn.clicked.connect(self._apply_text_filter)
        toolbar.addWidget(self.btn_warn)

        self.btn_info = QPushButton("INFO")
        self.btn_info.setCheckable(True)
        self.btn_info.clicked.connect(self._apply_text_filter)
        toolbar.addWidget(self.btn_info)

        self._style_level_buttons(p)

        # Autoscroll
        self.cb_autoscroll = QCheckBox("Autoscroll")
        self.cb_autoscroll.setChecked(True)
        toolbar.addWidget(self.cb_autoscroll)

        # Clear logs
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_logs)
        toolbar.addWidget(self.btn_clear)
        right_lay.addLayout(toolbar)

        # Monospace Text Box
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 10px;
            }}
            """
        )
        right_lay.addWidget(self.console)
        self.splitter.addWidget(right_panel)

        # Add syntax highlighter
        self.highlighter = LogHighlighter(self.console.document(), p)

        # Set proportions 30% left, 70% right
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

    def _icon_label(self, name, role="normal", size=18):
        lbl = QLabel()
        lbl.setPixmap(ThemeManager.icon(name, role).pixmap(size, size))
        return lbl

    def refresh_log_files(self):
        """Scan ~/.ros/log/ directory and populate the list on the left."""
        self.list_sources.clear()

        # Add Live Feed Option
        live_item = QListWidgetItem("🔴 Live Terminal Stream")
        live_item.setData(Qt.UserRole, "LIVE")
        self.list_sources.addItem(live_item)

        log_dir = os.environ.get("ROS_LOG_DIR", os.path.expanduser("~/.ros/log"))
        if not os.path.exists(log_dir):
            return

        # Scan for run log subdirectories
        run_dirs = sorted(
            [d for d in glob.glob(os.path.join(log_dir, "*")) if os.path.isdir(d) and not d.endswith("latest")],
            key=os.path.getmtime,
            reverse=True
        )

        # Separate latest link
        latest_path = os.path.join(log_dir, "latest")
        latest_resolved = None
        if os.path.exists(latest_path):
            try:
                latest_resolved = os.path.realpath(latest_path)
            except Exception:
                pass

        # Populate Latest Run
        if latest_resolved and os.path.exists(latest_resolved):
            hdr_item = QListWidgetItem("—— LATEST RUN LOGS ——")
            hdr_item.setFlags(Qt.NoItemFlags)
            self.list_sources.addItem(hdr_item)

            for filepath in sorted(glob.glob(os.path.join(latest_resolved, "*.log"))):
                basename = os.path.basename(filepath)
                item = QListWidgetItem(f"📄 {basename}")
                item.setData(Qt.UserRole, filepath)
                self.list_sources.addItem(item)

        # Populate Past Runs
        past_added = False
        for rd in run_dirs:
            # Skip if it is the latest run directory
            if latest_resolved and os.path.realpath(rd) == latest_resolved:
                continue

            if not past_added:
                hdr_item = QListWidgetItem("—— PAST RUN LOGS ——")
                hdr_item.setFlags(Qt.NoItemFlags)
                self.list_sources.addItem(hdr_item)
                past_added = True

            run_name = os.path.basename(rd)
            # Shorten UUIDs
            if len(run_name) > 8:
                run_disp = f"Run: {run_name[:8]}..."
            else:
                run_disp = f"Run: {run_name}"

            for filepath in sorted(glob.glob(os.path.join(rd, "*.log"))):
                basename = os.path.basename(filepath)
                item = QListWidgetItem(f"📁 {run_disp} / {basename}")
                item.setData(Qt.UserRole, filepath)
                self.list_sources.addItem(item)

        # Select Live Feed by default
        self.list_sources.setCurrentRow(0)

    def _on_source_selected(self, current: QListWidgetItem, _prev):
        # Stop existing tailer
        if self.tailer_thread:
            self.tailer_thread.stop()
            self.tailer_thread.wait(1000)
            self.tailer_thread = None

        if not current:
            return

        data = current.data(Qt.UserRole)
        self.clear_logs()

        if data == "LIVE":
            self._active_file = None
            # Load stored live logs
            for log_entry in self._live_logs:
                self._display_log_line(log_entry["source"], log_entry["message"])
        else:
            self._active_file = data
            # Start file tailer
            self.tailer_thread = LogTailerThread(data, self)
            self.tailer_thread.new_line.connect(self.append_file_log)
            self.tailer_thread.start()

    def append_live_log(self, source: str, message: str):
        """Append log lines arriving from running node or launch file subprocesses."""
        log_entry = {"source": source, "message": message}
        self._live_logs.append(log_entry)

        # Cap live log buffer at 2000 lines
        if len(self._live_logs) > 2000:
            self._live_logs.pop(0)

        # Show in console only if we are currently looking at the LIVE source
        if self._active_file is None:
            self._display_log_line(source, message)

    def append_file_log(self, line: str):
        """Callback for log tailer thread."""
        self._display_log_line("", line)

    def _display_log_line(self, source: str, message: str):
        # Format: "[Source] Message" or just "Message"
        full_line = f"[{source}] {message}" if source else message

        # Filter check
        if not self._passes_filter(full_line):
            return

        self.console.appendPlainText(full_line)

        # Handle autoscroll
        if self.cb_autoscroll.isChecked():
            scrollbar = self.console.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _passes_filter(self, line: str) -> bool:
        # 1. Text search
        query = self.txt_search.text().strip().upper()
        if query and query not in line.upper():
            return False

        # 2. Log Level Filter buttons (if any is checked)
        # If no buttons are checked, show everything. If any is checked, restrict to those levels.
        is_err = self.btn_err.isChecked()
        is_warn = self.btn_warn.isChecked()
        is_info = self.btn_info.isChecked()

        if is_err or is_warn or is_info:
            upper_line = line.upper()
            allowed = False
            if is_err and ("ERROR" in upper_line or "FATAL" in upper_line):
                allowed = True
            if is_warn and ("WARN" in upper_line or "WARNING" in upper_line):
                allowed = True
            if is_info and ("INFO" in upper_line):
                allowed = True
            return allowed

        return True

    def _apply_text_filter(self):
        """Reload display since filters changed."""
        self.console.clear()
        if self._active_file is None:
            for log_entry in self._live_logs:
                self._display_log_line(log_entry["source"], log_entry["message"])
        else:
            # For files, it's easier to reload the whole tailed chunk from disk
            # but to be safe and simple, we tail and apply filters. We reload here.
            if os.path.exists(self._active_file):
                try:
                    with open(self._active_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        for line in lines[-500:]:
                            self._display_log_line("", line.rstrip("\n\r"))
                except Exception:
                    pass

    def clear_logs(self):
        self.console.clear()
        if self._active_file is None:
            self._live_logs.clear()

    def closeEvent(self, event):
        if self.tailer_thread:
            self.tailer_thread.stop()
            self.tailer_thread.wait(1000)
        super().closeEvent(event)

    def refresh_theme(self):
        p = ThemeManager.palette()
        self.list_sources.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                color: {p['text_primary']};
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
            """
        )
        self.console.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
                font-size: 13px;
                padding: 10px;
            }}
            """
        )
        self.highlighter = LogHighlighter(self.console.document(), p)
        self._style_level_buttons(p)
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

    def _style_level_buttons(self, p):
        self.btn_err.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {p['text_secondary']};
                border: 1px solid {p['border']};
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {p['bg_hover']};
                color: {p['text_primary']};
            }}
            QPushButton:checked {{
                background-color: {p['danger']};
                color: white;
                border: 1px solid {p['danger']};
            }}
            """
        )
        self.btn_warn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {p['text_secondary']};
                border: 1px solid {p['border']};
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {p['bg_hover']};
                color: {p['text_primary']};
            }}
            QPushButton:checked {{
                background-color: {p['warning']};
                color: white;
                border: 1px solid {p['warning']};
            }}
            """
        )
        self.btn_info.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {p['text_secondary']};
                border: 1px solid {p['border']};
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {p['bg_hover']};
                color: {p['text_primary']};
            }}
            QPushButton:checked {{
                background-color: {p['success']};
                color: white;
                border: 1px solid {p['success']};
            }}
            """
        )
