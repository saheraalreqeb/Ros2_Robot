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
