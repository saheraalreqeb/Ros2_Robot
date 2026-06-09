"""
Parameter Manager Page
======================
Full-featured GUI for inspecting and modifying ROS2 node parameters.

Features:
  - Refresh & select running nodes from a dropdown.
  - Fetch all parameters for a node and display in a table (name, value, editable).
  - Set individual or all changed parameters.
  - Dump all parameters to a YAML file.
  - Load parameters from a YAML file.

All ``ros2 param`` commands are executed via subprocess.  If the current
workspace has been built (i.e. ``install/setup.bash`` exists), commands are
automatically prefixed with ``source <workspace>/install/setup.bash &&``
so that custom message types and parameter descriptions are available.
"""

import os
import subprocess
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QTableWidget, QTableWidgetItem,
    QLineEdit, QHeaderView, QFileDialog, QMessageBox,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QThread, Signal


# ---------------------------------------------------------------------------
#  Background worker – keeps the UI responsive while running ros2 commands
# ---------------------------------------------------------------------------
class _CommandWorker(QThread):
    """Run a shell command in the background and emit the result."""
    finished = Signal(bool, str)  # (success, stdout_or_stderr)

    def __init__(self, cmd: str, cwd: Optional[str] = None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        # Context properties for thread-safe slot forwarding
        self.node_name: Optional[str] = None
        self.row_index: Optional[int] = None
        self.param_name: Optional[str] = None
        self.param_value: Optional[str] = None
        self.file_path: Optional[str] = None

    def run(self):
        try:
            result = subprocess.run(
                self.cmd, shell=True, capture_output=True, text=True, cwd=self.cwd,
            )
            if result.returncode == 0:
                self.finished.emit(True, result.stdout.strip())
            else:
                self.finished.emit(False, result.stderr.strip() or result.stdout.strip())
        except Exception as exc:
            self.finished.emit(False, str(exc))


# ---------------------------------------------------------------------------
#  Main page widget
# ---------------------------------------------------------------------------
class ParameterManagerPage(QWidget):
    """Page for managing ROS2 node parameters."""

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path: Optional[str] = None
        self._workers: list[_CommandWorker] = []  # prevent GC of running threads

        # Derive initial workspace from CLI if available
        if self.cli and hasattr(self.cli, "workspace_path"):
            self.workspace_path = self.cli.workspace_path

        self._setup_ui()

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------
    def set_workspace(self, path: str):
        """Update the workspace path used for sourcing setup.bash."""
        self.workspace_path = path

    # ------------------------------------------------------------------
    #  UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignTop)

        # ---- Title row ----
        title_row = QHBoxLayout()
        title = QLabel("Parameter Manager")
        title.setProperty("class", "h1")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        desc = QLabel(
            "View and modify parameters of running ROS2 nodes. "
            "Select a node, inspect its parameters, change values, "
            "and persist them with Dump / Load."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ---- Node selection card ----
        node_card = QFrame()
        node_card.setProperty("class", "card")
        node_card_layout = QHBoxLayout(node_card)

        lbl_node = QLabel("Node:")
        lbl_node.setStyleSheet("font-weight: bold;")
        node_card_layout.addWidget(lbl_node)

        self.combo_nodes = QComboBox()
        self.combo_nodes.setMinimumWidth(300)
        # No inline style, inherits from global QSS (QComboBox rule in theme.py)
        self.combo_nodes.currentTextChanged.connect(self._on_node_selected)
        node_card_layout.addWidget(self.combo_nodes, 1)

        btn_refresh = QPushButton("Refresh Nodes")
        btn_refresh.setProperty("class", "action-button")
        btn_refresh.setToolTip("Run <b>ros2 node list</b> to discover active nodes.")
        btn_refresh.clicked.connect(self._refresh_nodes)
        node_card_layout.addWidget(btn_refresh)

        layout.addWidget(node_card)

        # ---- Action buttons card ----
        action_card = QFrame()
        action_card.setProperty("class", "card")
        action_layout = QHBoxLayout(action_card)

        btn_apply = QPushButton("Apply All Changes")
        btn_apply.setProperty("class", "action-button")
        btn_apply.setToolTip("Set every parameter whose <i>Set Value</i> column is non-empty.")
        btn_apply.clicked.connect(self._apply_all_changes)
        action_layout.addWidget(btn_apply)

        btn_dump = QPushButton("Dump All")
        btn_dump.setProperty("class", "action-button")
        btn_dump.setToolTip("Run <b>ros2 param dump</b> and save the YAML output to a file.")
        btn_dump.clicked.connect(self._dump_params)
        action_layout.addWidget(btn_dump)

        btn_load = QPushButton("Load YAML")
        btn_load.setProperty("class", "action-button")
        btn_load.setToolTip("Load parameters from a YAML file using <b>ros2 param load</b>.")
        btn_load.clicked.connect(self._load_params)
        action_layout.addWidget(btn_load)

        action_layout.addStretch()
        layout.addWidget(action_card)

        # ---- Parameter table ----
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(4)  # Name | Current Value | Set Value | Action
        self.param_table.setHorizontalHeaderLabels(
            ["Parameter Name", "Current Value", "Set Value", ""]
        )
        self.param_table.horizontalHeader().setStretchLastSection(False)
        self.param_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.param_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.param_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.param_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.param_table.verticalHeader().setVisible(False)
        self.param_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.param_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.param_table.setAlternatingRowColors(True)
        self.param_table.setStyleSheet("")
        layout.addWidget(self.param_table, 1)  # stretch=1 so table fills space

        # ---- Status label ----
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 12px; margin-top: 4px;")
        layout.addWidget(self.lbl_status)

    # ------------------------------------------------------------------
    #  Workspace sourcing helper
    # ------------------------------------------------------------------
    def _source_prefix(self) -> str:
        """Return a bash source prefix if the workspace is built, else empty."""
        if self.workspace_path:
            setup = os.path.join(self.workspace_path, "install", "setup.bash")
            if os.path.exists(setup):
                return f'source "{setup}" && '
        # Also check the CLI's workspace
        if self.cli and hasattr(self.cli, "workspace_path") and self.cli.workspace_path:
            setup = os.path.join(self.cli.workspace_path, "install", "setup.bash")
            if os.path.exists(setup):
                return f'source "{setup}" && '
        return ""

    def _build_cmd(self, ros2_cmd: str) -> str:
        """Wrap a ros2 command with optional workspace sourcing."""
        prefix = self._source_prefix()
        return f"bash -c '{prefix}{ros2_cmd}'"

    # ------------------------------------------------------------------
    #  Node refresh
    # ------------------------------------------------------------------
    def _refresh_nodes(self):
        """Run ``ros2 node list`` and populate the combo box."""
        self._set_status("Refreshing node list…")
        cmd = self._build_cmd("ros2 node list")
        worker = _CommandWorker(cmd)
        worker.finished.connect(self._on_nodes_refreshed)
        self._workers.append(worker)
        worker.start()

    def _on_nodes_refreshed(self, success: bool, output: str):
        if success:
            nodes = [n.strip() for n in output.splitlines() if n.strip()]
            self.combo_nodes.blockSignals(True)
            self.combo_nodes.clear()
            if nodes:
                self.combo_nodes.addItems(nodes)
                self._set_status(f"Found {len(nodes)} node(s).")
            else:
                self._set_status("No running nodes found.")
            self.combo_nodes.blockSignals(False)
            # Trigger parameter load for the first node
            if nodes:
                self._on_node_selected(nodes[0])
            else:
                self.param_table.setRowCount(0)
        else:
            self._set_status(f"Error: {output}")

    # ------------------------------------------------------------------
    #  Parameter listing
    # ------------------------------------------------------------------
    def _on_node_selected(self, node_name: str):
        """Fetch all parameters for *node_name* and display them."""
        if not node_name:
            return
        self._set_status(f"Loading parameters for {node_name}…")
        cmd = self._build_cmd(f"ros2 param list {node_name}")
        worker = _CommandWorker(cmd)
        worker.node_name = node_name
        worker.finished.connect(self._on_param_list)
        self._workers.append(worker)
        worker.start()

    def _on_param_list(self, success: bool, output: str):
        worker = self.sender()
        node_name = worker.node_name if worker else ""
        self.param_table.setRowCount(0)
        if not success:
            self._set_status(f"Failed to list params: {output}")
            return

        params = [p.strip() for p in output.splitlines() if p.strip()]
        if not params:
            self._set_status("Node has no parameters.")
            return

        self.param_table.setRowCount(len(params))

        # For each parameter, kick off a ``ros2 param get`` in the background.
        for row, param_name in enumerate(params):
            # Column 0 – parameter name (read-only)
            item_name = QTableWidgetItem(param_name)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            self.param_table.setItem(row, 0, item_name)

            # Column 1 – current value placeholder
            item_val = QTableWidgetItem("loading…")
            item_val.setFlags(item_val.flags() & ~Qt.ItemIsEditable)
            self.param_table.setItem(row, 1, item_val)

            # Column 2 – editable QLineEdit for new value
            edit = QLineEdit()
            edit.setPlaceholderText("new value")
            self.param_table.setCellWidget(row, 2, edit)

            # Column 3 – per-row Set button
            btn_set = QPushButton("Set")
            btn_set.setProperty("class", "action-button")
            btn_set.setStyleSheet(
                "padding: 4px 12px; font-size: 12px; min-width: 50px;"
            )
            btn_set.clicked.connect(
                lambda _checked, r=row, p=param_name: self._set_single_param(r, p)
            )
            self.param_table.setCellWidget(row, 3, btn_set)

            # Fetch the current value asynchronously
            self._fetch_param_value(node_name, param_name, row)

        self._set_status(f"Loaded {len(params)} parameter(s) for {node_name}.")

    def _fetch_param_value(self, node_name: str, param_name: str, row: int):
        """Run ``ros2 param get <node> <param>`` and fill *row* column 1."""
        cmd = self._build_cmd(f"ros2 param get {node_name} {param_name}")
        worker = _CommandWorker(cmd)
        worker.row_index = row
        worker.finished.connect(self._on_param_value)
        self._workers.append(worker)
        worker.start()

    def _on_param_value(self, success: bool, output: str):
        worker = self.sender()
        if not worker or worker.row_index is None:
            return
        row = worker.row_index
        if row >= self.param_table.rowCount():
            return  # table was reset in the meantime
        if success:
            value_text = output
            if " value is: " in output:
                value_text = output.split(" value is: ", 1)[1]
            item = QTableWidgetItem(value_text)
        else:
            item = QTableWidgetItem("N/A")
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.param_table.setItem(row, 1, item)

    # ------------------------------------------------------------------
    #  Setting parameters
    # ------------------------------------------------------------------
    def _current_node(self) -> str:
        return self.combo_nodes.currentText()

    def _set_single_param(self, row: int, param_name: str):
        """Set a single parameter from the *Set Value* QLineEdit in *row*."""
        node = self._current_node()
        if not node:
            self._set_status("No node selected.")
            return

        edit: QLineEdit = self.param_table.cellWidget(row, 2)
        if edit is None or not edit.text().strip():
            self._set_status(f"No value entered for '{param_name}'.")
            return

        new_value = edit.text().strip()
        self._run_set_param(node, param_name, new_value, row)

    def _apply_all_changes(self):
        """Set every parameter whose *Set Value* column is non-empty."""
        node = self._current_node()
        if not node:
            self._set_status("No node selected.")
            return

        count = 0
        for row in range(self.param_table.rowCount()):
            name_item = self.param_table.item(row, 0)
            edit: QLineEdit = self.param_table.cellWidget(row, 2)
            if name_item and edit and edit.text().strip():
                self._run_set_param(node, name_item.text(), edit.text().strip(), row)
                count += 1

        if count == 0:
            self._set_status("No values to apply – fill in the 'Set Value' column first.")
        else:
            self._set_status(f"Setting {count} parameter(s)…")

    def _run_set_param(self, node: str, param: str, value: str, row: int):
        """Execute ``ros2 param set <node> <param> <value>``."""
        cmd = self._build_cmd(f"ros2 param set {node} {param} {value}")
        worker = _CommandWorker(cmd)
        worker.row_index = row
        worker.param_name = param
        worker.param_value = value
        worker.finished.connect(self._on_param_set)
        self._workers.append(worker)
        worker.start()

    def _on_param_set(self, success: bool, output: str):
        worker = self.sender()
        if not worker or worker.row_index is None or worker.param_name is None or worker.param_value is None:
            return
        row = worker.row_index
        param = worker.param_name
        value = worker.param_value
        if success:
            self._set_status(f"✓ Set '{param}' = {value}")
            # Update the "Current Value" column to reflect the change
            if row < self.param_table.rowCount():
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.param_table.setItem(row, 1, item)
                # Clear the edit field after successful set
                edit: QLineEdit = self.param_table.cellWidget(row, 2)
                if edit:
                    edit.clear()
        else:
            self._set_status(f"✗ Failed to set '{param}': {output}")

    # ------------------------------------------------------------------
    #  Dump parameters
    # ------------------------------------------------------------------
    def _dump_params(self):
        """Run ``ros2 param dump <node>`` and save the output to a YAML file."""
        node = self._current_node()
        if not node:
            self._set_status("No node selected.")
            return

        # Ask the user where to save
        default_name = node.strip("/").replace("/", "_") + "_params.yaml"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Parameter Dump",
            default_name,
            "YAML Files (*.yaml *.yml);;All Files (*)",
        )
        if not filepath:
            return  # user cancelled

        self._set_status(f"Dumping parameters for {node}…")
        cmd = self._build_cmd(f"ros2 param dump {node}")
        worker = _CommandWorker(cmd)
        worker.file_path = filepath
        worker.finished.connect(self._on_dump_finished)
        self._workers.append(worker)
        worker.start()

    def _on_dump_finished(self, success: bool, output: str):
        worker = self.sender()
        filepath = worker.file_path if worker else ""
        if success:
            try:
                with open(filepath, "w", encoding="utf-8") as fh:
                    fh.write(output)
                self._set_status(f"✓ Parameters dumped to {filepath}")
            except OSError as exc:
                self._set_status(f"✗ Failed to write file: {exc}")
        else:
            self._set_status(f"✗ Dump failed: {output}")

    # ------------------------------------------------------------------
    #  Load parameters
    # ------------------------------------------------------------------
    def _load_params(self):
        """Load parameters from a user-chosen YAML file with ``ros2 param load``."""
        node = self._current_node()
        if not node:
            self._set_status("No node selected.")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Parameter File",
            "",
            "YAML Files (*.yaml *.yml);;All Files (*)",
        )
        if not filepath:
            return

        self._set_status(f"Loading parameters from {filepath}…")
        cmd = self._build_cmd(f'ros2 param load {node} "{filepath}"')
        worker = _CommandWorker(cmd)
        worker.finished.connect(self._on_load_finished)
        self._workers.append(worker)
        worker.start()

    def _on_load_finished(self, success: bool, output: str):
        if success:
            self._set_status(f"✓ Parameters loaded. {output}")
            # Refresh the table to show updated values
            node = self._current_node()
            if node:
                self._on_node_selected(node)
        else:
            self._set_status(f"✗ Load failed: {output}")

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------
    def _set_status(self, msg: str):
        """Update the status label at the bottom of the page."""
        self.lbl_status.setText(msg)
