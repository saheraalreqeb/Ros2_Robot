"""
gui/urdf_viewer.py
==================
Improved URDF Viewer featuring:
  • Primary 3D viewport rendered with PySide6 QOpenGLWidget (no extra deps)
  • Per-joint sliders for live joint-angle control in 3D
  • Collapsible side panel: XML Code / Hierarchy Tree / Kinematic Diagram
  • Full theme integration via ThemeManager
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import (
    QColor, QFont, QPen, QBrush, QPainter,
    QRadialGradient
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QAbstractItemView, QDoubleSpinBox, QFrame, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea,
    QSlider, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget
)

from gui.theme import ThemeManager

# ─── Geometry helpers ──────────────────────────────────────────────────────────

def _deg(rad: float) -> float:
    return math.degrees(rad)

def _rad(deg: float) -> float:
    return math.radians(deg)


# ─── URDF data structures ──────────────────────────────────────────────────────

class URDFLink:
    """Stores parsed data for a single URDF link."""
    def __init__(self, name: str):
        self.name = name
        self.has_visual = False
        self.has_collision = False
        self.has_inertial = False
        # Visual geometry approximation for 3D drawing
        self.geometry_type: str = "box"   # "box" | "cylinder" | "sphere"
        self.geometry_size: Tuple = (0.15, 0.15, 0.15)   # (x,y,z) / (r,l) / (r)
        # World-space transform (computed at render time)
        self.world_pos: List[float] = [0.0, 0.0, 0.0]
        self.world_rot: List[float] = [0.0, 0.0, 0.0]   # roll, pitch, yaw (rad)


class URDFJoint:
    """Stores parsed data for a single URDF joint."""
    def __init__(self):
        self.name: str = ""
        self.type: str = "fixed"
        self.parent: str = ""
        self.child: str = ""
        self.origin_xyz: List[float] = [0.0, 0.0, 0.0]
        self.origin_rpy: List[float] = [0.0, 0.0, 0.0]
        self.axis: List[float] = [0.0, 0.0, 1.0]
        self.limit_lower: float = -math.pi
        self.limit_upper: float = math.pi
        # Current angle (set by sliders)
        self.current_angle: float = 0.0

    @property
    def is_actuated(self) -> bool:
        return self.type in ("revolute", "continuous", "prismatic")


# ─── 3-D renderer widget ───────────────────────────────────────────────────────

class URDFViewport3D(QOpenGLWidget):
    """
    Lightweight 3-D renderer for URDF robots.

    Uses QPainter + trigonometry to project a simple 3-D kinematic chain to 2-D.
    No OpenGL shader code required — QOpenGLWidget provides a clean surface that
    we paint with QPainter's anti-aliased paths.

    Controls
    --------
    • Left-drag   → orbit (azimuth / elevation)
    • Right-drag  → pan
    • Scroll      → zoom
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Scene data
        self._links: Dict[str, URDFLink] = {}
        self._joints: List[URDFJoint] = []

        # Camera state
        self._azimuth: float = 30.0      # degrees
        self._elevation: float = 25.0   # degrees
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_mode: str | None = None   # "orbit" | "pan"
        self._drag_start = None
        self._drag_cam_start = None

        # Grid
        self._show_grid = True
        self._show_axes = True

        # Repaint timer (smooth redraws after changes)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.update)

        self.setMinimumSize(QSize(320, 260))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ── public API ──────────────────────────────────────────────────────────────

    def load_robot(self, links: Dict[str, URDFLink], joints: List[URDFJoint]) -> None:
        self._links = links
        self._joints = joints
        self._auto_fit()
        self.update()

    def update_joint_angle(self, joint_name: str, angle: float) -> None:
        for j in self._joints:
            if j.name == joint_name:
                j.current_angle = angle
                break
        self._timer.start(16)   # ~60 fps

    def clear(self) -> None:
        self._links = {}
        self._joints = []
        self.update()

    # ── camera helpers ──────────────────────────────────────────────────────────

    def _auto_fit(self) -> None:
        """Reset camera to nicely frame the loaded robot."""
        self._azimuth = 30.0
        self._elevation = 25.0
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

    def _project(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """
        Simple orthographic projection with orbit camera.
        Returns (screen_x, screen_y, depth) in widget-local coordinates.
        """
        az = _rad(self._azimuth)
        el = _rad(self._elevation)

        # Rotate around Y axis (azimuth)
        rx = x * math.cos(az) + z * math.sin(az)
        ry_tmp = y
        rz = -x * math.sin(az) + z * math.cos(az)

        # Rotate around X axis (elevation)
        rx2 = rx
        ry2 = ry_tmp * math.cos(el) - rz * math.sin(el)
        rz2 = ry_tmp * math.sin(el) + rz * math.cos(el)

        # Scale & center
        scale = 150.0 * self._zoom
        cx = self.width() / 2 + self._pan_x
        cy = self.height() / 2 + self._pan_y

        sx = cx + rx2 * scale
        sy = cy - ry2 * scale   # Y flipped for screen
        return sx, sy, rz2

    # ── forward kinematics ──────────────────────────────────────────────────────

    def _compute_transforms(self) -> Dict[str, Tuple[List[float], List[float]]]:
        """
        Walk the kinematic chain and compute world-space positions.
        Returns {link_name: (pos_xyz, rot_rpy)}.
        """
        child_to_joint: Dict[str, URDFJoint] = {}
        parent_to_children: Dict[str, List[str]] = {}
        for j in self._joints:
            child_to_joint[j.child] = j
            if j.parent not in parent_to_children:
                parent_to_children[j.parent] = []
            parent_to_children[j.parent].append(j.child)

        # Root links: not a child of any joint
        roots = [l for l in self._links if l not in child_to_joint]
        if not roots and self._links:
            roots = [next(iter(self._links))]

        transforms: Dict[str, Tuple[List[float], List[float]]] = {}

        def walk(link_name: str, pos: List[float], rpy: List[float]) -> None:
            transforms[link_name] = (list(pos), list(rpy))
            for child_name in parent_to_children.get(link_name, []):
                j = child_to_joint[child_name]
                # Joint origin offset
                ox, oy, oz = j.origin_xyz
                or_, op, oy_ = j.origin_rpy
                # Apply parent rotation to offset (simplified — only yaw)
                yaw = rpy[2]
                nx = pos[0] + ox * math.cos(yaw) - oy * math.sin(yaw)
                ny = pos[1] + ox * math.sin(yaw) + oy * math.cos(yaw)
                nz = pos[2] + oz

                # For revolute joints, add current angle around axis
                new_rpy = [rpy[0] + or_, rpy[1] + op, rpy[2] + oy_]
                if j.is_actuated and j.type == "revolute":
                    ax, ay, az_ = j.axis
                    new_rpy[0] += ax * j.current_angle
                    new_rpy[1] += ay * j.current_angle
                    new_rpy[2] += az_ * j.current_angle

                walk(child_name, [nx, ny, nz], new_rpy)

        for r in roots:
            walk(r, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])

        return transforms

    # ── drawing ──────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        p = ThemeManager.palette()
        bg = QColor(p["bg_main"])
        painter.fillRect(self.rect(), bg)

        if not self._links:
            painter.setPen(QColor(p["text_dim"]))
            painter.setFont(QFont("Segoe UI", 13))
            painter.drawText(
                self.rect(), Qt.AlignCenter,
                "Select a URDF / Xacro file to view the robot in 3-D"
            )
            painter.end()
            return

        if self._show_grid:
            self._draw_grid(painter, p)
        if self._show_axes:
            self._draw_axes(painter)

        transforms = self._compute_transforms()
        self._draw_robot(painter, p, transforms)
        self._draw_hud(painter, p)

        painter.end()

    def _draw_grid(self, painter: QPainter, p: dict) -> None:
        grid_color = QColor(p["border"])
        grid_color.setAlpha(80)
        painter.setPen(QPen(grid_color, 1))

        grid_step = 0.25
        grid_count = 8
        for i in range(-grid_count, grid_count + 1):
            # Lines along X
            x0, y0, _ = self._project(i * grid_step, 0, -grid_count * grid_step)
            x1, y1, _ = self._project(i * grid_step, 0, grid_count * grid_step)
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))
            # Lines along Z
            x0, y0, _ = self._project(-grid_count * grid_step, 0, i * grid_step)
            x1, y1, _ = self._project(grid_count * grid_step, 0, i * grid_step)
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))

    def _draw_axes(self, painter: QPainter) -> None:
        origin = self._project(0, 0, 0)
        axes = [
            (self._project(0.4, 0, 0), QColor("#ef4444"), "X"),
            (self._project(0, 0.4, 0), QColor("#22c55e"), "Y"),
            (self._project(0, 0, 0.4), QColor("#3b82f6"), "Z"),
        ]
        for (sx, sy, _), color, label in axes:
            painter.setPen(QPen(color, 2))
            painter.drawLine(int(origin[0]), int(origin[1]), int(sx), int(sy))
            painter.setPen(color)
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(int(sx) + 3, int(sy) - 3, label)

    def _draw_robot(
        self, painter: QPainter, p: dict,
        transforms: Dict[str, Tuple[List[float], List[float]]]
    ) -> None:
        """Draw links as capsules and joints as connections."""
        child_to_joint: Dict[str, URDFJoint] = {j.child: j for j in self._joints}
        link_color = QColor(p["accent"])
        joint_color = QColor(p["info"])
        edge_color = QColor(p["border_accent"])
        text_color = QColor(p["text_primary"])

        # Collect projected positions
        proj: Dict[str, Tuple[float, float, float]] = {}
        for link_name, (pos, _) in transforms.items():
            proj[link_name] = self._project(*pos)

        # Sort by depth for painter's algorithm
        sorted_links = sorted(
            [l for l in self._links if l in proj],
            key=lambda l: proj[l][2]
        )

        # Draw edges first (behind links)
        for j in self._joints:
            if j.parent in proj and j.child in proj:
                px, py, _ = proj[j.parent]
                cx, cy, _ = proj[j.child]
                painter.setPen(QPen(edge_color, 3))
                painter.drawLine(int(px), int(py), int(cx), int(cy))

                # Draw joint marker
                mx = int((px + cx) / 2)
                my = int((py + cy) / 2)
                jc = QColor(p["warning"]) if j.is_actuated else QColor(p["border_accent"])
                painter.setPen(QPen(jc, 2))
                painter.setBrush(QBrush(jc))
                painter.drawEllipse(mx - 5, my - 5, 10, 10)

        # Draw links
        for link_name in sorted_links:
            sx, sy, depth = proj[link_name]
            link = self._links[link_name]

            # Node size based on zoom
            r = max(8, int(12 * self._zoom))

            # Gradient fill
            grad = QRadialGradient(sx - r * 0.3, sy - r * 0.3, r * 1.4)
            lighter = link_color.lighter(130)
            grad.setColorAt(0.0, lighter)
            grad.setColorAt(1.0, link_color)

            painter.setPen(QPen(QColor(p["border_accent"]), 1))
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(int(sx - r), int(sy - r), r * 2, r * 2)

            # Link name label
            painter.setPen(text_color)
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(int(sx) + r + 3, int(sy) + 4, link_name)

    def _draw_hud(self, painter: QPainter, p: dict) -> None:
        """Draw overlay info: link/joint count, camera info."""
        painter.setFont(QFont("Consolas", 9))
        painter.setPen(QColor(p["text_dim"]))
        lines = [
            f"Links: {len(self._links)}  Joints: {len(self._joints)}",
            f"Az: {self._azimuth:.0f}°  El: {self._elevation:.0f}°  Zoom: {self._zoom:.2f}x",
            "Drag: orbit  |  Right-drag: pan  |  Scroll: zoom",
        ]
        y = self.height() - 14 * len(lines) - 6
        for line in lines:
            painter.drawText(8, y, line)
            y += 14

    # ── mouse / wheel ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_mode = "orbit"
        elif event.button() == Qt.RightButton:
            self._drag_mode = "pan"
        self._drag_start = event.position()
        self._drag_cam_start = (
            self._azimuth, self._elevation, self._pan_x, self._pan_y
        )

    def mouseMoveEvent(self, event) -> None:
        if not self._drag_mode or not self._drag_start:
            return
        dx = event.position().x() - self._drag_start.x()
        dy = event.position().y() - self._drag_start.y()
        az0, el0, px0, py0 = self._drag_cam_start

        if self._drag_mode == "orbit":
            self._azimuth = az0 + dx * 0.5
            self._elevation = max(-89, min(89, el0 - dy * 0.5))
        elif self._drag_mode == "pan":
            self._pan_x = px0 + dx
            self._pan_y = py0 + dy

        self.update()

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_mode = None

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else 1 / 1.12
        self._zoom = max(0.1, min(10.0, self._zoom * factor))
        self.update()

    def mouseDoubleClickEvent(self, _event) -> None:
        """Double-click resets camera."""
        self._auto_fit()
        self.update()


