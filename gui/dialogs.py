import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QFormLayout, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QPoint


def center_dialog_on_parent(dialog: QDialog):
    """Centers *dialog* over its parent window or top-level MainWindow using global screen coordinates."""
    parent = dialog.parentWidget() or dialog.parent()
    top_level = None
    if parent:
        top_level = parent.window() if hasattr(parent, 'window') else parent
    if not top_level:
        from PySide6.QtWidgets import QApplication
        top_level = QApplication.activeWindow()

    if top_level and dialog:
        top_left = top_level.mapToGlobal(QPoint(0, 0))
        parent_w = top_level.width()
        parent_h = top_level.height()

        center_x = top_left.x() + parent_w // 2
        center_y = top_left.y() + parent_h // 2

        dialog_w = dialog.width() if dialog.width() > 0 else (dialog.sizeHint().width() if dialog.sizeHint().width() > 0 else 400)
        dialog_h = dialog.height() if dialog.height() > 0 else (dialog.sizeHint().height() if dialog.sizeHint().height() > 0 else 250)

        x = max(0, center_x - dialog_w // 2)
        y = max(0, center_y - dialog_h // 2)

        dialog.move(x, y)


class InitWorkspaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Initialize New Workspace")
        self.resize(480, 180)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. my_ros2_ws")
        form_layout.addRow("Workspace Name:", self.name_edit)

        path_layout = QHBoxLayout()
        default_dir = os.path.expanduser("~")
        self.path_edit = QLineEdit(default_dir)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_location)

        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(self.browse_btn)

        form_layout.addRow("Location:", path_layout)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Create")
        self.cancel_btn = QPushButton("Cancel")

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _browse_location(self):
        current = self.path_edit.text().strip() or os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Parent Directory",
            current,
            options=QFileDialog.DontUseNativeDialog
        )
        if dir_path:
            self.path_edit.setText(dir_path)

    def showEvent(self, event):
        super().showEvent(event)
        center_dialog_on_parent(self)
        QTimer.singleShot(0, lambda: center_dialog_on_parent(self))

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "location": self.path_edit.text().strip()
        }


class CreatePackageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create ROS2 Package")
        self.resize(400, 200)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.name_edit = QLineEdit()
        form_layout.addRow("Package Name:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["ament_python", "ament_cmake"])
        form_layout.addRow("Build Type:", self.type_combo)

        self.deps_edit = QLineEdit()
        self.deps_edit.setPlaceholderText("e.g. rclpy std_msgs")
        form_layout.addRow("Dependencies:", self.deps_edit)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Create")
        self.cancel_btn = QPushButton("Cancel")

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def showEvent(self, event):
        super().showEvent(event)
        center_dialog_on_parent(self)
        QTimer.singleShot(0, lambda: center_dialog_on_parent(self))

    def get_data(self):
        deps_text = self.deps_edit.text().strip()
        deps = deps_text.split() if deps_text else []
        return {
            "name": self.name_edit.text().strip(),
            "build_type": self.type_combo.currentText(),
            "dependencies": deps
        }


class CreateNodeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add ROS2 Node")
        self.resize(400, 200)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.pkg_combo = QComboBox()
        # The caller will populate this
        form_layout.addRow("Target Package:", self.pkg_combo)

        self.name_edit = QLineEdit()
        form_layout.addRow("Node Name:", self.name_edit)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["python", "cpp"])
        form_layout.addRow("Language:", self.lang_combo)

        self.node_type_combo = QComboBox()
        self.node_type_combo.addItems(["Normal Node", "Lifecycle Node"])
        form_layout.addRow("Node Type:", self.node_type_combo)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Add")
        self.cancel_btn = QPushButton("Cancel")

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def showEvent(self, event):
        super().showEvent(event)
        center_dialog_on_parent(self)
        QTimer.singleShot(0, lambda: center_dialog_on_parent(self))

    def get_data(self):
        return {
            "package": self.pkg_combo.currentText(),
            "name": self.name_edit.text().strip(),
            "language": self.lang_combo.currentText(),
            "node_type": self.node_type_combo.currentText()
        }


class NodeProfileDialog(QDialog):
    def __init__(self, parent=None, profile_manager=None, pkg_name="", node_name=""):
        super().__init__(parent)
        self.setWindowTitle(f"Configure {node_name}")
        self.resize(500, 300)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.profile_manager = profile_manager
        self.pkg_name = pkg_name
        self.node_name = node_name

        layout = QVBoxLayout(self)

        # Profile selection
        prof_layout = QHBoxLayout()
        prof_layout.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        prof_layout.addWidget(self.profile_combo, 1)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete_profile)
        prof_layout.addWidget(self.delete_btn)
        layout.addLayout(prof_layout)

        form_layout = QFormLayout()

        self.app_args_edit = QLineEdit()
        self.app_args_edit.setPlaceholderText("e.g. --config /path/to/config.yaml")
        form_layout.addRow("App Args:", self.app_args_edit)

        self.ros_args_edit = QLineEdit()
        self.ros_args_edit.setPlaceholderText("e.g. -p robot_ip:=192.168.1.10")
        form_layout.addRow("ROS Args:", self.ros_args_edit)

        self.cwd_edit = QLineEdit()
        self.cwd_edit.setPlaceholderText("Working Directory")
        form_layout.addRow("Working Dir:", self.cwd_edit)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")

        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        self._load_profiles()

    def showEvent(self, event):
        super().showEvent(event)
        center_dialog_on_parent(self)
        QTimer.singleShot(0, lambda: center_dialog_on_parent(self))

    def _load_profiles(self):
        if not self.profile_manager:
            return

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()

        profiles = self.profile_manager.load_profiles(self.pkg_name, self.node_name)
        if profiles:
            for p in profiles:
                self.profile_combo.addItem(p["profile_name"], p)
            self._populate_fields(profiles[0])
        else:
            self.profile_combo.addItem("default", None)

        self.profile_combo.blockSignals(False)

    def _on_profile_changed(self, text):
        idx = self.profile_combo.findText(text)
        if idx >= 0:
            data = self.profile_combo.itemData(idx)
            if data:
                self._populate_fields(data)
                return

        # If new profile typed or no data
        self.app_args_edit.clear()
        self.ros_args_edit.clear()
        self.cwd_edit.clear()

    def _populate_fields(self, data):
        self.app_args_edit.setText(data.get("app_args", ""))
        self.ros_args_edit.setText(data.get("ros_args", ""))
        self.cwd_edit.setText(data.get("working_directory", ""))

    def _delete_profile(self):
        if not self.profile_manager:
            return
        profile_name = self.profile_combo.currentText()
        if not profile_name:
            return

        self.profile_manager.delete_profile(self.pkg_name, self.node_name, profile_name)
        self._load_profiles()

    def get_data(self):
        return {
            "profile_name": self.profile_combo.currentText().strip() or "default",
            "app_args": self.app_args_edit.text().strip(),
            "ros_args": self.ros_args_edit.text().strip(),
            "working_directory": self.cwd_edit.text().strip()
        }
