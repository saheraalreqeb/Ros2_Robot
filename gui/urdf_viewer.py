"""
gui/urdf_viewer.py
==================
URDF Viewer with true-geometry 3-D rendering.

• Renders actual boxes, cylinders, and spheres from URDF visual data
  using depth-sorted, back-face-culled, lit polygon faces.
• Full forward kinematics with proper rotation matrices (Rodrigues).
• Per-joint sliders for live joint-angle control.
• Interactive camera: orbit, pan, zoom.
• Hierarchy tree + 2-D kinematic graph in detail tabs.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPointF
from PySide6.QtGui import (
    QColor, QFont, QPen, QBrush, QPainter, QPolygonF,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QAbstractItemView, QDoubleSpinBox, QFrame, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea,
    QSlider, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from gui.theme import ThemeManager

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Linear-algebra helpers (pure Python – no numpy needed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _rot_x(a: float) -> List[List[float]]:
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _rot_y(a: float) -> List[List[float]]:
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rot_z(a: float) -> List[List[float]]:
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _mat3_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def _mat3_vec(m: List[List[float]], v: List[float]) -> List[float]:
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def _rpy_to_matrix(r: float, p: float, y: float) -> List[List[float]]:
    """URDF RPY → rotation matrix  Rz(y) · Ry(p) · Rx(r)."""
    return _mat3_mul(_mat3_mul(_rot_z(y), _rot_y(p)), _rot_x(r))


def _identity3() -> List[List[float]]:
    return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _vadd(a: List[float], b: List[float]) -> List[float]:
    return [a[i] + b[i] for i in range(3)]


def _vsub(a: List[float], b: List[float]) -> List[float]:
    return [a[i] - b[i] for i in range(3)]


def _vscale(v: List[float], s: float) -> List[float]:
    return [x * s for x in v]


def _vcross(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _vdot(a: List[float], b: List[float]) -> float:
    return sum(a[i] * b[i] for i in range(3))


def _vnorm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Rigid-body transform
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _TF:
    """Lightweight rigid-body transform (rotation + translation)."""

    __slots__ = ("rot", "pos")

    def __init__(
        self,
        rot: List[List[float]] | None = None,
        pos: List[float] | None = None,
    ):
        self.rot: List[List[float]] = rot if rot is not None else _identity3()
        self.pos: List[float] = pos if pos is not None else [0.0, 0.0, 0.0]

    def apply(self, p: List[float]) -> List[float]:
        return _vadd(_mat3_vec(self.rot, p), self.pos)

    def chain(self, child: "_TF") -> "_TF":
        """Return self ∘ child."""
        return _TF(
            _mat3_mul(self.rot, child.rot),
            _vadd(_mat3_vec(self.rot, child.pos), self.pos),
        )

    @staticmethod
    def from_xyz_rpy(xyz: List[float], rpy: List[float]) -> "_TF":
        return _TF(_rpy_to_matrix(rpy[0], rpy[1], rpy[2]), list(xyz))

    @staticmethod
    def from_axis_angle(axis: List[float], angle: float) -> "_TF":
        """Rodrigues rotation formula."""
        n = _vnorm(axis)
        if n < 1e-12:
            return _TF()
        ax = [x / n for x in axis]
        c, s = math.cos(angle), math.sin(angle)
        t = 1.0 - c
        x, y, z = ax
        rot = [
            [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
        ]
        return _TF(rot, [0.0, 0.0, 0.0])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Geometry face generators
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# A "Face" is (list-of-3D-vertices, base-QColor).
Face = Tuple[List[List[float]], QColor]


def _box_faces(sx: float, sy: float, sz: float, color: QColor) -> List[Face]:
    """Six quad faces for an axis-aligned box centered at the origin."""
    hw, hh, hd = sx / 2, sy / 2, sz / 2
    v = [
        [-hw, -hh, -hd],  # 0   back-bottom-left
        [hw, -hh, -hd],   # 1   back-bottom-right
        [hw, hh, -hd],    # 2   back-top-right
        [-hw, hh, -hd],   # 3   back-top-left
        [-hw, -hh, hd],   # 4   front-bottom-left
        [hw, -hh, hd],    # 5   front-bottom-right
        [hw, hh, hd],     # 6   front-top-right
        [-hw, hh, hd],    # 7   front-top-left
    ]
    idx = [
        [4, 5, 6, 7],  # +Z  front
        [1, 0, 3, 2],  # -Z  back
        [5, 1, 2, 6],  # +X  right
        [0, 4, 7, 3],  # -X  left
        [7, 6, 2, 3],  # +Y  top
        [0, 1, 5, 4],  # -Y  bottom
    ]
    return [([list(v[i]) for i in f], color) for f in idx]


def _cylinder_faces(
    radius: float, length: float, color: QColor, segs: int = 14
) -> List[Face]:
    """Faces for a cylinder along the Z axis, centered at origin."""
    hl = length / 2
    faces: List[Face] = []
    top, bot = [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        x, y = radius * math.cos(a), radius * math.sin(a)
        top.append([x, y, hl])
        bot.append([x, y, -hl])
    for i in range(segs):
        j = (i + 1) % segs
        faces.append(([bot[i], bot[j], top[j], top[i]], color))
    faces.append(([list(p) for p in top], color.lighter(110)))
    faces.append(([list(p) for p in reversed(bot)], color.darker(110)))
    return faces


def _sphere_faces(
    radius: float, color: QColor, rings: int = 8, segs: int = 10
) -> List[Face]:
    """Faces for a UV sphere centered at origin."""
    pts: List[List[float]] = []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(segs):
            th = 2 * math.pi * j / segs
            pts.append([
                radius * math.sin(phi) * math.cos(th),
                radius * math.sin(phi) * math.sin(th),
                radius * math.cos(phi),
            ])
    faces: List[Face] = []
    for i in range(rings):
        for j in range(segs):
            nj = (j + 1) % segs
            p0 = i * segs + j
            p1 = i * segs + nj
            p2 = (i + 1) * segs + nj
            p3 = (i + 1) * segs + j
            faces.append(
                ([list(pts[p0]), list(pts[p1]), list(pts[p2]), list(pts[p3])], color)
            )
    return faces


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  URDF data structures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class URDFLink:
    """Parsed data for a URDF ``<link>``."""

    def __init__(self, name: str):
        self.name = name
        self.has_visual = False
        self.has_collision = False
        self.has_inertial = False
        self.geometry_type: str = "none"  # box | cylinder | sphere | mesh | none
        self.geometry_size: tuple = ()
        self.visual_xyz: List[float] = [0.0, 0.0, 0.0]
        self.visual_rpy: List[float] = [0.0, 0.0, 0.0]


class URDFJoint:
    """Parsed data for a URDF ``<joint>``."""

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
        self.current_angle: float = 0.0

    @property
    def is_actuated(self) -> bool:
        return self.type in ("revolute", "continuous", "prismatic")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3-D viewport
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class URDFViewport3D(QOpenGLWidget):
    """
    Renders URDF robots as solid 3-D geometry using QPainter.

    Every link's ``<visual><geometry>`` is drawn as the real shape
    (box / cylinder / sphere) with back-face culling, depth sorting,
    and simple Lambertian lighting.

    Controls:
        Left-drag → orbit   |   Right-drag → pan
        Scroll    → zoom    |   Double-click → reset camera
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._links: Dict[str, URDFLink] = {}
        self._joints: List[URDFJoint] = []

        # Camera
        self._az: float = 30.0
        self._el: float = 25.0
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_mode: str | None = None
        self._drag_start = None
        self._drag_snap: tuple | None = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.update)

        self.setMinimumSize(QSize(300, 220))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ── public API ──────────────────────────────────────────────────────────

    def load_robot(
        self, links: Dict[str, URDFLink], joints: List[URDFJoint]
    ) -> None:
        self._links = links
        self._joints = joints
        self._auto_fit()
        self.update()

    def update_joint_angle(self, joint_name: str, angle: float) -> None:
        for j in self._joints:
            if j.name == joint_name:
                j.current_angle = angle
                break
        self._timer.start(16)

    def clear(self) -> None:
        self._links = {}
        self._joints = []
        self.update()

    # ── camera ──────────────────────────────────────────────────────────────

    def _auto_fit(self) -> None:
        self._az = 30.0
        self._el = 25.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        if not self._links:
            self._zoom = 1.0
            return
        tfs = self._compute_fk()
        if not tfs:
            self._zoom = 1.0
            return
        coords = [t.pos for t in tfs.values()]
        extent = 0.0
        for c in coords:
            extent = max(extent, abs(c[0]), abs(c[1]), abs(c[2]))
        # Also consider geometry sizes
        for link in self._links.values():
            if link.geometry_size:
                extent = max(extent, max(link.geometry_size) / 2)
        extent = max(extent, 0.15)
        self._zoom = min(5.0, max(0.2, 0.45 / extent))

    def _cam_matrix(self) -> List[List[float]]:
        return _mat3_mul(_rot_x(-math.radians(self._el)),
                         _rot_y(-math.radians(self._az)))

    def _project(self, pt: List[float]) -> Tuple[float, float, float]:
        r = _mat3_vec(self._cam_matrix(), pt)
        s = 280.0 * self._zoom
        cx = self.width() / 2 + self._pan_x
        cy = self.height() / 2 + self._pan_y
        return (cx + r[0] * s, cy - r[1] * s, r[2])

    # ── forward kinematics ──────────────────────────────────────────────────

    def _compute_fk(self) -> Dict[str, _TF]:
        c2j: Dict[str, URDFJoint] = {j.child: j for j in self._joints}
        p2c: Dict[str, List[str]] = {}
        for j in self._joints:
            p2c.setdefault(j.parent, []).append(j.child)

        roots = [l for l in self._links if l not in c2j]
        if not roots and self._links:
            roots = [next(iter(self._links))]

        out: Dict[str, _TF] = {}

        def walk(name: str, parent_tf: _TF) -> None:
            out[name] = parent_tf
            for child in p2c.get(name, []):
                j = c2j[child]
                jtf = _TF.from_xyz_rpy(j.origin_xyz, j.origin_rpy)
                if j.type in ("revolute", "continuous"):
                    jtf = jtf.chain(_TF.from_axis_angle(j.axis, j.current_angle))
                elif j.type == "prismatic":
                    jtf = jtf.chain(
                        _TF(pos=_vscale(j.axis, j.current_angle))
                    )
                walk(child, parent_tf.chain(jtf))

        for r in roots:
            walk(r, _TF())
        return out

    # ── painting ────────────────────────────────────────────────────────────

    def paintEvent(self, _ev) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pal = ThemeManager.palette()
        painter.fillRect(self.rect(), QColor(pal["bg_main"]))

        if not self._links:
            painter.setPen(QColor(pal["text_dim"]))
            painter.setFont(QFont("Segoe UI", 13))
            painter.drawText(
                self.rect(), Qt.AlignCenter,
                "Select a URDF / Xacro file\nto view the robot in 3-D",
            )
            painter.end()
            return

        self._draw_grid(painter, pal)
        self._draw_axes(painter)

        fk = self._compute_fk()
        self._draw_robot(painter, pal, fk)
        self._draw_labels(painter, pal, fk)
        self._draw_hud(painter, pal)
        painter.end()

    # ── grid / axes ─────────────────────────────────────────────────────────

    def _draw_grid(self, ptr: QPainter, pal: dict) -> None:
        gc = QColor(pal["border"])
        gc.setAlpha(50)
        ptr.setPen(QPen(gc, 1))
        step, n = 0.25, 8
        for i in range(-n, n + 1):
            a = self._project([i * step, 0, -n * step])
            b = self._project([i * step, 0, n * step])
            ptr.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
            a = self._project([-n * step, 0, i * step])
            b = self._project([n * step, 0, i * step])
            ptr.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))

    def _draw_axes(self, ptr: QPainter) -> None:
        o = self._project([0, 0, 0])
        for end, col, lbl in [
            ([0.5, 0, 0], "#ef4444", "X"),
            ([0, 0.5, 0], "#22c55e", "Y"),
            ([0, 0, 0.5], "#3b82f6", "Z"),
        ]:
            e = self._project(end)
            ptr.setPen(QPen(QColor(col), 2))
            ptr.drawLine(int(o[0]), int(o[1]), int(e[0]), int(e[1]))
            ptr.setFont(QFont("Segoe UI", 9, QFont.Bold))
            ptr.drawText(int(e[0]) + 4, int(e[1]) - 4, lbl)

    # ── robot geometry ──────────────────────────────────────────────────────

    def _draw_robot(
        self, ptr: QPainter, pal: dict, fk: Dict[str, _TF]
    ) -> None:
        cam = self._cam_matrix()

        # Light direction (in camera space, pointing into the scene)
        light = [0.3, 0.7, -0.6]
        ln = _vnorm(light)
        light = [x / ln for x in light] if ln > 1e-9 else [0, 0, -1]

        base_color = QColor(pal["accent"])
        mesh_color = QColor(pal["info"])
        joint_col = QColor(pal["warning"])
        none_col = QColor(pal["text_dim"])

        # Collect every renderable face: (avg_depth, projected_poly, color)
        bucket: List[Tuple[float, Any, QColor, str]] = []
        # type = "poly" or "line"

        for name, link in self._links.items():
            if name not in fk:
                continue
            link_tf = fk[name]
            vis_tf = _TF.from_xyz_rpy(link.visual_xyz, link.visual_rpy)
            full_tf = link_tf.chain(vis_tf)

            # Choose geometry
            gt = link.geometry_type
            gs = link.geometry_size
            if gt == "box" and len(gs) >= 3:
                faces = _box_faces(gs[0], gs[1], gs[2], base_color)
            elif gt == "cylinder" and len(gs) >= 2:
                faces = _cylinder_faces(gs[0], gs[1], base_color)
            elif gt == "sphere" and len(gs) >= 1:
                faces = _sphere_faces(gs[0], base_color, rings=6, segs=8)
            elif gt == "mesh":
                faces = _box_faces(0.06, 0.06, 0.06, mesh_color)
            else:
                # No visual geometry → tiny marker
                faces = _sphere_faces(0.012, none_col, rings=3, segs=4)

            for verts, col in faces:
                world = [full_tf.apply(v) for v in verts]
                if len(world) < 3:
                    continue

                # Face normal
                e1 = _vsub(world[1], world[0])
                e2 = _vsub(world[2], world[0])
                normal = _vcross(e1, e2)
                nlen = _vnorm(normal)
                if nlen < 1e-12:
                    continue
                normal = [x / nlen for x in normal]

                # Back-face culling (camera looks along +Z in cam space)
                cam_n = _mat3_vec(cam, normal)
                if cam_n[2] > 0.02:
                    continue

                # Lambertian diffuse
                ndotl = max(0.0, _vdot(cam_n, light))
                bright = 0.30 + 0.70 * ndotl

                fc = QColor(col)
                fc = QColor(
                    min(255, int(fc.red() * bright)),
                    min(255, int(fc.green() * bright)),
                    min(255, int(fc.blue() * bright)),
                    210,
                )

                proj = [self._project(w) for w in world]
                avg_d = sum(p[2] for p in proj) / len(proj)
                poly = [(p[0], p[1]) for p in proj]
                bucket.append((avg_d, poly, fc, "poly"))

        # Joint connection rods
        c2j = {j.child: j for j in self._joints}
        for j in self._joints:
            if j.parent in fk and j.child in fk:
                a = self._project(fk[j.parent].pos)
                b = self._project(fk[j.child].pos)
                avg = (a[2] + b[2]) / 2 + 999  # behind geometry
                jc = joint_col if j.is_actuated else QColor(pal["border_accent"])
                bucket.append(
                    (avg, [(a[0], a[1]), (b[0], b[1])], jc, "line")
                )

        # Depth sort (painter's algorithm: far first)
        bucket.sort(key=lambda f: -f[0])

        for _, poly, col, kind in bucket:
            if kind == "line":
                ptr.setPen(QPen(col, 2))
                ptr.setBrush(Qt.NoBrush)
                ptr.drawLine(
                    int(poly[0][0]), int(poly[0][1]),
                    int(poly[1][0]), int(poly[1][1]),
                )
                mx = int((poly[0][0] + poly[1][0]) / 2)
                my = int((poly[0][1] + poly[1][1]) / 2)
                ptr.setBrush(QBrush(col))
                ptr.setPen(Qt.NoPen)
                ptr.drawEllipse(mx - 3, my - 3, 6, 6)
            else:
                qpoly = QPolygonF([QPointF(x, y) for x, y in poly])
                ptr.setPen(QPen(col.darker(130), 1))
                ptr.setBrush(QBrush(col))
                ptr.drawPolygon(qpoly)

    def _draw_labels(
        self, ptr: QPainter, pal: dict, fk: Dict[str, _TF]
    ) -> None:
        ptr.setFont(QFont("Segoe UI", 7))
        ptr.setPen(QColor(pal["text_secondary"]))
        for name, tf in fk.items():
            sx, sy, _ = self._project(tf.pos)
            ptr.drawText(int(sx) + 6, int(sy) - 3, name)

    def _draw_hud(self, ptr: QPainter, pal: dict) -> None:
        ptr.setFont(QFont("Consolas", 8))
        ptr.setPen(QColor(pal["text_dim"]))
        lines = [
            f"Links: {len(self._links)}  Joints: {len(self._joints)}",
            f"Az: {self._az:.0f}°  El: {self._el:.0f}°  Zoom: {self._zoom:.1f}x",
            "L-drag: orbit | R-drag: pan | Scroll: zoom | Dbl-click: reset",
        ]
        y = self.height() - 13 * len(lines) - 4
        for ln in lines:
            ptr.drawText(8, y, ln)
            y += 13

    # ── mouse / wheel ───────────────────────────────────────────────────────

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        self._drag_mode = "orbit" if ev.button() == Qt.LeftButton else "pan"
        self._drag_start = ev.position()
        self._drag_snap = (self._az, self._el, self._pan_x, self._pan_y)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if not self._drag_mode or not self._drag_start:
            return
        dx = ev.position().x() - self._drag_start.x()
        dy = ev.position().y() - self._drag_start.y()
        a0, e0, px0, py0 = self._drag_snap  # type: ignore[misc]
        if self._drag_mode == "orbit":
            self._az = a0 + dx * 0.5
            self._el = max(-89, min(89, e0 - dy * 0.5))
        else:
            self._pan_x = px0 + dx
            self._pan_y = py0 + dy
        self.update()

    def mouseReleaseEvent(self, _ev) -> None:  # noqa: N802
        self._drag_mode = None

    def wheelEvent(self, ev) -> None:  # noqa: N802
        f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.05, min(20.0, self._zoom * f))
        self.update()

    def mouseDoubleClickEvent(self, _ev) -> None:  # noqa: N802
        self._auto_fit()
        self.update()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Joint control panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class JointControlPanel(QScrollArea):
    """
    Scrollable panel with one card per actuated joint.
    Each card has a slider, a spinbox showing degrees, and a reset button.
    """

    angle_changed = Signal(str, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)
        self.setWidget(self._inner)
        self._ctrls: Dict[str, Tuple[QSlider, QDoubleSpinBox]] = {}

    def load_joints(self, joints: List[URDFJoint]) -> None:
        while self._lay.count() > 0:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._ctrls.clear()

        actuated = [j for j in joints if j.is_actuated]

        if not actuated:
            lbl = QLabel("No moveable joints")
            lbl.setAlignment(Qt.AlignCenter)
            p = ThemeManager.palette()
            lbl.setStyleSheet(f"color: {p['text_dim']}; font-style: italic;")
            self._lay.addWidget(lbl)
            self._lay.addStretch(1)
            return

        p = ThemeManager.palette()
        for joint in actuated:
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background: {p['bg_card']}; "
                f"border: 1px solid {p['border']}; border-radius: 6px; }}"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(3)

            # Joint name (word-wrap so it never clips)
            ln = QLabel(joint.name)
            ln.setFont(QFont("Segoe UI", 9, QFont.Bold))
            ln.setWordWrap(True)
            cl.addWidget(ln)

            # Type badge
            lt = QLabel(joint.type)
            lt.setStyleSheet(
                f"color: {p['text_dim']}; font-size: 9px; "
                f"background: {p['bg_input']}; border: none; "
                f"border-radius: 3px; padding: 1px 5px;"
            )
            lt.setFixedHeight(16)
            cl.addWidget(lt)

            # Slider
            lo = int(math.degrees(joint.limit_lower)) if joint.type != "continuous" else -180
            hi = int(math.degrees(joint.limit_upper)) if joint.type != "continuous" else 180
            slider = QSlider(Qt.Horizontal)
            slider.setRange(lo * 10, hi * 10)
            slider.setValue(0)
            cl.addWidget(slider)

            # Spinbox + reset row
            row = QHBoxLayout()
            row.setSpacing(4)
            spin = QDoubleSpinBox()
            spin.setRange(float(lo), float(hi))
            spin.setValue(0.0)
            spin.setSuffix("°")
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setMinimumWidth(60)

            reset_btn = QPushButton("⟳")
            reset_btn.setToolTip("Reset to 0°")
            reset_btn.setFixedSize(22, 22)
            reset_btn.setStyleSheet(
                f"QPushButton {{ background: {p['bg_input']}; "
                f"border: 1px solid {p['border']}; border-radius: 4px; "
                f"font-size: 13px; padding: 0; }}"
                f"QPushButton:hover {{ background: {p['bg_hover']}; }}"
            )

            row.addWidget(spin, 1)
            row.addWidget(reset_btn)
            cl.addLayout(row)

            # Wire signals  (capture loop vars via defaults)
            name = joint.name

            def _on_slider(val: int, n: str = name, sp: QDoubleSpinBox = spin) -> None:
                deg = val / 10.0
                sp.blockSignals(True)
                sp.setValue(deg)
                sp.blockSignals(False)
                self.angle_changed.emit(n, math.radians(deg))

            def _on_spin(val: float, n: str = name, sl: QSlider = slider) -> None:
                sl.blockSignals(True)
                sl.setValue(int(val * 10))
                sl.blockSignals(False)
                self.angle_changed.emit(n, math.radians(val))

            def _on_reset(_: bool = False, sl: QSlider = slider) -> None:
                sl.setValue(0)

            slider.valueChanged.connect(_on_slider)
            spin.valueChanged.connect(_on_spin)
            reset_btn.clicked.connect(_on_reset)

            self._ctrls[joint.name] = (slider, spin)
            self._lay.addWidget(card)

        self._lay.addStretch(1)

    def reset_all(self) -> None:
        for sl, _ in self._ctrls.values():
            sl.setValue(0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Main URDF Viewer Page
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


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

    # ── public ──────────────────────────────────────────────────────────────

    def set_workspace(self, path: str) -> None:
        self.workspace_path = path
        self.scan_workspace()

    def refresh_theme(self) -> None:
        p = ThemeManager.palette()
        for sp in (self.splitter_main, self.splitter_right, self.splitter_top):
            sp.setStyleSheet(
                f"QSplitter::handle {{ background-color: {p['border']}; }}"
            )
        self._apply_tabs_style(p)
        self._apply_toolbar_style(p)
        self._rebuild_joint_panel()
        if self.links:
            self._refresh_diagram()
            self._build_tree()

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        p = ThemeManager.palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── toolbar ──────────────────────────────────────────────────────
        self.toolbar = QFrame()
        self.toolbar.setObjectName("urdf_toolbar")
        self._apply_toolbar_style(p)

        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(16, 6, 16, 6)
        tb.setSpacing(10)

        lbl_title = QLabel("URDF Viewer")
        lbl_title.setProperty("class", "h1")
        tb.addWidget(lbl_title)
        tb.addStretch()

        self.lbl_active = QLabel("No file selected")
        self.lbl_active.setStyleSheet(
            f"color: {p['text_secondary']}; font-size: 12px;"
        )
        tb.addWidget(self.lbl_active)

        for text, cls, slot in [
            ("Reset Camera", "action-button", self._reset_camera),
            ("Reset Joints", "btn-warning", self._reset_joints),
            ("Refresh Files", "btn-primary", self.scan_workspace),
        ]:
            btn = QPushButton(text)
            btn.setProperty("class", cls)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        root.addWidget(self.toolbar)

        # ── main horizontal splitter  (file list | right area) ───────────
        self.splitter_main = QSplitter(Qt.Horizontal)
        self.splitter_main.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )
        root.addWidget(self.splitter_main, 1)

        # ── left: file list ──────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(6)

        lbl_f = QLabel("ROBOT DESCRIPTION FILES")
        lbl_f.setStyleSheet(
            f"color: {p['text_secondary']}; font-size: 10px; "
            f"font-weight: 600; letter-spacing: 0.5px;"
        )
        ll.addWidget(lbl_f)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter URDF / Xacro…")
        self.txt_search.textChanged.connect(self._filter_files)
        ll.addWidget(self.txt_search)

        self.list_urdf_files = QListWidget()
        self.list_urdf_files.setObjectName("list_urdf_files")
        self.list_urdf_files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_urdf_files.currentItemChanged.connect(self._on_file_selected)
        ll.addWidget(self.list_urdf_files)

        self.splitter_main.addWidget(left)

        # ── right: vertical splitter  (3-D area | detail tabs) ──────────
        self.splitter_right = QSplitter(Qt.Vertical)
        self.splitter_right.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

        # top: 3-D viewport + joint panel in a horizontal splitter
        self.splitter_top = QSplitter(Qt.Horizontal)
        self.splitter_top.setStyleSheet(
            f"QSplitter::handle {{ background-color: {p['border']}; }}"
        )

        self.viewport3d = URDFViewport3D()
        self.splitter_top.addWidget(self.viewport3d)

        # Joint control wrapper
        jp_wrap = QWidget()
        jl = QVBoxLayout(jp_wrap)
        jl.setContentsMargins(6, 6, 6, 6)
        jl.setSpacing(4)
        lbl_jc = QLabel("JOINT CONTROLS")
        lbl_jc.setStyleSheet(
            f"color: {p['text_secondary']}; font-size: 10px; "
            f"font-weight: 600; letter-spacing: 0.5px;"
        )
        jl.addWidget(lbl_jc)
        self.joint_panel = JointControlPanel()
        self.joint_panel.angle_changed.connect(self.viewport3d.update_joint_angle)
        jl.addWidget(self.joint_panel, 1)
        jp_wrap.setMinimumWidth(180)

        self.splitter_top.addWidget(jp_wrap)
        # 75 % viewport, 25 % joint panel
        self.splitter_top.setSizes([700, 240])
        self.splitter_top.setStretchFactor(0, 3)
        self.splitter_top.setStretchFactor(1, 1)

        self.splitter_right.addWidget(self.splitter_top)

        # bottom: detail tabs
        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(6, 2, 6, 6)
        dl.setSpacing(2)

        self.tabs_urdf = QTabWidget()
        self.tabs_urdf.setObjectName("tabs_urdf")
        self._apply_tabs_style(p)

        self.tree_urdf_hierarchy = QTreeWidget()
        self.tree_urdf_hierarchy.setObjectName("tree_urdf_hierarchy")
        self.tree_urdf_hierarchy.setHeaderLabels(["Kinematic Tree"])
        self.tabs_urdf.addTab(self.tree_urdf_hierarchy, "Hierarchy")

        self.view_urdf_diagram = QGraphicsView()
        self.view_urdf_diagram.setObjectName("view_urdf_diagram")
        self.view_urdf_diagram.setRenderHint(QPainter.Antialiasing)
        self.scene_urdf = QGraphicsScene()
        self.view_urdf_diagram.setScene(self.scene_urdf)
        self.tabs_urdf.addTab(self.view_urdf_diagram, "Graph")

        dl.addWidget(self.tabs_urdf)
        self.splitter_right.addWidget(detail)
        self.splitter_right.setSizes([620, 260])

        self.splitter_main.addWidget(self.splitter_right)
        self.splitter_main.setSizes([170, 850])

    def _apply_toolbar_style(self, p: dict) -> None:
        self.toolbar.setStyleSheet(
            f"QFrame#urdf_toolbar {{"
            f"  background-color: {p['bg_card']};"
            f"  border-bottom: 1px solid {p['border']};"
            f"}}"
        )

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
                font-size: 12px; font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background-color: {p['bg_selected']};
                color: {p['text_primary']};
                border-bottom: 2px solid {p['accent']};
            }}
            QTabBar::tab:hover {{ background-color: {p['bg_hover']}; }}
            """
        )

    # ── scan / filter / select ──────────────────────────────────────────────

    def scan_workspace(self) -> None:
        self.list_urdf_files.clear()
        self.all_files = []
        src = os.path.join(self.workspace_path, "src")
        if not os.path.isdir(src):
            src = self.workspace_path
        for dirpath, _, fnames in os.walk(src):
            for fn in fnames:
                if fn.endswith((".urdf", ".xacro")):
                    fp = os.path.join(dirpath, fn)
                    rel = os.path.relpath(fp, self.workspace_path).replace("\\", "/")
                    self.all_files.append((fn, rel, fp))
        self.all_files.sort(key=lambda x: x[0])
        self._filter_files()

    def _filter_files(self) -> None:
        self.list_urdf_files.clear()
        q = self.txt_search.text().lower()
        for fn, rel, fp in self.all_files:
            if q in fn.lower() or q in rel.lower():
                it = QListWidgetItem(fn)
                it.setToolTip(rel)
                it.setData(Qt.UserRole, fp)
                self.list_urdf_files.addItem(it)
        if self.list_urdf_files.count() > 0:
            self.list_urdf_files.setCurrentRow(0)
        else:
            self.lbl_active.setText("No URDF/Xacro files found")
            self.tree_urdf_hierarchy.clear()
            self.scene_urdf.clear()
            self.viewport3d.clear()

    def _on_file_selected(self, cur: QListWidgetItem, _prev) -> None:
        if not cur:
            return
        fp = cur.data(Qt.UserRole)
        self.active_file = fp
        self.lbl_active.setText(os.path.basename(fp))

        raw = ""
        try:
            with open(fp, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as exc:
            raw = f"Error reading file:\n{exc}"

        xml_text = raw
        if fp.endswith(".xacro"):
            try:
                proc = subprocess.run(
                    ["xacro", fp],
                    capture_output=True, text=True, check=True, timeout=10,
                )
                xml_text = proc.stdout
            except Exception:
                pass
        self._parse_and_build(xml_text)

    # ── parsing ─────────────────────────────────────────────────────────────

    def _parse_and_build(self, xml_text: str) -> None:
        self.links = {}
        self.joints = []
        self.tree_urdf_hierarchy.clear()
        self.scene_urdf.clear()

        if not xml_text.strip() or "Error reading file" in xml_text:
            self.viewport3d.clear()
            return

        root_el = self._try_parse(xml_text)
        if root_el is None:
            self.viewport3d.clear()
            return

        robot = root_el if root_el.tag == "robot" else (
            root_el.find(".//robot") or root_el
        )
        self._extract_links(robot)
        self._extract_joints(robot)

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

    def _try_parse(self, xml_text: str) -> ET.Element | None:
        for attempt in (xml_text, re.sub(r'\sxmlns="[^"]+"', "", xml_text, count=1)):
            try:
                return ET.fromstring(attempt)
            except Exception:
                pass
        self.tree_urdf_hierarchy.addTopLevelItem(
            QTreeWidgetItem(["⚠️ XML parsing error"])
        )
        return None

    def _extract_links(self, robot: ET.Element) -> None:
        for el in robot.findall(".//link"):
            name = el.get("name")
            if not name:
                continue
            lk = URDFLink(name)
            lk.has_visual = el.find("visual") is not None
            lk.has_collision = el.find("collision") is not None
            lk.has_inertial = el.find("inertial") is not None

            vis = el.find("visual")
            if vis is not None:
                orig = vis.find("origin")
                if orig is not None:
                    try:
                        lk.visual_xyz = [float(v) for v in orig.get("xyz", "0 0 0").split()[:3]]
                    except ValueError:
                        pass
                    try:
                        lk.visual_rpy = [float(v) for v in orig.get("rpy", "0 0 0").split()[:3]]
                    except ValueError:
                        pass

                geom = vis.find("geometry")
                if geom is not None:
                    box = geom.find("box")
                    cyl = geom.find("cylinder")
                    sph = geom.find("sphere")
                    mesh = geom.find("mesh")
                    if box is not None:
                        try:
                            lk.geometry_type = "box"
                            lk.geometry_size = tuple(
                                float(s) for s in box.get("size", "0.1 0.1 0.1").split()[:3]
                            )
                        except ValueError:
                            pass
                    elif cyl is not None:
                        try:
                            lk.geometry_type = "cylinder"
                            lk.geometry_size = (
                                float(cyl.get("radius", "0.05")),
                                float(cyl.get("length", "0.1")),
                            )
                        except ValueError:
                            pass
                    elif sph is not None:
                        try:
                            lk.geometry_type = "sphere"
                            lk.geometry_size = (float(sph.get("radius", "0.05")),)
                        except ValueError:
                            pass
                    elif mesh is not None:
                        lk.geometry_type = "mesh"
                        # Try to extract scale for approximate sizing
                        sc = mesh.get("scale", "1 1 1").split()
                        try:
                            s = max(float(x) for x in sc[:3])
                            lk.geometry_size = (0.05 * s, 0.05 * s, 0.05 * s)
                        except ValueError:
                            lk.geometry_size = (0.05, 0.05, 0.05)
            self.links[name] = lk

    def _extract_joints(self, robot: ET.Element) -> None:
        for el in robot.findall(".//joint"):
            name = el.get("name")
            if not name:
                continue
            parent_el = el.find("parent")
            child_el = el.find("child")
            if parent_el is None or child_el is None:
                continue
            pn = parent_el.get("link")
            cn = child_el.get("link")
            if not pn or not cn:
                continue

            j = URDFJoint()
            j.name = name
            j.type = el.get("type", "fixed")
            j.parent = pn
            j.child = cn

            orig = el.find("origin")
            if orig is not None:
                try:
                    j.origin_xyz = [float(v) for v in orig.get("xyz", "0 0 0").split()[:3]]
                except ValueError:
                    pass
                try:
                    j.origin_rpy = [float(v) for v in orig.get("rpy", "0 0 0").split()[:3]]
                except ValueError:
                    pass

            ax = el.find("axis")
            if ax is not None:
                try:
                    j.axis = [float(v) for v in ax.get("xyz", "0 0 1").split()[:3]]
                except ValueError:
                    pass

            lim = el.find("limit")
            if lim is not None and j.type != "continuous":
                try:
                    j.limit_lower = float(lim.get("lower", str(-math.pi)))
                    j.limit_upper = float(lim.get("upper", str(math.pi)))
                except ValueError:
                    pass

            self.joints.append(j)

    # ── hierarchy tree ──────────────────────────────────────────────────────

    def _build_tree(self) -> None:
        self.tree_urdf_hierarchy.clear()
        p2j: Dict[str, List[URDFJoint]] = {}
        c2p: Dict[str, str] = {}
        for j in self.joints:
            p2j.setdefault(j.parent, []).append(j)
            c2p[j.child] = j.parent

        roots = [l for l in self.links if l not in c2p]
        if not roots and self.links:
            roots = [next(iter(self.links))]

        def add(parent_item: QTreeWidgetItem, lname: str) -> None:
            lk = self.links.get(lname)
            ico = "🔵" if (lk and lk.has_visual) else "⚪"
            li = QTreeWidgetItem([f"{ico} {lname}"])
            parent_item.addChild(li)
            for j in p2j.get(lname, []):
                em = "🔄" if j.is_actuated else "🔩"
                ji = QTreeWidgetItem([f"{em} {j.name} ({j.type})"])
                li.addChild(ji)
                if j.child in self.links:
                    add(ji, j.child)

        for r in roots:
            ri = QTreeWidgetItem([f"🤖 {r}"])
            self.tree_urdf_hierarchy.addTopLevelItem(ri)
            for j in p2j.get(r, []):
                em = "🔄" if j.is_actuated else "🔩"
                ji = QTreeWidgetItem([f"{em} {j.name} ({j.type})"])
                ri.addChild(ji)
                if j.child in self.links:
                    add(ji, j.child)
        self.tree_urdf_hierarchy.expandAll()

    # ── 2-D diagram ─────────────────────────────────────────────────────────

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

        pos: Dict[str, Tuple[float, float]] = {}
        dw, nh = 180, 90
        yoff = [40]

        def calc(ln: str, depth: int) -> Tuple[float, float]:
            children = [j.child for j in p2j.get(ln, []) if j.child in self.links]
            if not children:
                xy = (depth * dw + 50, yoff[0])
                yoff[0] += nh
                pos[ln] = xy
                return xy
            cc = [calc(c, depth + 1) for c in children]
            x = depth * dw + 50
            y = sum(cy for _, cy in cc) / len(cc)
            pos[ln] = (x, y)
            return (x, y)

        for r in roots:
            calc(r, 0)
            yoff[0] += 40

        bc = QColor(p["border"])
        ac = QColor(p["accent"])
        lc = QColor(p["success"])
        wc = QColor(p["warning"])
        tc = QColor(p["text_primary"])
        dc = QColor(p["text_secondary"])

        for j in self.joints:
            if j.parent in pos and j.child in pos:
                px, py = pos[j.parent]
                cx, cy = pos[j.child]
                pen = QPen(wc if j.is_actuated else ac, 2)
                self.scene_urdf.addLine(px + 24, py, cx - 24, cy, pen)
                mx, my = (px + cx) / 2, (py + cy) / 2
                lb = self.scene_urdf.addText(f"{j.name} ({j.type})")
                lb.setDefaultTextColor(dc)
                f = lb.font()
                f.setPointSize(7)
                f.setItalic(True)
                lb.setFont(f)
                br = lb.boundingRect()
                lb.setPos(mx - br.width() / 2, my - br.height() - 2)

        nr = 24
        for n, (x, y) in pos.items():
            self.scene_urdf.addEllipse(
                x - nr, y - nr, nr * 2, nr * 2,
                QPen(bc, 2), QBrush(lc),
            )
            t = self.scene_urdf.addText(n)
            t.setDefaultTextColor(tc)
            f = t.font()
            f.setPointSize(8)
            f.setBold(True)
            t.setFont(f)
            br = t.boundingRect()
            t.setPos(x - br.width() / 2, y + nr + 4)
        self.scene_urdf.setSceneRect(self.scene_urdf.itemsBoundingRect())

    # ── helpers ─────────────────────────────────────────────────────────────

    def _rebuild_joint_panel(self) -> None:
        self.joint_panel.load_joints(self.joints)

    def _reset_camera(self) -> None:
        self.viewport3d._auto_fit()
        self.viewport3d.update()

    def _reset_joints(self) -> None:
        self.joint_panel.reset_all()