# ─── Joint control panel ───────────────────────────────────────────────────────

class JointControlPanel(QScrollArea):
    """
    Scrollable panel with one slider + spinbox per actuated joint.
    Emits angle_changed(joint_name, angle_rad) on interaction.
    """

    angle_changed = Signal(str, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(10)
        self._layout.addStretch(1)
        self.setWidget(self._inner)
        self._controls: Dict[str, Tuple[QSlider, QDoubleSpinBox]] = {}

    def load_joints(self, joints: List[URDFJoint]) -> None:
        # Clear existing
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._controls.clear()
        actuated = [j for j in joints if j.is_actuated]

        if not actuated:
            lbl = QLabel("No moveable joints found")
            lbl.setAlignment(Qt.AlignCenter)
            p = ThemeManager.palette()
            lbl.setStyleSheet(f"color: {p['text_dim']}; font-style: italic;")
            self._layout.addWidget(lbl)
            self._layout.addStretch(1)
            return

        for joint in actuated:
            frame = QFrame()
            frame.setFrameShape(QFrame.NoFrame)
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.setSpacing(4)

            # Label row
            lbl_row = QHBoxLayout()
            lbl_name = QLabel(joint.name)
            lbl_name.setFont(QFont("Segoe UI", 10, QFont.Bold))
            lbl_type = QLabel(f"[{joint.type}]")
            p = ThemeManager.palette()
            lbl_type.setStyleSheet(f"color: {p['text_dim']}; font-size: 10px;")
            lbl_row.addWidget(lbl_name)
            lbl_row.addWidget(lbl_type)
            lbl_row.addStretch()
            fl.addLayout(lbl_row)

            # Slider + spinbox row
            ctrl_row = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            lo = int(math.degrees(joint.limit_lower)) if joint.type != "continuous" else -180
            hi = int(math.degrees(joint.limit_upper)) if joint.type != "continuous" else 180
            slider.setRange(lo * 10, hi * 10)   # ×10 for 0.1° precision
            slider.setValue(0)
            slider.setTickPosition(QSlider.TicksBothSides)
            slider.setTickInterval(max(1, (hi - lo) * 10 // 8))

            spin = QDoubleSpinBox()
            spin.setRange(float(lo), float(hi))
            spin.setValue(0.0)
            spin.setSuffix("°")
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setFixedWidth(80)

            # Cross-connect
            name = joint.name   # capture for lambdas

            def _slider_changed(val: int, n: str = name, sp: QDoubleSpinBox = spin) -> None:
                deg = val / 10.0
                sp.blockSignals(True)
                sp.setValue(deg)
                sp.blockSignals(False)
                self.angle_changed.emit(n, math.radians(deg))

            def _spin_changed(val: float, n: str = name, sl: QSlider = slider) -> None:
                sl.blockSignals(True)
                sl.setValue(int(val * 10))
                sl.blockSignals(False)
                self.angle_changed.emit(n, math.radians(val))

            slider.valueChanged.connect(_slider_changed)
            spin.valueChanged.connect(_spin_changed)

            ctrl_row.addWidget(slider, 1)
            ctrl_row.addWidget(spin)
            fl.addLayout(ctrl_row)

            # Reset button
            reset_btn = QPushButton("Reset")
            reset_btn.setProperty("class", "action-button")
            reset_btn.setFixedHeight(22)

            def _reset(n: str = name, sl: QSlider = slider) -> None:
                sl.setValue(0)

            reset_btn.clicked.connect(_reset)
            fl.addWidget(reset_btn, 0, Qt.AlignRight)

            self._controls[joint.name] = (slider, spin)
            self._layout.addWidget(frame)

        self._layout.addStretch(1)

    def reset_all(self) -> None:
        for sl, sp in self._controls.values():
            sl.setValue(0)


# ─── Main URDF Viewer Page ─────────────────────────────────────────────────────

class URDFViewerPage(QWidget):
    """Top-level URDF viewer page widget."""

    def __init__(self, cli=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cli = cli
        self.workspace_path = os.getcwd()
        self.active_file: Optional[str] = None
        self.links: Dict[str, URDFLink] = {}
        self.joints: List[URDFJoint] = []
        self.all_files: List[Tuple[str, str, str]] = []

        self._build_ui()
        self.scan_workspace()

    # ── public helpers ──────────────────────────────────────────────────────────

    def set_workspace(self, path: str) -> None:
        self.workspace_path = path
        self.scan_workspace()

    def refresh_theme(self) -> None:
        p = ThemeManager.palette()
        self.splitter_main.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )
        self.splitter_right.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )
        self._apply_tabs_style(p)
        self._rebuild_joint_panel()
        if self.links:
            self._refresh_diagram()
            self._build_tree()

    # ── UI construction ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        p = ThemeManager.palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top toolbar ──────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setObjectName("urdf_toolbar")
        toolbar.setStyleSheet(
            f"QFrame#urdf_toolbar {{"
            f"  background-color: {p['bg_card']};"
            f"  border-bottom: 1px solid {p['border']};"
            f"  padding: 6px 16px;"
            f"}}"
        )
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(16, 6, 16, 6)
        tb_lay.setSpacing(10)

        lbl_title = QLabel("URDF Viewer")
        lbl_title.setProperty("class", "h1")
        tb_lay.addWidget(lbl_title)

        tb_lay.addStretch()

        self.lbl_active = QLabel("No file selected")
        self.lbl_active.setStyleSheet(
            f"color: {p['text_secondary']}; font-size: 12px;"
        )
        tb_lay.addWidget(self.lbl_active)

        btn_reset_cam = QPushButton("Reset Camera")
        btn_reset_cam.setProperty("class", "action-button")
        btn_reset_cam.clicked.connect(self._reset_camera)
        tb_lay.addWidget(btn_reset_cam)

        btn_reset_joints = QPushButton("Reset Joints")
        btn_reset_joints.setProperty("class", "btn-warning")
        btn_reset_joints.clicked.connect(self._reset_joints)
        tb_lay.addWidget(btn_reset_joints)

        btn_refresh = QPushButton("Refresh Files")
        btn_refresh.setProperty("class", "btn-primary")
        btn_refresh.clicked.connect(self.scan_workspace)
        tb_lay.addWidget(btn_refresh)

        root.addWidget(toolbar)

        # ── Main horizontal splitter ─────────────────────────────────────────
        # Left: file list  |  Right: 3-D + controls + detail tabs
        self.splitter_main = QSplitter(Qt.Horizontal)
        self.splitter_main.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )
        root.addWidget(self.splitter_main, 1)

        # ── Left panel: file list ────────────────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(12, 12, 12, 12)
        left_lay.setSpacing(8)

        lbl_files = QLabel("Robot Description Files")
        lbl_files.setStyleSheet(
            f"color: {p['text_secondary']}; font-size: 11px; "
            f"font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;"
        )
        left_lay.addWidget(lbl_files)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter URDF / Xacro…")
        self.txt_search.textChanged.connect(self._filter_files)
        left_lay.addWidget(self.txt_search)

        self.list_urdf_files = QListWidget()
        self.list_urdf_files.setObjectName("list_urdf_files")
        self.list_urdf_files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_urdf_files.currentItemChanged.connect(self._on_file_selected)
        left_lay.addWidget(self.list_urdf_files)

        self.splitter_main.addWidget(left)

        # ── Right area: vertical splitter ────────────────────────────────────
        # Top: 3-D viewport + joint controls side-by-side
        # Bottom: detail tabs (XML / Hierarchy / Diagram)
        self.splitter_right = QSplitter(Qt.Vertical)
        self.splitter_right.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

        # Top section: 3-D + joint controls
        top_widget = QWidget()
        top_lay = QHBoxLayout(top_widget)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(0)

        # 3-D viewport (dominant)
        self.viewport3d = URDFViewport3D()
        top_lay.addWidget(self.viewport3d, 3)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {p['border']};")
        top_lay.addWidget(sep)

        # Joint control panel
        joint_panel_wrap = QWidget()
        joint_panel_wrap.setMinimumWidth(200)
        joint_panel_wrap.setMaximumWidth(280)
        jp_lay = QVBoxLayout(joint_panel_wrap)
        jp_lay.setContentsMargins(8, 8, 8, 8)
        jp_lay.setSpacing(6)

        lbl_joints = QLabel("Joint Controls")
        lbl_joints.setStyleSheet(
            f"color: {p['text_secondary']}; font-size: 11px; "
            f"font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;"
        )
        jp_lay.addWidget(lbl_joints)

        self.joint_panel = JointControlPanel()
        self.joint_panel.angle_changed.connect(self.viewport3d.update_joint_angle)
        jp_lay.addWidget(self.joint_panel, 1)

        top_lay.addWidget(joint_panel_wrap)
        self.splitter_right.addWidget(top_widget)

        # Bottom section: detail tabs
        detail_widget = QWidget()
        detail_lay = QVBoxLayout(detail_widget)
        detail_lay.setContentsMargins(8, 4, 8, 8)
        detail_lay.setSpacing(4)

        self.tabs_urdf = QTabWidget()
        self.tabs_urdf.setObjectName("tabs_urdf")
        self._apply_tabs_style(p)

        # Tab 1: Hierarchy Tree
        self.tree_urdf_hierarchy = QTreeWidget()
        self.tree_urdf_hierarchy.setObjectName("tree_urdf_hierarchy")
        self.tree_urdf_hierarchy.setHeaderLabels(["Kinematic Tree"])
        self.tabs_urdf.addTab(self.tree_urdf_hierarchy, "Hierarchy")

        # Tab 2: Kinematic Diagram (2-D overview)
        self.view_urdf_diagram = QGraphicsView()
        self.view_urdf_diagram.setObjectName("view_urdf_diagram")
        self.view_urdf_diagram.setRenderHint(QPainter.Antialiasing)
        self.scene_urdf = QGraphicsScene()
        self.view_urdf_diagram.setScene(self.scene_urdf)
        self.tabs_urdf.addTab(self.view_urdf_diagram, "Graph")

        detail_lay.addWidget(self.tabs_urdf)
        self.splitter_right.addWidget(detail_widget)

        # 70 % viewport / 30 % detail tabs
        self.splitter_right.setSizes([650, 280])

        self.splitter_main.addWidget(self.splitter_right)
        self.splitter_main.setSizes([200, 900])

    def _apply_tabs_style(self, p: dict) -> None:
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
                padding: 6px 14px;
                border: 1px solid {p['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 12px;
                font-weight: 600;
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

    # ── scanning & loading ──────────────────────────────────────────────────────

    def scan_workspace(self) -> None:
        self.list_urdf_files.clear()
        self.all_files = []

        src_path = os.path.join(self.workspace_path, "src")
        if not os.path.exists(src_path):
            src_path = self.workspace_path

        for root_dir, _, files in os.walk(src_path):
            for fname in files:
                if fname.endswith(".urdf") or fname.endswith(".xacro"):
                    full = os.path.join(root_dir, fname)
                    rel = os.path.relpath(full, self.workspace_path).replace("\\", "/")
                    self.all_files.append((fname, rel, full))

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
            self.lbl_active.setText("No URDF/Xacro files found")
            self.tree_urdf_hierarchy.clear()
            self.scene_urdf.clear()
            self.viewport3d.clear()

    def _on_file_selected(
        self, current: QListWidgetItem, _previous: QListWidgetItem
    ) -> None:
        if not current:
            return

        filepath = current.data(Qt.UserRole)
        self.active_file = filepath
        self.lbl_active.setText(os.path.basename(filepath))

        # Load raw content
        raw_content = ""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_content = f.read()
        except Exception as exc:
            raw_content = f"Error reading file:\n{exc}"

        # Resolve xacro if possible
        parsed_xml = raw_content
        if filepath.endswith(".xacro"):
            try:
                proc = subprocess.run(
                    ["xacro", filepath],
                    capture_output=True, text=True, check=True, timeout=10
                )
                parsed_xml = proc.stdout
            except Exception:
                pass   # Fallback to raw xacro

        self._parse_and_build(parsed_xml)

    # ── parsing ──────────────────────────────────────────────────────────────────

    def _parse_and_build(self, xml_content: str) -> None:
        self.links = {}
        self.joints = []
        self.tree_urdf_hierarchy.clear()
        self.scene_urdf.clear()

        if not xml_content.strip() or "Error reading file" in xml_content:
            self.viewport3d.clear()
            return

        root_el = self._parse_xml(xml_content)
        if root_el is None:
            self.viewport3d.clear()
            return

        robot_tag = (
            root_el if root_el.tag in ("robot",) else root_el.find(".//robot") or root_el
        )

        self._parse_links(robot_tag)
        self._parse_joints(robot_tag)

        if not self.links:
            self.tree_urdf_hierarchy.addTopLevelItem(
                QTreeWidgetItem(["No links found in robot description"])
            )
            self.viewport3d.clear()
            return

        self._build_tree()
        self._refresh_diagram()
        self._rebuild_joint_panel()
        self.viewport3d.load_robot(self.links, self.joints)

    def _parse_xml(self, xml_content: str) -> ET.Element | None:
        try:
            return ET.fromstring(xml_content)
        except Exception:
            pass
        try:
            clean = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
            return ET.fromstring(clean)
        except Exception as e2:
            self.tree_urdf_hierarchy.addTopLevelItem(
                QTreeWidgetItem([f"⚠️ XML Parsing Error: {e2}"])
            )
            return None

    def _parse_links(self, robot_tag: ET.Element) -> None:
        for link_el in robot_tag.findall(".//link"):
            name = link_el.get("name")
            if not name:
                continue
            lk = URDFLink(name)
            lk.has_visual = link_el.find("visual") is not None
            lk.has_collision = link_el.find("collision") is not None
            lk.has_inertial = link_el.find("inertial") is not None

            # Extract geometry for 3-D approximation
            vis = link_el.find("visual")
            if vis is not None:
                geom = vis.find("geometry")
                if geom is not None:
                    box = geom.find("box")
                    cyl = geom.find("cylinder")
                    sph = geom.find("sphere")
                    if box is not None:
                        size_str = box.get("size", "0.1 0.1 0.1").split()
                        try:
                            lk.geometry_type = "box"
                            lk.geometry_size = tuple(float(s) for s in size_str[:3])
                        except ValueError:
                            pass
                    elif cyl is not None:
                        try:
                            lk.geometry_type = "cylinder"
                            lk.geometry_size = (
                                float(cyl.get("radius", 0.05)),
                                float(cyl.get("length", 0.1)),
                            )
                        except ValueError:
                            pass
                    elif sph is not None:
                        try:
                            lk.geometry_type = "sphere"
                            lk.geometry_size = (float(sph.get("radius", 0.05)),)
                        except ValueError:
                            pass
            self.links[name] = lk

    def _parse_joints(self, robot_tag: ET.Element) -> None:
        for joint_el in robot_tag.findall(".//joint"):
            name = joint_el.get("name")
            if not name:
                continue
            jtype = joint_el.get("type", "fixed")
            parent_el = joint_el.find("parent")
            child_el = joint_el.find("child")
            if parent_el is None or child_el is None:
                continue
            p_name = parent_el.get("link")
            c_name = child_el.get("link")
            if not p_name or not c_name:
                continue

            j = URDFJoint()
            j.name = name
            j.type = jtype
            j.parent = p_name
            j.child = c_name

            origin_el = joint_el.find("origin")
            if origin_el is not None:
                xyz_str = origin_el.get("xyz", "0 0 0").split()
                rpy_str = origin_el.get("rpy", "0 0 0").split()
                try:
                    j.origin_xyz = [float(v) for v in xyz_str[:3]]
                except ValueError:
                    pass
                try:
                    j.origin_rpy = [float(v) for v in rpy_str[:3]]
                except ValueError:
                    pass

            axis_el = joint_el.find("axis")
            if axis_el is not None:
                xyz_str = axis_el.get("xyz", "0 0 1").split()
                try:
                    j.axis = [float(v) for v in xyz_str[:3]]
                except ValueError:
                    pass

            limit_el = joint_el.find("limit")
            if limit_el is not None and jtype != "continuous":
                try:
                    j.limit_lower = float(limit_el.get("lower", str(-math.pi)))
                    j.limit_upper = float(limit_el.get("upper", str(math.pi)))
                except ValueError:
                    pass

            self.joints.append(j)

    # ── hierarchy tree ──────────────────────────────────────────────────────────

    def _build_tree(self) -> None:
        p2j: Dict[str, List[URDFJoint]] = {}
        c2p: Dict[str, str] = {}
        for j in self.joints:
            p2j.setdefault(j.parent, []).append(j)
            c2p[j.child] = j.parent

        roots = [l for l in self.links if l not in c2p]
        if not roots and self.links:
            roots = [next(iter(self.links))]

        def add_node(parent_item: QTreeWidgetItem, link_name: str) -> None:
            lk = self.links.get(link_name)
            tag = "🤖" if lk else "?"
            icon = "🔵" if (lk and lk.has_visual) else "⚪"
            link_item = QTreeWidgetItem([f"{icon} {link_name}"])
            parent_item.addChild(link_item)
            for j in p2j.get(link_name, []):
                emoji = "🔄" if j.is_actuated else "🔩"
                joint_item = QTreeWidgetItem([f"{emoji} {j.name} ({j.type})"])
                link_item.addChild(joint_item)
                if j.child in self.links:
                    add_node(joint_item, j.child)

        for r in roots:
            root_item = QTreeWidgetItem([f"🤖 {r}"])
            self.tree_urdf_hierarchy.addTopLevelItem(root_item)
            for j in p2j.get(r, []):
                emoji = "🔄" if j.is_actuated else "🔩"
                joint_item = QTreeWidgetItem([f"{emoji} {j.name} ({j.type})"])
                root_item.addChild(joint_item)
                if j.child in self.links:
                    add_node(joint_item, j.child)

        self.tree_urdf_hierarchy.expandAll()

    # ── 2-D diagram ─────────────────────────────────────────────────────────────

    def _refresh_diagram(self) -> None:
        self.scene_urdf.clear()
        p = ThemeManager.palette()

        p2j: Dict[str, List[URDFJoint]] = {}
        c2p: Dict[str, str] = {}
        for j in self.joints:
            p2j.setdefault(j.parent, []).append(j)
            c2p[j.child] = j.parent

        roots = [l for l in self.links if l not in c2p]
        if not roots and self.links:
            roots = [next(iter(self.links))]

        positions: Dict[str, Tuple[float, float]] = {}
        depth_w = 180
        node_h = 90
        y_off = [40]

        def calc_pos(link_name: str, depth: int) -> Tuple[float, float]:
            children_joints = p2j.get(link_name, [])
            children = [j.child for j in children_joints if j.child in self.links]
            if not children:
                pos = (depth * depth_w + 50, y_off[0])
                y_off[0] += node_h
                positions[link_name] = pos
                return pos
            child_coords = [calc_pos(c, depth + 1) for c in children]
            x = depth * depth_w + 50
            y = sum(cy for _, cy in child_coords) / len(child_coords)
            positions[link_name] = (x, y)
            return (x, y)

        for r in roots:
            calc_pos(r, 0)
            y_off[0] += 40

        border_c = QColor(p["border"])
        accent_c = QColor(p["accent"])
        link_c = QColor(p["success"])
        warn_c = QColor(p["warning"])
        text_c = QColor(p["text_primary"])
        dim_c = QColor(p["text_secondary"])

        # Edges
        for j in self.joints:
            if j.parent in positions and j.child in positions:
                px, py = positions[j.parent]
                cx, cy = positions[j.child]
                pen = QPen(warn_c if j.is_actuated else accent_c, 2)
                self.scene_urdf.addLine(px + 24, py, cx - 24, cy, pen)
                mx, my = (px + cx) / 2, (py + cy) / 2
                lbl = self.scene_urdf.addText(f"{j.name} ({j.type})")
                lbl.setDefaultTextColor(dim_c)
                f = lbl.font(); f.setPointSize(7); f.setItalic(True); lbl.setFont(f)
                br = lbl.boundingRect()
                lbl.setPos(mx - br.width() / 2, my - br.height() - 2)

        # Nodes
        node_r = 24
        for name, (x, y) in positions.items():
            self.scene_urdf.addEllipse(
                x - node_r, y - node_r, node_r * 2, node_r * 2,
                QPen(border_c, 2), QBrush(link_c)
            )
            t = self.scene_urdf.addText(name)
            t.setDefaultTextColor(text_c)
            f = t.font(); f.setPointSize(8); f.setBold(True); t.setFont(f)
            br = t.boundingRect()
            t.setPos(x - br.width() / 2, y + node_r + 4)

        self.scene_urdf.setSceneRect(self.scene_urdf.itemsBoundingRect())

    # ── joint panel rebuild ──────────────────────────────────────────────────────

    def _rebuild_joint_panel(self) -> None:
        self.joint_panel.load_joints(self.joints)

    # ── button callbacks ─────────────────────────────────────────────────────────

    def _reset_camera(self) -> None:
        self.viewport3d._auto_fit()
        self.viewport3d.update()

    def _reset_joints(self) -> None:
        self.joint_panel.reset_all()
