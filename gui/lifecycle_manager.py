"""
Lifecycle Manager Page, manage ROS2 lifecycle-managed nodes.

Layout
------
QSplitter
├─ Left  (~30 %)  : Title + Refresh button + QListWidget of lifecycle nodes
└─ Right (~70 %)  : Node name label
                    Current state label
                    Available transitions list (read-only)
                    5 fixed transition buttons: Configure, Activate,
                      Deactivate, Cleanup, Shutdown
                    Output console
"""

from gui.theme import ThemeManager

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QListWidget,
    QFrame, QTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal


from gui.thread_utils import _safe_stop_thread


# ---------------------------------------------------------------------------
#  Worker threads
# ---------------------------------------------------------------------------

class _LifecycleListWorker(QThread):
    """Runs lifecycle_nodes() in the background."""
    result_ready = Signal(list)

    def __init__(self, cli, parent=None):
        super().__init__(parent)
        self._cli = cli

    def run(self):
        try:
            nodes = self._cli.lifecycle_nodes()
            self.result_ready.emit(nodes)
        except Exception:
            self.result_ready.emit([])


class _LifecycleStateWorker(QThread):
    """Runs lifecycle_get_state(node) in the background."""
    result_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, cli, node_name: str, parent=None):
        super().__init__(parent)
        self._cli = cli
        self._node_name = node_name

    def run(self):
        try:
            state = self._cli.lifecycle_get_state(self._node_name)
            self.result_ready.emit(state)
        except RuntimeError as exc:
            self.error_occurred.emit(str(exc))
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class _LifecycleTransitionsWorker(QThread):
    """Runs lifecycle_list_transitions(node) in the background."""
    result_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, cli, node_name: str, parent=None):
        super().__init__(parent)
        self._cli = cli
        self._node_name = node_name

    def run(self):
        try:
            transitions = self._cli.lifecycle_list_transitions(self._node_name)
            self.result_ready.emit(transitions)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class _LifecycleSetTransitionWorker(QThread):
    """Runs lifecycle_set_transition(node, transition) in the background."""
    result_ready = Signal(str, str)  # (node, result_text)

    def __init__(self, cli, node_name: str, transition: str, parent=None):
        super().__init__(parent)
        self._cli = cli
        self._node_name = node_name
        self._transition = transition

    def run(self):
        try:
            output = self._cli.lifecycle_set_transition(self._node_name, self._transition)
            self.result_ready.emit(self._node_name, output)
        except RuntimeError as exc:
            self.result_ready.emit(self._node_name, f"Error: {exc}")
        except Exception as exc:
            self.result_ready.emit(self._node_name, f"Error: {exc}")


# ---------------------------------------------------------------------------
#  Main page widget
# ---------------------------------------------------------------------------

_TRANSITIONS = ["configure", "activate", "deactivate", "cleanup", "shutdown"]


