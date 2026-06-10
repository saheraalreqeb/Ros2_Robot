import os
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QListWidget, QListWidgetItem, QSplitter, QTabWidget,
    QPlainTextEdit, QTreeWidget, QTreeWidgetItem, QGraphicsView,
    QGraphicsScene, QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QBrush, QFont

from gui.theme import ThemeManager

class URDFViewerPage(QWidget):
    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path = os.getcwd()
        self.active_file: Optional[str] = None
        self.links: Dict[str, Any] = {}
        self.joints: List[Dict[str, Any]] = []

        self._build_ui()
        self.scan_workspace()

    def set_workspace(self, path: str) -> None:
        self.workspace_path = path
        self.scan_workspace()

    def _build_ui(self) -> None:
        p = ThemeManager.palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(14)

        # Title
        title_row = QHBoxLayout()
        title = QLabel("URDF Viewer")
        title.setProperty("class", "h1")
        title_row.addWidget(title)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "action-button")
        btn_refresh.clicked.connect(self.scan_workspace)
        title_row.addWidget(btn_refresh, 0, Qt.AlignRight)
        root.addLayout(title_row)

        desc = QLabel(
            "Inspect and visualize Unified Robot Description Format (URDF) "
            "and Xacro files in your workspace."
        )
        desc.setWordWrap(True)
        root.addWidget(desc)

        # Splitter layout
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

        # Left panel: file selector
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)

        lbl_files = QLabel("Workspace Robot Descriptions")
        lbl_files.setStyleSheet("font-weight: bold;")
        left_lay.addWidget(lbl_files)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter URDF/Xacro files...")
        self.txt_search.textChanged.connect(self._filter_files)
        left_lay.addWidget(self.txt_search)

        self.list_urdf_files = QListWidget()
        self.list_urdf_files.setObjectName("list_urdf_files")
        self.list_urdf_files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_urdf_files.currentItemChanged.connect(self._on_file_selected)
        left_lay.addWidget(self.list_urdf_files)

        self.splitter.addWidget(left_panel)

        # Right panel: detail tabs
        self.right_panel = QWidget()
        right_lay = QVBoxLayout(self.right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(8)

        self.lbl_active_file = QLabel("Select a file to inspect")
        self.lbl_active_file.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.lbl_active_file.setWordWrap(True)
        right_lay.addWidget(self.lbl_active_file)

        self.tabs_urdf = QTabWidget()
        self.tabs_urdf.setObjectName("tabs_urdf")
        self._apply_tabs_style(p)

        # Tab 1: XML view
        self.txt_urdf_xml = QPlainTextEdit()
        self.txt_urdf_xml.setObjectName("txt_urdf_xml")
        self.txt_urdf_xml.setReadOnly(True)
        self.txt_urdf_xml.setFont(QFont("monospace", 10))
        self.tabs_urdf.addTab(self.txt_urdf_xml, "XML Code")

        # Tab 2: Hierarchy Tree
        self.tree_urdf_hierarchy = QTreeWidget()
        self.tree_urdf_hierarchy.setObjectName("tree_urdf_hierarchy")
        self.tree_urdf_hierarchy.setHeaderLabels(["Kinematic Tree Element"])
        self.tabs_urdf.addTab(self.tree_urdf_hierarchy, "Hierarchy Tree")

        # Tab 3: Schematic diagram
        self.view_urdf_diagram = QGraphicsView()
        self.view_urdf_diagram.setObjectName("view_urdf_diagram")
        self.scene_urdf = QGraphicsScene()
        self.view_urdf_diagram.setScene(self.scene_urdf)
        self.tabs_urdf.addTab(self.view_urdf_diagram, "Kinematic Diagram")

        right_lay.addWidget(self.tabs_urdf)
        self.splitter.addWidget(self.right_panel)

        self.splitter.setSizes([220, 500])
        root.addWidget(self.splitter, 1)

    def _apply_tabs_style(self, p):
        self.tabs_urdf.setStyleSheet(
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

    def scan_workspace(self) -> None:
        self.list_urdf_files.clear()
        self.all_files = []

        # Find .urdf and .xacro files in workspace src/
        src_path = os.path.join(self.workspace_path, "src")
        if not os.path.exists(src_path):
            src_path = self.workspace_path

        for root, _, files in os.walk(src_path):
            for f in files:
                if f.endswith(".urdf") or f.endswith(".xacro"):
                    full_path = os.path.join(root, f)
                    rel = os.path.relpath(full_path, self.workspace_path)
                    rel = rel.replace('\\', '/')
                    self.all_files.append((f, rel, full_path))

        self.all_files.sort(key=lambda x: x[0])
        self._filter_files()

    def _filter_files(self) -> None:
        self.list_urdf_files.clear()
        query = self.txt_search.text().lower()

        for filename, rel, full_path in self.all_files:
            if query in filename.lower() or query in rel.lower():
                item = QListWidgetItem(filename)
                item.setToolTip(rel)
                item.setData(Qt.UserRole, full_path)
                self.list_urdf_files.addItem(item)

        if self.list_urdf_files.count() > 0:
            self.list_urdf_files.setCurrentRow(0)
        else:
            self.lbl_active_file.setText("No URDF/Xacro files found")
            self.txt_urdf_xml.clear()
            self.tree_urdf_hierarchy.clear()
            self.scene_urdf.clear()

    def _on_file_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        if not current:
            return

        filepath = current.data(Qt.UserRole)
        self.active_file = filepath
        self.lbl_active_file.setText(current.text())

        # Load file contents
        raw_content = ""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_content = f.read()
        except Exception as exc:
            raw_content = f"Error reading file:\n{exc}"

        self.txt_urdf_xml.setPlainText(raw_content)

        # Parse XML
        parsed_xml = None
        is_xacro = filepath.endswith(".xacro")
        if is_xacro:
            # Try running xacro in the background
            try:
                proc = subprocess.run(
                    ["xacro", filepath],
                    capture_output=True,
                    text=True,
                    check=True
                )
                parsed_xml = proc.stdout
            except Exception:
                # Fallback to parsing the raw xacro
                parsed_xml = raw_content
        else:
            parsed_xml = raw_content

        self._parse_and_build(parsed_xml)

    def _parse_and_build(self, xml_content: str) -> None:
        self.links = {}
        self.joints = []
        self.tree_urdf_hierarchy.clear()
        self.scene_urdf.clear()

        if not xml_content.strip():
            return

        try:
            root = ET.fromstring(xml_content)
        except Exception as e:
            # Try standard parsing with some namespaces removed
            try:
                # Strip XML namespaces for robust parsing
                import re
                xml_clean = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
                root = ET.fromstring(xml_clean)
            except Exception as e2:
                # Add an error item to the tree
                self.tree_urdf_hierarchy.addTopLevelItem(
                    QTreeWidgetItem([f"⚠️ XML Parsing Error: {e2}"])
                )
                return

        # Find robot tag or navigate to it
        robot_tag = root if root.tag == "robot" else root.find(".//robot")
        if robot_tag is None:
            # If root node tags don't match, search generally
            robot_tag = root

        # Parse links
        for link in robot_tag.findall(".//link"):
            name = link.get("name")
            if name:
                self.links[name] = {
                    "name": name,
                    "visual": link.find("visual") is not None,
                    "collision": link.find("collision") is not None,
                    "inertial": link.find("inertial") is not None
                }

        # Parse joints
        for joint in robot_tag.findall(".//joint"):
            name = joint.get("name")
            jtype = joint.get("type") or "fixed"
            parent = joint.find("parent")
            child = joint.find("child")

            p_name = parent.get("link") if parent is not None else None
            c_name = child.get("link") if child is not None else None

            if name and p_name and c_name:
                self.joints.append({
                    "name": name,
                    "type": jtype,
                    "parent": p_name,
                    "child": c_name
                })

        if not self.links:
            # Add placeholders if XML has no links parsed
            self.tree_urdf_hierarchy.addTopLevelItem(
                QTreeWidgetItem(["No links found in robot description"])
            )
            return

        # Build hierarchy tree
        self._build_tree()
        self._build_diagram()

    def _build_tree(self) -> None:
        # Determine parent-child structures
        parent_to_joints = {}
        child_to_parent = {}

        for j in self.joints:
            p = j["parent"]
            c = j["child"]
            if p and c:
                if p not in parent_to_joints:
                    parent_to_joints[p] = []
                parent_to_joints[p].append(j)
                child_to_parent[c] = p

        # Roots: links not children of any joint
        roots = [l for l in self.links if l not in child_to_parent]
        if not roots and self.links:
            roots = [list(self.links.keys())[0]]

        def add_node(parent_item, link_name):
            link_item = QTreeWidgetItem([f"🟢 Link: {link_name}"])
            if self.links[link_name]["visual"]:
                link_item.setToolTip(0, "Has visual description")
            parent_item.addChild(link_item)

            if link_name in parent_to_joints:
                for j in parent_to_joints[link_name]:
                    joint_item = QTreeWidgetItem([f"🔗 Joint: {j['name']} ({j['type']})"])
                    link_item.addChild(joint_item)
                    add_node(joint_item, j["child"])

        for r in roots:
            root_item = QTreeWidgetItem([f"🤖 Robot Root: {r}"])
            self.tree_urdf_hierarchy.addTopLevelItem(root_item)

            # Add child joints and links recursively
            if r in parent_to_joints:
                for j in parent_to_joints[r]:
                    joint_item = QTreeWidgetItem([f"🔗 Joint: {j['name']} ({j['type']})"])
                    root_item.addChild(joint_item)
                    add_node(joint_item, j["child"])

        self.tree_urdf_hierarchy.expandAll()

    def _build_diagram(self) -> None:
        # Build structure for diagram
        parent_to_joints = {}
        child_to_parent = {}

        for j in self.joints:
            p = j["parent"]
            c = j["child"]
            if p and c:
                if p not in parent_to_joints:
                    parent_to_joints[p] = []
                parent_to_joints[p].append(j)
                child_to_parent[c] = p

        roots = [l for l in self.links if l not in child_to_parent]
        if not roots and self.links:
            roots = [list(self.links.keys())[0]]

        # Center-based tree layout positions calculation
        positions = {}
        depth_width = 180
        node_height = 80
        y_offset = [50]

        def calculate_positions(link_name, depth):
            joints = parent_to_joints.get(link_name, [])
            children = [j["child"] for j in joints if j["child"] in self.links]

            if not children:
                x = depth * depth_width + 50
                y = y_offset[0]
                y_offset[0] += node_height
                positions[link_name] = (x, y)
                return (x, y)

            child_coords = []
            for child in children:
                child_coords.append(calculate_positions(child, depth + 1))

            x = depth * depth_width + 50
            y = sum(cy for cx, cy in child_coords) / len(child_coords)
            positions[link_name] = (x, y)
            return (x, y)

        for r in roots:
            calculate_positions(r, 0)
            y_offset[0] += 40

        # Draw to QGraphicsScene
        p = ThemeManager.palette()
        border_color = QColor(p["border"])
        accent_color = QColor(p["accent"])
        link_color = QColor(p["success"])
        text_color = QColor(p["text_primary"])

        # Draw links
        node_radius = 24
        for name, (x, y) in positions.items():
            # Draw circle representing link
            self.scene_urdf.addEllipse(
                x - node_radius, y - node_radius,
                node_radius * 2, node_radius * 2,
                QPen(border_color, 2),
                QBrush(link_color)
            )

            # Draw name
            text = self.scene_urdf.addText(name)
            text.setDefaultTextColor(text_color)
            font = text.font()
            font.setPointSize(9)
            font.setBold(True)
            text.setFont(font)
            br = text.boundingRect()
            text.setPos(x - br.width() / 2, y + node_radius + 4)

        # Draw joints (lines connecting links)
        for j in self.joints:
            parent = j["parent"]
            child = j["child"]

            if parent in positions and child in positions:
                px, py = positions[parent]
                cx, cy = positions[child]

                # Draw joint line
                self.scene_urdf.addLine(
                    px + node_radius, py,
                    cx - node_radius, cy,
                    QPen(accent_color, 2)
                )

                # Draw joint name label at center
                mid_x = (px + cx) / 2
                mid_y = (py + cy) / 2
                lbl = self.scene_urdf.addText(f"{j['name']} ({j['type']})")
                lbl.setDefaultTextColor(border_color)
                font = lbl.font()
                font.setPointSize(8)
                font.setItalic(True)
                lbl.setFont(font)
                br = lbl.boundingRect()
                lbl.setPos(mid_x - br.width() / 2, mid_y - br.height() - 2)

        self.scene_urdf.setSceneRect(self.scene_urdf.itemsBoundingRect())

    def refresh_theme(self) -> None:
        p = ThemeManager.palette()
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )
        self._apply_tabs_style(p)
        if hasattr(self, "txt_urdf_xml") and self.txt_urdf_xml.toPlainText().strip():
            self._parse_and_build(self.txt_urdf_xml.toPlainText())
