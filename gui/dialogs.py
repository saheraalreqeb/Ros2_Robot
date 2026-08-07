from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QFormLayout
)
from PySide6.QtCore import Qt

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