class LifecycleManagerPage(QWidget):
    """GUI page for managing ROS2 lifecycle-managed nodes."""

    @staticmethod
    def _parse_transition_names(transitions: list) -> set:
        """Extract transition names from raw CLI output lines.

        Handles formats like:
          - deactivate [4]
          - configure [1]
        """
        result = set()
        for line in transitions:
            line = line.strip()
            # Skip metadata lines like "  Start: active"
            if ':' in line and '[' not in line:
                continue
            line = line.lstrip('-').strip()
            bracket_idx = line.find('[')
            if bracket_idx != -1:
                name = line[:bracket_idx].strip()
            else:
                name = line.strip()
            if name:
                result.add(name)
        return result

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path = None

        self._list_worker = None
        self._state_worker = None
        self._transitions_worker = None
        self._set_worker = None

        self._current_node = None
        self._available_transitions: set = set()

        self._build_ui()
        self.refresh_theme()

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def set_workspace(self, path: str):
        """Store the workspace path so the CLI can source install/setup.bash."""
        self.workspace_path = path
        if self.cli:
            self.cli.set_workspace(path)

    def refresh_lifecycle_nodes(self):
        """Populate the lifecycle node list in the background."""
        if self._list_worker is not None and self._list_worker.isRunning():
            return

        self._node_list.clear()
        self._clear_details()

        if self.cli is None:
            self._append_output("Error: No CLI instance available.")
            return

        self._list_worker = _LifecycleListWorker(self.cli, self)
        self._list_worker.result_ready.connect(self._on_nodes_refreshed)
        self._list_worker.start()

    # ------------------------------------------------------------------
    #  Theme
    # ------------------------------------------------------------------

    def refresh_theme(self):
        """Re-apply theme palette colours to all styled widgets."""
        p = ThemeManager.palette()

        self._btn_refresh.setIcon(ThemeManager.icon("fa5s.sync-alt", "accent"))

        # Left panel — node list
        self._node_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 12px;
                color: {p['text_primary']};
                font-size: 14px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 10px 14px;
                border-radius: 8px;
            }}
            QListWidget::item:hover {{
                background-color: {p['bg_hover']};
            }}
            QListWidget::item:selected {{
                background-color: {p['bg_selected']};
                color: {p['accent']};
            }}
            """
        )

        # Node name label
        self._lbl_node_name.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {p['text_primary']};"
        )

        # Current state value
        self._lbl_state_value.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {p['accent']};"
        )

        # Transitions text area
        mono_style = f"""
            QTextEdit {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                padding: 8px;
            }}
            """
        self._txt_transitions.setStyleSheet(mono_style)
        self._txt_output.setStyleSheet(mono_style)

        # Transition buttons
        btn_style = f"""
            QPushButton {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {p['bg_hover']};
                border: 1px solid {p['accent']};
            }}
            QPushButton:disabled {{
                background-color: {p['bg_hover']};
                color: {p['text_dim']};
            }}
            """
        for btn in self._transition_buttons.values():
            btn.setStyleSheet(btn_style)

        # Splitter handle
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

    # ------------------------------------------------------------------
    #  UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        p = ThemeManager.palette()
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ---- QSplitter -------------------------------------------------
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(2)
        root_layout.addWidget(self._splitter)

        # ---- Left panel (node list) ------------------------------------
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 30, 10, 20)

        left_title = QLabel("Lifecycle Nodes")
        left_title.setObjectName("lifecycle_title_label")
        left_title.setProperty("class", "h1")
        left_layout.addWidget(left_title)

        # Refresh button
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setObjectName("btn_refresh_lifecycle")
        self._btn_refresh.setProperty("class", "action-button")
        self._btn_refresh.setToolTip("Discover lifecycle-managed nodes")
        self._btn_refresh.clicked.connect(self.refresh_lifecycle_nodes)
        left_layout.addWidget(self._btn_refresh)

        # Node list
        self._node_list = QListWidget()
        self._node_list.setObjectName("list_lifecycle_nodes")
        self._node_list.currentItemChanged.connect(self._on_node_selected)
        left_layout.addWidget(self._node_list, 1)

        self._splitter.addWidget(left_panel)

        # ---- Right panel (details + actions) ----------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 30, 20, 20)

        right_title = QLabel("Lifecycle Manager")
        right_title.setProperty("class", "h1")
        right_layout.addWidget(right_title)

        # -- Node name card ------------------------------------------------
        self._details_card = QFrame()
        self._details_card.setProperty("class", "card")
        card_layout = QVBoxLayout(self._details_card)

        self._lbl_node_name = QLabel("Select a node from the list")
        self._lbl_node_name.setObjectName("lbl_selected_node")
        self._lbl_node_name.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {p['text_primary']};"
        )
        self._lbl_node_name.setWordWrap(True)
        card_layout.addWidget(self._lbl_node_name)

        # Current state row
        state_row = QHBoxLayout()
        state_label = QLabel("Current State:")
        state_label.setStyleSheet(f"font-size: 15px; color: {p['text_secondary']};")
        state_row.addWidget(state_label)

        self._lbl_state_value = QLabel("\u2014")
        self._lbl_state_value.setObjectName("lbl_current_state")
        self._lbl_state_value.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {p['accent']};"
        )
        state_row.addWidget(self._lbl_state_value)
        state_row.addStretch()
        card_layout.addLayout(state_row)

        right_layout.addWidget(self._details_card)

        # -- Available transitions -----------------------------------------
        transitions_label = QLabel("Available Transitions:")
        transitions_label.setProperty("class", "section-title")
        right_layout.addWidget(transitions_label)

        self._txt_transitions = QTextEdit()
        self._txt_transitions.setObjectName("text_transitions")
        self._txt_transitions.setReadOnly(True)
        self._txt_transitions.setMaximumHeight(120)
        right_layout.addWidget(self._txt_transitions)

        # -- Execute transition buttons ------------------------------------
        exec_label = QLabel("Execute Transition:")
        exec_label.setProperty("class", "section-title")
        right_layout.addWidget(exec_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._transition_buttons = {}
        for transition in _TRANSITIONS:
            display = transition.capitalize()
            btn = QPushButton(display)
            btn.setObjectName(f"btn_transition_{transition}")
            btn.setEnabled(False)
            btn.clicked.connect(
                lambda checked=False, t=transition: self._on_transition_clicked(t)
            )
            self._transition_buttons[transition] = btn
            btn_row.addWidget(btn)

        btn_row.addStretch()
        right_layout.addLayout(btn_row)

        # -- Output console ------------------------------------------------
        output_label = QLabel("Output:")
        output_label.setProperty("class", "section-title")
        right_layout.addWidget(output_label)

        self._txt_output = QTextEdit()
        self._txt_output.setObjectName("text_output_console")
        self._txt_output.setReadOnly(True)
        self._txt_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self._txt_output, 1)

        self._splitter.addWidget(right_panel)

        # ---- Splitter proportions (30 / 70) ------------------------------
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 7)
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

        self._update_button_states()

    # ------------------------------------------------------------------
    #  Event handlers
    # ------------------------------------------------------------------

    def _on_nodes_refreshed(self, nodes: list):
        """Populate the QListWidget with discovered lifecycle nodes."""
        self._node_list.clear()
        self._clear_details()

        if not nodes:
            self._append_output("No lifecycle-managed nodes found.")
            return

        for node in sorted(nodes):
            self._node_list.addItem(node)

    def _on_node_selected(self, current, _previous):
        """Handle selection of a lifecycle node."""
        if current is None:
            self._clear_details()
            return

        node_name = current.text()
        self._current_node = node_name
        self._lbl_node_name.setText(node_name)

        self._fetch_node_state(node_name)
        self._fetch_node_transitions(node_name)

    def _fetch_node_state(self, node_name: str):
        """Fetch the current lifecycle state for the given node."""
        if self.cli is None:
            self._lbl_state_value.setText("(no CLI)")
            return

        # Cancel any ongoing state fetch
        if self._state_worker is not None and self._state_worker.isRunning():
            self._state_worker.result_ready.disconnect()
            self._state_worker.error_occurred.disconnect()

        self._lbl_state_value.setText("...")

        self._state_worker = _LifecycleStateWorker(self.cli, node_name, self)
        self._state_worker.result_ready.connect(self._on_state_ready)
        self._state_worker.error_occurred.connect(self._on_state_error)
        self._state_worker.start()

    def _on_state_ready(self, state: str):
        self._lbl_state_value.setText(state)
        self._update_button_states()

    def _on_state_error(self, error: str):
        self._lbl_state_value.setText("Unavailable")
        self._append_output(f"[State Error] {self._current_node}: {error}")
        self._update_button_states()

    def _fetch_node_transitions(self, node_name: str):
        """Fetch the available lifecycle transitions for the given node."""
        if self.cli is None:
            self._txt_transitions.setPlainText("(no CLI)")
            return

        # Cancel any ongoing transitions fetch
        if self._transitions_worker is not None and self._transitions_worker.isRunning():
            self._transitions_worker.result_ready.disconnect()
            self._transitions_worker.error_occurred.disconnect()

        # Clear cached transitions while the worker runs — prevents stale
        # transitions from a previous node selection from enabling buttons
        # before the new result arrives.
        self._available_transitions = set()
        self._txt_transitions.setPlainText("Loading...")

        self._transitions_worker = _LifecycleTransitionsWorker(self.cli, node_name, self)
        self._transitions_worker.result_ready.connect(self._on_transitions_ready)
        self._transitions_worker.error_occurred.connect(self._on_transitions_error)
        self._transitions_worker.start()

    def _on_transitions_ready(self, transitions: list):
        if not transitions:
            self._txt_transitions.setPlainText("(none available)")
            self._available_transitions = set()
        else:
            self._txt_transitions.setPlainText("\n".join(transitions))
            self._available_transitions = self._parse_transition_names(transitions)
        self._update_button_states()

    def _on_transitions_error(self, error: str):
        self._txt_transitions.setPlainText("Unavailable")
        self._append_output(f"[Transitions Error] {self._current_node}: {error}")
        self._available_transitions = set()
        self._update_button_states()

    def _on_transition_clicked(self, transition: str):
        """Handle a transition button click."""
        if self._current_node is None:
            self._append_output("No node selected.")
            return

        if self.cli is None:
            self._append_output("Error: No CLI instance available.")
            return

        # Disable buttons while running
        self._set_button_states(False)

        self._append_output(
            f"> ros2 lifecycle set {self._current_node} {transition}"
        )

        self._set_worker = _LifecycleSetTransitionWorker(
            self.cli, self._current_node, transition, self
        )
        self._set_worker.result_ready.connect(self._on_transition_result)
        # Safety net: re-enable buttons when worker finishes, even on unexpected paths
        self._set_worker.finished.connect(self._update_button_states)
        self._set_worker.start()

    def _on_transition_result(self, node_name: str, result: str):
        """Display the transition result and refresh state/transitions."""
        self._append_output(result)

        # Refresh state and transitions after the transition
        if node_name == self._current_node:
            self._fetch_node_state(node_name)
            self._fetch_node_transitions(node_name)
        else:
            self._update_button_states()

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _clear_details(self):
        """Reset the right panel detail widgets."""
        self._lbl_node_name.setText("Select a node from the list")
        self._lbl_state_value.setText("\u2014")
        self._txt_transitions.clear()
        self._current_node = None
        self._available_transitions = set()
        self._update_button_states()

    def _update_button_states(self):
        """Enable only transition buttons whose transition is currently available."""
        base_ok = (
            self._current_node is not None
            and self.cli is not None
        )
        for name, btn in self._transition_buttons.items():
            btn.setEnabled(base_ok and name in self._available_transitions)

    def _set_button_states(self, enabled: bool):
        """Enable or disable all transition buttons."""
        for btn in self._transition_buttons.values():
            btn.setEnabled(enabled)

    def _append_output(self, text: str):
        """Append a line to the output console."""
        existing = self._txt_output.toPlainText()
        if existing:
            self._txt_output.setPlainText(existing + "\n" + text)
        else:
            self._txt_output.setPlainText(text)
        # Scroll to bottom
        cursor = self._txt_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._txt_output.setTextCursor(cursor)

    def cleanup(self):
        """Idempotent shutdown – stop all lifecycle workers."""
        try:
            _safe_stop_thread(self._list_worker)
            _safe_stop_thread(self._state_worker)
            _safe_stop_thread(self._transitions_worker)
            _safe_stop_thread(self._set_worker)
        except Exception:
            pass  # best-effort cleanup
